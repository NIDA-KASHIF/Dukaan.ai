"""Dukaan Autopilot: the jobs a store owner usually does by hand, every day.

1. Bank SMS match   - your bank's own SMS ("PKR 2,500 received ... TID 123") is matched to the
                      customer's order. Bank-confirmed money = files sent at once. A fake
                      screenshot never matches a real bank SMS.
2. Lost-sale recovery - customers who ordered but did not pay get a polite reminder,
                      inside WhatsApp's 24-hour reply window.
3. Customer memory  - who bought what; returning customers are greeted as such and
                      offered the next product that suits them.
4. Morning brief    - yesterday's sales, money waiting, unpaid orders and today's post idea.
"""
import datetime as dt
import re
import threading
import time

from . import config, db, llm
from .integrations import whatsapp

# ====================================================================== 1. bank SMS
AMOUNT_RE = [
    re.compile(r"(?:PKR|Rs\.?|Rupees|INR|USD|\$|AED|SAR|GBP|£|€)\s*([\d,]+(?:\.\d{1,2})?)", re.I),
    re.compile(r"([\d,]+(?:\.\d{1,2})?)\s*(?:PKR|Rs\.?|Rupees)", re.I),
]
REF_RE = re.compile(r"(?:TID|Trx\.?\s*ID|Txn\.?\s*ID|Tran(?:saction)?\.?\s*(?:ID|#|No\.?|Ref)|Ref(?:erence)?\.?\s*(?:No\.?|#|ID)?|RRN|STAN|Trace\s*(?:No\.?|ID))"
                    r"\s*[:#.\-]?\s*([A-Z0-9][A-Z0-9\-]{4,})", re.I)
SENDER_RE = re.compile(r"(?:from|by|sender[:\s])\s+([A-Za-z][A-Za-z .']{2,40}?)(?=\s+(?:A/?C|a/c|acc|account|via|on|to|IBAN|Raast|ref|TID|\d)|[.,;\n]|$)", re.I)
CREDIT_WORDS = re.compile(r"\b(received|credit(?:ed)?|deposited|incoming|cr\b|has been added|transferred to your|you have received)", re.I)
DEBIT_WORDS = re.compile(r"\b(debited|sent to|paid to|withdrawn|purchase|you have sent|dr\b)", re.I)


def parse_bank_sms(text):
    """Read a bank / wallet SMS. Returns {is_credit, amount, ref, sender}."""
    t = " ".join(text.split())
    amount = None
    for rx in AMOUNT_RE:
        m = rx.search(t)
        if m:
            try:
                amount = float(m.group(1).replace(",", ""))
                break
            except ValueError:
                pass
    ref = (REF_RE.search(t) or [None, ""])[1] if REF_RE.search(t) else ""
    sm = SENDER_RE.search(t)
    sender = sm.group(1).strip() if sm else ""
    is_credit = bool(CREDIT_WORDS.search(t)) and not DEBIT_WORDS.search(t)
    if (amount is None or not CREDIT_WORDS.search(t)) and config.configured_providers():
        try:
            d = llm.ask_json("You read bank and mobile-wallet SMS messages.",
                             'Extract {"is_credit": true if money came IN to this account, "amount": number, '
                             '"ref": "transaction id / TID / reference or empty", "sender": "who sent it or empty"} '
                             f"from this SMS:\n{text}")
            amount = amount if amount is not None else d.get("amount")
            ref = ref or str(d.get("ref") or "")
            sender = sender or str(d.get("sender") or "")
            is_credit = bool(d.get("is_credit", is_credit))
        except Exception:  # noqa: BLE001 - the regex result is still usable
            pass
    try:
        amount = float(str(amount).replace(",", "")) if amount is not None else None
    except ValueError:
        amount = None
    return {"is_credit": is_credit, "amount": amount, "ref": (ref or "").upper(), "sender": sender}


def _norm(ref):
    return re.sub(r"[^A-Z0-9]", "", str(ref or "").upper())


def _refs_match(a, b):
    a, b = _norm(a), _norm(b)
    if len(a) < 5 or len(b) < 5:
        return False
    return a == b or (len(a) >= 8 and len(b) >= 8 and (a.endswith(b[-8:]) or b.endswith(a[-8:])))


