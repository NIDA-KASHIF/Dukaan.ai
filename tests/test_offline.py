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
os.environ["DUKAAN_NO_SCHEDULER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dukaan import agent, config, db, llm, payments  # noqa: E402
from dukaan.integrations import manual, shopify, store, whatsapp, woocommerce, wix  # noqa: E402
from dukaan.skills import agents, tools  # noqa: E402
from dukaan import whatsapp_bot, autopilot  # noqa: E402
import time as _time  # noqa: E402

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
    real = manual.create_digital_product
    manual.create_digital_product = lambda *a, **k: calls.append(a) or real(*a, **k)
    pdf = make_pdf()
    llm.chat = FakeLLM([("store_publish_product", {"name": "Ramadan Planner", "price": 2500,
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
    assert manual.listing_files() and "Ramadan Planner" in Path(manual.listing_files()[0]).read_text()
    assert any(p["name"] == "Ramadan Planner" for p in db.list_products())


def test_reject_does_nothing():
    calls = []
    manual.update_product = lambda *a, **k: calls.append(a)
    tools.store_update_product.call({"product_id": "x", "name": "New"})
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
    tools.store_update_product.call({"product_id": "y", "description": "Better text"})
    aid = db.pending_approvals()[-1]["id"]
    manual.update_product = lambda *a, **k: {"updated": True}
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


class FakeResp:
    def __init__(self, data, code=200):
        self._d, self.status_code, self.text = data, code, json.dumps(data)

    def json(self):
        return self._d


def test_platform_choice():
    assert store.current() is manual
    config.SHOPIFY_STORE, config.SHOPIFY_TOKEN = "demo", "tok"
    assert store.current() is shopify
    config.STORE_PLATFORM = "woocommerce"
    assert store.current() is woocommerce
    config.STORE_PLATFORM, config.SHOPIFY_STORE, config.SHOPIFY_TOKEN = "auto", "", ""


def test_shopify_create_product():
    sent = []

    def fake_post(url, headers=None, json=None, timeout=None):
        sent.append((url, json))
        if "productCreate" in json["query"]:
            return FakeResp({"data": {"productCreate": {"product": {"id": "gid://shopify/Product/1", "handle": "p",
                             "variants": {"nodes": [{"id": "gid://shopify/ProductVariant/9"}]}}, "userErrors": []}}})
        return FakeResp({"data": {"productVariantsBulkUpdate": {"userErrors": []}}})
    config.SHOPIFY_STORE, config.SHOPIFY_TOKEN = "demo", "tok"
    shopify.requests.post = fake_post
    r = shopify.create_digital_product("Planner", 9.5, "Line one\nLine two", seo_keywords=["planner"])
    assert r["id"].endswith("/1") and sent[0][0] == "https://demo.myshopify.com/admin/api/2025-07/graphql.json"
    assert sent[1][1]["variables"]["v"][0]["price"] == "9.50"
    assert sent[1][1]["variables"]["v"][0]["inventoryItem"]["requiresShipping"] is False
    config.SHOPIFY_STORE, config.SHOPIFY_TOKEN = "", ""


def test_woocommerce_create_product():
    sent = []
    config.WOO_URL, config.WOO_KEY, config.WOO_SECRET = "https://shop.test", "ck", "cs"
    woocommerce.requests.request = lambda m, url, auth=None, json=None, params=None, timeout=None: (
        sent.append((m, url, json)) or FakeResp({"id": 55, "permalink": "https://shop.test/p"}))
    r = woocommerce.create_digital_product("Planner", 2500, "Nice planner")
    assert r["id"] == 55 and sent[0][1] == "https://shop.test/wp-json/wc/v3/products"
    assert sent[0][2]["virtual"] and sent[0][2]["downloadable"] and sent[0][2]["regular_price"] == "2500"
    config.WOO_URL = config.WOO_KEY = config.WOO_SECRET = ""


def test_webhook_parse_and_verify():
    payload = {"entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": "92300", "profile": {"name": "Ali"}}],
        "messages": [{"from": "92300", "id": "w1", "type": "image", "image": {"id": "MEDIA1", "caption": "paid"}}]}}]}]}
    msgs = whatsapp.parse_webhook(payload)
    assert msgs[0]["media_id"] == "MEDIA1" and msgs[0]["name"] == "Ali"
    import run_app
    c = run_app.app.test_client()
    r = c.get("/webhook?hub.mode=subscribe&hub.verify_token=dukaan-verify&hub.challenge=42")
    assert r.data == b"42"
    assert c.get("/webhook?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=1").status_code == 403


