"""What happens when a WhatsApp message arrives.

Owner's number  -> talks to the Manager agent, and can reply APPROVE 5 / REJECT 5 / PENDING.
Anyone else     -> talks to the Sales agent. A screenshot sent after ordering is checked as a payment.
"""
import re
import threading

from . import agent, config, db, payments
from .integrations import whatsapp
from .skills import agents, tools

_sales_lock = threading.Lock()


def _owner_notify(text):
    if config.OWNER_WHATSAPP:
        whatsapp.send_text(config.OWNER_WHATSAPP, text)


agent.set_owner_notifier(_owner_notify)


def handle(msg):
    sender = msg["from"]
    if config.OWNER_WHATSAPP and sender == config.OWNER_WHATSAPP:
        return handle_owner(msg)
    if msg["type"] in ("image", "document") and msg.get("media_id"):
        return handle_payment(msg)
    return handle_customer_text(msg)


def handle_owner(msg):
    text = (msg.get("text") or "").strip()
    m = re.match(r"^(approve|reject|ok|no)\s*#?(\d+)$", text, re.I)
    if m:
        aid = int(m.group(2))
        reply = agent.run_approved(aid) if m.group(1).lower() in ("approve", "ok") else agent.reject(aid)
    elif text.lower() in ("pending", "approvals"):
        items = db.pending_approvals()
        reply = "\n\n".join(f"#{a['id']}: {a['summary'][:300]}" for a in items) or "Nothing is waiting for approval."
    elif text.lower() in ("reset", "new chat"):
        db.clear_history("owner")
        reply = "New conversation started."
    else:
        hist = db.history("owner")
        db.add_message("owner", "user", text)
        try:
            reply = agents.manager().run(text, hist)
        except Exception as e:  # noqa: BLE001
            reply = f"Sorry, something went wrong: {e}"
        db.add_message("owner", "assistant", reply)
    whatsapp.send_text(msg["from"], reply)
    return reply


def handle_customer_text(msg):
    channel = f"wa:{msg['from']}"
    text = msg.get("text") or ""
    if not text.strip():
        return None
    with _sales_lock:
        hist = db.history(channel, 12)
        db.add_message(channel, "user", text)
        try:
            reply = agents.sales_agent(msg["from"], msg.get("name", "")).run(text, hist)
        except Exception:  # noqa: BLE001
            reply = "Thank you for your message! We will reply shortly. 🤍"
            _owner_notify(f"⚠️ The AI could not answer customer {msg['from']}: {text[:200]}")
        db.add_message(channel, "assistant", reply)
    whatsapp.send_text(msg["from"], reply)
    return reply


def handle_payment(msg):
    customer = msg["from"]
    order = db.open_order_for(customer)
    if not order:
        reply = ("Thank you! I could not find an open order for you. Please tell me which product you want "
                 "and I will create the order first. 🤍")
        whatsapp.send_text(customer, reply)
        return reply
    img, mime = whatsapp.download_media(msg["media_id"])
    profile = config.load_profile()
    try:
        result = payments.check(img, mime, order, profile)
    except Exception as e:  # noqa: BLE001
        result = {"verdict": "failed", "checks": [], "problems": [f"Could not read the screenshot: {e}"],
                  "read": {}, "transaction_id": ""}
    db.update_order(order["id"], status="payment_review",
                    payment={"transaction_id": result["transaction_id"], **result})
    lines = "\n".join("✔ " + c for c in result["checks"]) + ("\n" if result["checks"] else "") + \
        "\n".join("✖ " + p for p in result["problems"])
    head = f"Order #{order['id']} — {order['customer_name'] or customer} — {order['total']:g} {order['currency']}\n" + \
        ", ".join(i["name"] for i in order["items"])

    if result["verdict"] == "passed" and config.AUTO_DELIVER:
        tools.deliver(order["id"])
        _owner_notify(f"💰 Paid & delivered automatically\n{head}\n{lines}")
        return "delivered"

    if result["verdict"] == "passed":
        whatsapp.send_text(customer, "✅ Payment screenshot received, thank you! Your files will be sent in a few minutes.")
        tools.deliver_order.call({"order_id": order["id"]})  # creates approval + notifies owner
        _owner_notify(f"💰 Payment looks correct\n{head}\n{lines}\n\nCheck your bank app, then reply APPROVE with the number above.")
        return "waiting_owner"

    whatsapp.send_text(customer, "Thank you! We received your screenshot. The owner will confirm the payment "
                                 "and send your files soon. 🤍")
    tools.deliver_order.call({"order_id": order["id"]})
    _owner_notify(f"⚠️ Payment needs your check\n{head}\n{lines}\n\nOnly approve after you see the money in your bank.")
    return "needs_check"