def _names_match(a, b):
    a = {w for w in re.findall(r"[a-z]{3,}", str(a or "").lower())}
    b = {w for w in re.findall(r"[a-z]{3,}", str(b or "").lower())}
    return bool(a & b)


def _payer_name(order):
    read = (order.get("payment") or {}).get("read") or {}
    return f"{read.get('sender_name') or ''} {order.get('customer_name') or ''}"


def _open_orders(hours=72):
    since = time.time() - hours * 3600
    return [o for o in db.list_orders(300)
            if o["status"] in ("awaiting_payment", "payment_review") and o["created"] >= since]


def record_bank_sms(text, source="app"):
    """Save a bank SMS and try to match it to an order. Returns what happened."""
    p = parse_bank_sms(text)
    if not p["is_credit"] or not p["amount"]:
        return {"status": "ignored", "reason": "Not an incoming payment (or no amount found).", "read": p}
    if p["ref"] and any(_refs_match(p["ref"], b["ref"]) for b in db.bank_payments(300)):
        return {"status": "duplicate", "read": p}
    bid = db.add_bank_payment(p["amount"], p["ref"], p["sender"], text, source)
    bank = {"id": bid, "amount": p["amount"], "ref": p["ref"], "sender": p["sender"]}
    return {**_match_bank_row(bank), "read": p, "bank_id": bid}


def _match_bank_row(bank):
    same_amount = [o for o in _open_orders() if abs(float(o["total"]) - bank["amount"]) < 1]
    by_ref = [o for o in same_amount if _refs_match(bank["ref"], (o["payment"] or {}).get("transaction_id"))]
    if len(by_ref) == 1:
        return confirm(by_ref[0], bank, "bank SMS transaction ID matches the screenshot")
    claimed = [o for o in same_amount if o["status"] == "payment_review"]
    if len(claimed) == 1 and len(same_amount) == 1:
        if _names_match(bank["sender"], _payer_name(claimed[0])):
            return confirm(claimed[0], bank, "amount and payer name match the only order waiting")
        o = claimed[0]
        _notify(f"🏦 Bank: {bank['amount']:g} received from {bank['sender'] or 'unknown'} (ref {bank['ref'] or '-'}).\n"
                f"It is probably order #{o['id']} ({o['customer_name'] or o['customer']}), but the ID and name do not match. "
                "Check, then APPROVE the delivery if it is right.")
        return {"status": "probable", "order_id": o["id"]}
    if len(same_amount) > 1:
        _notify(f"🏦 Bank: {bank['amount']:g} received from {bank['sender'] or 'unknown'} (ref {bank['ref'] or '-'}).\n"
                f"{len(same_amount)} open orders have this amount: "
                + ", ".join(f"#{o['id']} {o['customer_name'] or o['customer']}" for o in same_amount)
                + "\nReply APPROVE with the right order's approval number.")
        return {"status": "ambiguous", "orders": [o["id"] for o in same_amount]}
    return {"status": "waiting", "reason": "Saved. It will be matched when the customer sends the screenshot."}


def match_for_order(order):
    """Called after a customer's screenshot is checked: is there a bank SMS for it already?"""
    tid = (order.get("payment") or {}).get("transaction_id")
    rows = [b for b in db.bank_payments(200, unmatched_only=True) if time.time() - b["created"] < 72 * 3600
            and abs(b["amount"] - float(order["total"])) < 1]
    exact = [b for b in rows if _refs_match(b["ref"], tid)]
    if len(exact) == 1:
        return confirm(order, exact[0], "bank SMS transaction ID matches the screenshot")
    # Without a matching transaction ID, the amount alone is never enough (a fake screenshot could
    # "claim" someone else's payment). The payer's name on the bank SMS must match too.
    named = [b for b in rows if _names_match(b["sender"], _payer_name(order))]
    others = [o for o in _open_orders() if abs(float(o["total"]) - float(order["total"])) < 1]
    if len(named) == 1 and len(others) == 1 and (order.get("payment") or {}).get("verdict") == "passed":
        return confirm(order, named[0], "bank SMS amount and payer name match")
    return None


