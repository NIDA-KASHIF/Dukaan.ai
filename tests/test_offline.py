"""Offline tests: no API keys needed. The AI, Wix and WhatsApp are replaced by fakes.

Run:  python -m pytest tests -q      (or)   python tests/test_offline.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["DUKAAN_DATA_DIR"] = tempfile.mkdtemp(prefix="dukaan_test_")
os.environ["GEMINI_API_KEY"] = "fake"
os.environ["OWNER_WHATSAPP"] = "923000000000"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dukaan import agent, config, db, llm, payments  # noqa: E402
from dukaan.integrations import whatsapp, wix  # noqa: E402
from dukaan.skills import agents, tools  # noqa: E402
from dukaan import whatsapp_bot  # noqa: E402

SENT = []
whatsapp.send_text = lambda to, text: SENT.append(("text", to, text))
whatsapp.send_document = lambda to, path, caption="": SENT.append(("doc", to, Path(path).name))
whatsapp.download_media = lambda mid: (b"fake-image", "image/jpeg")


class FakeLLM:
    """Plays back a script of replies; each item is text or (tool_name, args)."""

    def __init__(self, script):
        self.script = list(script)

    def __call__(self, messages, tools=None, **kw):
        step = self.script.pop(0)
        if isinstance(step, tuple):
            name, args = step
            return {"role": "assistant", "content": "", "tool_calls": [
                {"id": f"c{len(self.script)}", "type": "function",
                 "function": {"name": name, "arguments": json.dumps(args)}}]}, "fake"
        return {"role": "assistant", "content": step}, "fake"


def setup_profile():
    prof = config.load_profile()
    prof["store_name"] = "Digital Qalam"
    prof["payment_methods"] = [{"type": "Bank", "bank": "Meezan", "account_title": "Nida Kashif Siddiqui",
                                "account_number": "01230104567890"}]
    config.save_profile(prof)


def make_pdf():
    p = config.PRODUCTS_DIR / "planner.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    return str(p)


def test_publish_needs_approval_then_runs():
    calls = []
    wix.create_digital_product = lambda *a, **k: calls.append(a) or {"id": "wix123", "name": a[0]}
    pdf = make_pdf()
    llm.chat = FakeLLM([("wix_publish_product", {"name": "Ramadan Planner", "price": 2500,
                                                 "description": "30 days", "pdf_path": pdf}),
                        "Saved for approval #1."])
    reply = agents.manager().run("Publish my Ramadan planner")
    assert "approval" in reply.lower()
    assert not calls, "Wix must NOT be called before approval"
    pend = db.pending_approvals()
    assert len(pend) == 1 and "Ramadan Planner" in pend[0]["summary"]
    assert any("Approval #" in s[2] for s in SENT if s[0] == "text"), "owner should be notified on WhatsApp"
    out = agent.run_approved(pend[0]["id"])
    assert out.startswith("✅") and calls
    assert any(p["name"] == "Ramadan Planner" for p in db.list_products())


def test_reject_does_nothing():
    calls = []
    wix.update_product = lambda *a, **k: calls.append(a)
    tools.wix_update_product.call({"product_id": "x", "name": "New"})
    aid = db.pending_approvals()[-1]["id"]
    agent.reject(aid)
    assert not calls and db.get_approval(aid)["status"] == "rejected"


def test_sales_order_payment_and_delivery():
    customer = "923111111111"
    pid = db.list_products()[0]["id"]
    llm.chat = FakeLLM([("start_order", {"product_ids": [pid]}), "Your order is ready, please pay."])
    whatsapp_bot.handle({"from": customer, "name": "Ayesha", "type": "text", "text": "I want the planner", "id": "m1"})
    order = db.open_order_for(customer)
    assert order and order["total"] == 2500

    today = __import__("datetime").date.today().isoformat()
    payments.llm.ask_json = lambda *a, **k: {
        "is_payment_receipt": True, "status_text": "Successful", "amount": "2,500", "currency": "PKR",
        "transaction_id": "TID998877", "date": today, "receiver_name": "NIDA KASHIF SIDDIQUI",
        "receiver_account": "****7890", "signs_of_editing": "none"}
    res = whatsapp_bot.handle({"from": customer, "name": "Ayesha", "type": "image", "media_id": "img1", "text": "", "id": "m2"})
    assert res == "waiting_owner", res
    aid = db.pending_approvals()[-1]["id"]
    agent.run_approved(aid)
    assert db.get_order(order["id"])["status"] == "delivered"
    assert ("doc", customer, "planner.pdf") in SENT
    assert db.payment_ref_used("TID998877")


def test_reused_transaction_id_is_caught():
    customer = "923222222222"
    pid = db.list_products()[0]["id"]
    agents._current_customer.update(wa=customer, name="Sara")
    agents.start_order.fn([pid])
    order = db.open_order_for(customer)
    today = __import__("datetime").date.today().isoformat()
    payments.llm.ask_json = lambda *a, **k: {
        "is_payment_receipt": True, "status_text": "Successful", "amount": 2500, "transaction_id": "TID998877",
        "date": today, "receiver_name": "Nida Kashif Siddiqui", "receiver_account": "7890", "signs_of_editing": "none"}
    r = payments.check(b"x", "image/jpeg", order, config.load_profile())
    assert r["verdict"] == "failed" and any("ALREADY USED" in p for p in r["problems"])


def test_wrong_amount_and_receiver():
    order = {"total": 2500}
    payments.llm.ask_json = lambda *a, **k: {
        "is_payment_receipt": True, "status_text": "Successful", "amount": 500, "transaction_id": "NEW1",
        "date": "2001-01-01", "receiver_name": "Someone Else", "receiver_account": "1111", "signs_of_editing": "none"}
    r = payments.check(b"x", "image/jpeg", order, config.load_profile())
    assert r["verdict"] == "failed" and len(r["problems"]) >= 3


def test_owner_commands_on_whatsapp():
    tools.wix_update_product.call({"product_id": "y", "description": "Better text"})
    aid = db.pending_approvals()[-1]["id"]
    wix.update_product = lambda *a, **k: {"updated": True}
    out = whatsapp_bot.handle({"from": config.OWNER_WHATSAPP, "type": "text", "text": f"APPROVE {aid}", "id": "o1"})
    assert out.startswith("✅")


def test_delegate_and_custom_skill():
    built = []
    tools.render.build_pdf = lambda spec, name=None: built.append(spec) or {"pdf": "x.pdf", "pages": 3}
    llm.chat = FakeLLM([
        ("delegate", {"agent": "product_designer", "task": "Kids tracing worksheet"}),
        ("build_printable", {"spec": {"title": "ABC Tracing", "pages": [{"type": "tracing", "text": "A B C"}]}}),
        "Built ABC Tracing (3 pages).",
        "Your worksheet is ready: x.pdf",
    ])
    reply = agents.manager().run("Make a tracing worksheet")
    assert built and built[0]["title"] == "ABC Tracing" and "ready" in reply
    tools.create_skill.fn("eid cards", "Eid greeting cards", "Write 5 Eid card messages.")
    assert "eid_cards" in tools.custom_skills()
    llm.chat = FakeLLM(["1. Eid Mubarak!"])
    assert "Eid" in agents.run_specialist("skill:eid_cards", "Make cards")


def test_webhook_parse_and_verify():
    payload = {"entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": "92300", "profile": {"name": "Ali"}}],
        "messages": [{"from": "92300", "id": "w1", "type": "image", "image": {"id": "MEDIA1", "caption": "paid"}}]}}]}]}
    msgs = whatsapp.parse_webhook(payload)
    assert msgs[0]["media_id"] == "MEDIA1" and msgs[0]["name"] == "Ali"
    import run_whatsapp
    c = run_whatsapp.app.test_client()
    r = c.get("/webhook?hub.mode=subscribe&hub.verify_token=dukaan-verify&hub.challenge=42")
    assert r.data == b"42"
    assert c.get("/webhook?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=1").status_code == 403


def test_provider_fallback():
    import importlib
    importlib.reload(llm)  # undo the fake
    os.environ["GROQ_API_KEY"] = "fake2"
    config.PROVIDERS["groq"]["key"] = "fake2"
    used = []

    class Boom:
        def __init__(self, name):
            self.name = name
            self.chat = self
            self.completions = self

        def create(self, **kw):
            used.append(self.name)
            if self.name == "gemini":
                raise RuntimeError("Error 429 quota exceeded")
            msg = type("M", (), {"content": "hi from groq", "tool_calls": None})
            return type("R", (), {"choices": [type("C", (), {"message": msg})]})

    llm._client = lambda name: Boom(name)
    out, prov = llm.chat([{"role": "user", "content": "hi"}])
    assert prov == "groq" and out["content"] == "hi from groq" and used[0] == "gemini"


if __name__ == "__main__":
    setup_profile()
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("All tests passed.")
else:
    setup_profile()
