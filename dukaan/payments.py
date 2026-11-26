"""Check a payment screenshot a customer sent.

IMPORTANT: a screenshot can be edited or faked. The AI reads the screenshot and
checks it against the order, but it CANNOT see your bank account. That is why,
by default (AUTO_DELIVER=false), the owner gets a WhatsApp message and replies
APPROVE <n> after checking the bank app. Turn AUTO_DELIVER on only if you accept that risk.
"""
import datetime as dt
import re

from . import config, db, llm

READ_PROMPT = """You read payment receipt screenshots from Pakistani and international banks and wallets
(bank apps, Raast, IBFT, JazzCash, Easypaisa, SadaPay, NayaPay, PayPal, Wise...).
Extract exactly these fields:
{"is_payment_receipt": true/false,
 "status_text": "what the receipt says, e.g. Successful / Pending / Failed",
 "amount": number or null,
 "currency": "PKR" or other,
 "transaction_id": "the transaction / reference / TID / RRN number, or null",
 "date": "YYYY-MM-DD or null",
 "receiver_name": "name of the person/business that received the money, or null",
 "receiver_account": "account / IBAN / phone number of the receiver (as shown, may be masked), or null",
 "sender_name": "or null",
 "signs_of_editing": "describe anything that looks edited, cropped oddly, mismatched fonts, or 'none'"}
Do not guess. Use null for anything you cannot read."""


def _digits(s):
    return re.sub(r"\D", "", str(s or ""))


def _name_match(a, b):
    a = set(re.findall(r"[a-z]+", str(a or "").lower()))
    b = set(re.findall(r"[a-z]+", str(b or "").lower()))
    return bool(a and b and len(a & b) >= min(2, len(a), len(b)))


def check(image_bytes, mime, order, profile):
    data = llm.ask_json(READ_PROMPT, "Read this payment screenshot.", vision_image_bytes=image_bytes, mime=mime)
    checks, problems = [], []

    def ok(cond, good, bad):
        (checks if cond else problems).append(good if cond else bad)

    ok(bool(data.get("is_payment_receipt")), "Looks like a payment receipt", "Does not look like a payment receipt")
    status = str(data.get("status_text") or "").lower()
    ok(not any(w in status for w in ("fail", "pending", "declin", "reject")),
       "Status is not failed/pending", f"Receipt status: {data.get('status_text')}")
    amount = data.get("amount")
    try:
        amount = float(str(amount).replace(",", "")) if amount is not None else None
    except ValueError:
        amount = None
    ok(amount is not None and amount + 0.5 >= float(order["total"]),
       f"Amount {amount:g} covers order total {order['total']:g}" if amount else "",
       f"Amount {amount} is less than / not readable vs total {order['total']:g}")

    accounts = profile.get("payment_methods", [])
    recv_ok = False
    for acc in accounts:
        if _name_match(data.get("receiver_name"), acc.get("account_title")):
            recv_ok = True
        num = _digits(data.get("receiver_account"))
        for field in ("account_number", "iban", "phone"):
            mine = _digits(acc.get(field))
            if num and mine and len(num) >= 4 and (mine.endswith(num[-4:]) or num.endswith(mine[-4:])):
                recv_ok = True
    ok(recv_ok, "Money went to your account (name/number matches)",
       f"Receiver '{data.get('receiver_name')}' / '{data.get('receiver_account')}' does not match your account")

    tid = str(data.get("transaction_id") or "").strip()
    ok(bool(tid) and not db.payment_ref_used(tid), f"Transaction ID {tid} is new",
       "No transaction ID found" if not tid else f"Transaction ID {tid} was ALREADY USED for another order")

    when = data.get("date")
    fresh = False
    try:
        d = dt.date.fromisoformat(str(when))
        fresh = 0 <= (dt.date.today() - d).days <= config.PAYMENT_MAX_AGE_DAYS
    except ValueError:
        pass
    ok(fresh, f"Date {when} is recent", f"Date '{when}' is missing or older than {config.PAYMENT_MAX_AGE_DAYS} days")

    edit = str(data.get("signs_of_editing") or "none").lower()
    ok(edit in ("none", "no", "", "null"), "No visible signs of editing", f"Possible editing: {data.get('signs_of_editing')}")

    verdict = "passed" if not problems else "failed"
    return {"verdict": verdict, "checks": [c for c in checks if c], "problems": problems,
            "read": data, "transaction_id": tid}