def confirm(order, bank, how):
    from .skills import tools  # local import: tools imports this module's callers
    db.set_bank_match(bank["id"], order["id"], how)
    pay = dict(order.get("payment") or {})
    pay.update(bank_confirmed=True, bank_ref=bank.get("ref"), bank_how=how)
    db.update_order(order["id"], payment=pay, paid_at=time.time())
    _close_delivery_approvals(order["id"])
    head = f"Order #{order['id']} · {order['customer_name'] or order['customer']} · {float(order['total']):g} {order['currency']}"
    if config.BANK_AUTO_DELIVER:
        tools.deliver(order["id"])
        _notify(f"✅ Bank confirmed and delivered\n{head}\nHow: {how}")
        return {"status": "delivered", "order_id": order["id"], "how": how}
    tools.deliver_order.call({"order_id": order["id"]})
    _notify(f"✅ Bank confirmed\n{head}\nHow: {how}\nReply APPROVE to send the files.")
    return {"status": "confirmed", "order_id": order["id"], "how": how}


def _close_delivery_approvals(order_id):
    import json
    for a in db.pending_approvals():
        if a["kind"] == "deliver_order" and json.loads(a["payload"]).get("args", {}).get("order_id") == order_id:
            db.set_approval(a["id"], "done", "Handled by bank SMS match")


# ====================================================================== 2. lost-sale recovery
WINDOW = 23.5 * 3600  # WhatsApp lets businesses reply freely for 24h after the customer's last message


def _is_urdu(text):
    return len(re.findall(r"[؀-ۿ]", text or "")) > 3


def _reminder(order, second, urdu):
    items = ", ".join(i["name"] for i in order["items"])
    total = f"{float(order['total']):g} {order['currency']}"
    if urdu:
        if second:
            return f"السلام علیکم! آپ کا آرڈر ({items}) ابھی بھی محفوظ ہے۔ {total} ادا کر کے اسکرین شاٹ یہاں بھیج دیں، فائل فوراً مل جائے گی۔ کوئی سوال ہو تو بتائیں 🤍"
        return f"السلام علیکم! آپ کا آرڈر ({items}) تیار ہے۔ {total} کی ادائیگی کا اسکرین شاٹ بھیج دیں تو فائل فوراً بھیج دی جائے گی۔ ادائیگی میں کوئی مشکل ہو تو بتائیں 🤍"
    if second:
        return (f"Hi! Your order ({items}) is still saved for you. Pay {total} and send the screenshot here, "
                "and your files arrive right away. Any questions? Just reply 🤍")
    return (f"Hi! Your order ({items}) is ready. Send the payment screenshot for {total} and I'll send your files "
            "at once. Need help paying? Just reply 🤍")


def recovery_tick(now=None):
    if not config.RECOVERY:
        return []
    now = now or time.time()
    sent = []
    for o in db.list_orders(300):
        if o["status"] != "awaiting_payment":
            continue
        last_msg = db.last_customer_message_time(o["customer"]) or o["created"]
        if now - last_msg > WINDOW:
            continue  # outside the 24-hour window: WhatsApp would need a paid template
        age_h = (now - o["created"]) / 3600
        n = o.get("nudges") or 0
        second = n == 1 and age_h >= config.RECOVERY_SECOND_HOURS
        if (n == 0 and age_h >= config.RECOVERY_FIRST_HOURS) or second:
            hist = db.history(f"wa:{o['customer']}", 4)
            urdu = any(_is_urdu(h["content"]) for h in hist if h["role"] == "user")
            whatsapp.send_text(o["customer"], _reminder(o, second, urdu))
            db.add_message(f"wa:{o['customer']}", "assistant", "(reminder sent)")
            db.update_order(o["id"], nudges=n + 1, last_nudge=now)
            sent.append(o["id"])
    return sent


# ====================================================================== 3. customer memory
def customer_summary(wa):
    c = db.get_customer(wa)
    if not c or not c["orders"]:
        return "This is a new customer (no purchases yet)."
    return (f"Returning customer {c['name'] or ''}: {c['orders']} order(s), spent {c['spent']:g}. "
            f"Already bought: {', '.join(c['products'])}. Greet them warmly as a returning customer and suggest "
            "products they do not have yet; never offer what they already bought.")