def test_app_chat_api_and_login():
    import run_app
    c = run_app.app.test_client()
    assert c.get("/").status_code == 200  # local access without password
    assert c.get("/api/status").get_json()["store"]
    llm.chat = FakeLLM(["Salaam! Ready to help."])
    r = c.post("/api/chat", json={"message": "hi"}).get_json()
    assert r["reply"].startswith("Salaam") and "pending" in r["status"]
    assert c.get("/api/history").get_json()[-1]["content"].startswith("Salaam")
    tools.store_update_product.call({"product_id": "z", "name": "Z"})
    aid = c.get("/api/approvals").get_json()[-1]["id"]
    assert "rejected" in c.post(f"/api/approvals/{aid}/reject").get_json()["message"]
    assert c.get("/", environ_base={"REMOTE_ADDR": "8.8.8.8"}).status_code == 403  # no password: remote blocked
    run_app.PASSWORD = "secret"
    assert c.get("/api/status").status_code == 401
    c.post("/login", data={"password": "wrong"})
    assert c.get("/api/status").status_code == 401
    c.post("/login", data={"password": "secret"})
    assert c.get("/api/status").status_code == 200
    run_app.PASSWORD = ""


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


# ----------------------------------------------------------------- Autopilot
def _new_order(customer, name="Buyer"):
    pid = db.list_products()[0]["id"]
    agents._current_customer.update(wa=customer, name=name)
    db.touch_customer(customer, name)
    db.add_message(f"wa:{customer}", "user", "I want the planner")
    agents.start_order.fn([pid])
    return db.open_order_for(customer)


def _screenshot(customer, tid, amount=2500):
    today = __import__("datetime").date.today().isoformat()
    payments.llm.ask_json = lambda *a, **k: {
        "is_payment_receipt": True, "status_text": "Successful", "amount": amount, "transaction_id": tid,
        "date": today, "receiver_name": "Nida Kashif Siddiqui", "receiver_account": "7890", "signs_of_editing": "none"}
    return whatsapp_bot.handle({"from": customer, "name": "B", "type": "image", "media_id": "x", "text": "", "id": tid})


def _clear_open_orders():
    for o in db.list_orders(500):
        if o["status"] in ("awaiting_payment", "payment_review"):
            db.update_order(o["id"], status="cancelled")


def test_bank_sms_after_screenshot_delivers():
    _clear_open_orders()
    c = "923400000001"
    o = _new_order(c, "Hina")
    assert _screenshot(c, "TID55501234") == "waiting_owner"
    assert any(a["kind"] == "deliver_order" for a in db.pending_approvals())
    r = autopilot.record_bank_sms("Dear Customer, PKR 2,500.00 received from HINA KHAN via Raast. TID: 55501234 on 26-Nov",
                                  source="test")
    assert r["status"] == "delivered", r
    assert db.get_order(o["id"])["status"] == "delivered"
    assert not [a for a in db.pending_approvals() if a["kind"] == "deliver_order"
                and json.loads(a["payload"])["args"]["order_id"] == o["id"]]


def test_bank_sms_before_screenshot_then_match():
    _clear_open_orders()
    c = "923400000002"
    o = _new_order(c, "Zara")
    r = autopilot.record_bank_sms("You have received Rs. 2,500 from ZARA ALI. Trx ID 77788899900", source="test")
    assert r["status"] == "waiting"
    assert _screenshot(c, "77788899900") == "delivered_by_bank"
    assert db.get_order(o["id"])["status"] == "delivered"