def upsell_for(wa, exclude_names=()):
    if not config.UPSELL:
        return None
    c = db.get_customer(wa) or {"products": []}
    owned = set(c["products"]) | set(exclude_names)
    options = [p for p in db.list_products() if p["name"] not in owned]
    return options[0] if options else None


# ====================================================================== 4. morning brief
def _tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(config.TIMEZONE)
    except Exception:  # noqa: BLE001
        return dt.timezone(dt.timedelta(hours=5))


def build_brief(with_idea=True):
    tz = _tz()
    today = dt.datetime.now(tz).date()
    start_y = dt.datetime.combine(today - dt.timedelta(days=1), dt.time(), tz).timestamp()
    start_t = start_y + 86400
    orders = db.list_orders(500)
    delivered_y = [o for o in orders if o["status"] == "delivered" and start_y <= (o.get("paid_at") or o["created"]) < start_t]
    revenue = sum(float(o["total"]) for o in delivered_y)
    delivered_t = [o for o in orders if o["status"] == "delivered" and (o.get("paid_at") or o["created"]) >= start_t]
    unpaid = [o for o in orders if o["status"] == "awaiting_payment" and time.time() - o["created"] < 72 * 3600]
    review = [o for o in orders if o["status"] == "payment_review"]
    pending = db.pending_approvals()
    week = [o for o in orders if o["status"] == "delivered" and time.time() - o["created"] < 7 * 86400]
    best = {}
    for o in week:
        for i in o["items"]:
            best[i["name"]] = best.get(i["name"], 0) + 1
    top = max(best, key=best.get) if best else None
    recovered = [o for o in delivered_y if (o.get("nudges") or 0) > 0]
    cur = config.load_profile().get("currency", "")
    lines = [f"🌅 *Good morning! {config.load_profile().get('store_name')} — {today:%d %b}*",
             f"💰 Yesterday: {len(delivered_y)} sale(s), {revenue:g} {cur}"]
    if delivered_t:
        lines.append(f"📈 Today so far: {len(delivered_t)} sale(s), {sum(float(o['total']) for o in delivered_t):g} {cur}")
    if recovered:
        lines.append(f"🔁 {len(recovered)} of them came back after a reminder")
    if top:
        lines.append(f"🏆 Best seller this week: {top} ({best[top]})")
    lines.append(f"⏳ Unpaid orders: {len(unpaid)}" + (" (reminders are being sent)" if unpaid and config.RECOVERY else ""))
    if review:
        lines.append(f"🧾 Screenshots waiting for bank confirmation: {len(review)}")
    if pending:
        lines.append(f"🟡 Waiting for your approval: {len(pending)} — reply PENDING to see them")
    if with_idea and config.configured_providers():
        try:
            prods = ", ".join(p["name"] for p in db.list_products()[:8]) or "printable digital products"
            msg, _ = llm.chat([{"role": "user", "content":
                                f"Give ONE short social media post idea for today ({today:%A %d %B}) for a store selling: {prods}. "
                                "Reply with a 1-line idea and a ready caption under 40 words with 3 hashtags."}], temperature=0.8)
            lines.append("\n📣 Today's post idea:\n" + msg["content"].strip())
        except Exception:  # noqa: BLE001
            pass
    return "\n".join(lines)


def maybe_send_brief():
    if config.BRIEF_HOUR < 0 or not config.OWNER_WHATSAPP:
        return False
    now = dt.datetime.now(_tz())
    if now.hour < config.BRIEF_HOUR or db.kv_get("brief_date") == now.date().isoformat():
        return False
    db.kv_set("brief_date", now.date().isoformat())
    whatsapp.send_text(config.OWNER_WHATSAPP, build_brief())
    return True


# ====================================================================== scheduler
def _notify(text):
    from . import agent
    agent.notify_owner(text)


_started = False


def start(every_seconds=300):
    """Run the recovery and brief jobs in the background (started by run_app.py)."""
    global _started
    if _started:
        return
    _started = True

    def loop():
        while True:
            try:
                recovery_tick()
                maybe_send_brief()
            except Exception as e:  # noqa: BLE001
                print("Autopilot error:", e)
            time.sleep(every_seconds)
    threading.Thread(target=loop, daemon=True, name="autopilot").start()