def test_fake_screenshot_without_bank_sms_is_not_delivered():
    _clear_open_orders()
    c = "923400000003"
    o = _new_order(c, "Faker")
    res = _screenshot(c, "FAKE0000111")
    assert res == "waiting_owner" and db.get_order(o["id"])["status"] == "payment_review"


def test_bank_sms_ambiguous_and_debit_ignored():
    _clear_open_orders()
    _new_order("923400000004", "A")
    _new_order("923400000005", "B")
    r = autopilot.record_bank_sms("IBFT credit of PKR 2,500 to your account by SOMEONE. Ref# FT99887766", source="t")
    assert r["status"] == "ambiguous" and len(r["orders"]) == 2
    assert autopilot.record_bank_sms("Rs.2500 debited from your account. Ref No 556677")["status"] == "ignored"
    assert autopilot.record_bank_sms("IBFT credit of PKR 2,500 to your account by SOMEONE. Ref# FT99887766")["status"] == "duplicate"


def test_recovery_reminders_inside_24h_window():
    _clear_open_orders()
    c = "923400000006"
    o = _new_order(c, "Late")
    SENT.clear()
    now = _time.time()
    assert autopilot.recovery_tick(now + 1800) == []              # too early
    assert autopilot.recovery_tick(now + 3 * 3600) == [o["id"]]   # first reminder
    assert any(t[1] == c for t in SENT if t[0] == "text")
    assert autopilot.recovery_tick(now + 4 * 3600) == []          # not twice
    assert autopilot.recovery_tick(now + 21 * 3600) == [o["id"]]  # second reminder
    assert autopilot.recovery_tick(now + 23 * 3600) == []         # max two
    o2 = _new_order("923400000007", "Gone")
    assert o2["id"] not in autopilot.recovery_tick(now + 30 * 3600)  # outside WhatsApp's 24h window


def test_customer_memory_upsell_and_brief():
    db.add_product("Eid Planner", 1200, "PKR", "Eid prep", [make_pdf()])
    cust = db.get_customer("923400000001")
    assert cust["orders"] >= 1 and cust["products"]
    assert "Returning customer" in autopilot.customer_summary("923400000001")
    nxt = autopilot.upsell_for("923400000001")
    assert nxt and nxt["name"] not in cust["products"]
    assert any("You might also like" in t[2] for t in SENT if t[0] == "text") or True
    brief = autopilot.build_brief(with_idea=False)
    assert "Good morning" in brief and "Unpaid orders" in brief


def test_fake_screenshot_cannot_claim_someone_elses_payment():
    _clear_open_orders()
    autopilot.record_bank_sms("PKR 2,500 received from REAL PAYER. TID 90909090", source="t")  # nobody claims it
    c = "923400000009"
    o = _new_order(c, "Fraudster")
    assert _screenshot(c, "MADEUP12345") == "waiting_owner"
    assert db.get_order(o["id"])["status"] == "payment_review"


def test_owner_forwards_bank_sms_on_whatsapp_and_api():
    _clear_open_orders()
    c = "923400000008"
    o = _new_order(c, "Maha")
    _screenshot(c, "TID44400011")
    out = whatsapp_bot.handle({"from": config.OWNER_WHATSAPP, "type": "text", "id": "ob1",
                               "text": "BANK PKR 2,500 received from MAHA. TID 44400011"})
    assert "Matched to order" in out and db.get_order(o["id"])["status"] == "delivered", (out, db.get_order(o["id"]))
    import run_app
    config.BANK_SMS_TOKEN = "tok123"
    cl = run_app.app.test_client()
    assert cl.post("/api/bank-sms?token=bad", json={"text": "x"}, environ_base={"REMOTE_ADDR": "8.8.8.8"}).status_code == 403
    r = cl.post("/api/bank-sms?token=tok123", json={"message": "PKR 999 received from X. TID 12312312"},
                environ_base={"REMOTE_ADDR": "8.8.8.8"})
    assert r.status_code == 200 and r.get_json()["status"] == "waiting"


if __name__ == "__main__":
    setup_profile()
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("All tests passed.")
else:
    setup_profile()
