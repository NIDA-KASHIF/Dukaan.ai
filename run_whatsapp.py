"""WhatsApp webhook server.

Run:   python run_whatsapp.py
Then expose it to the internet (for example with:  ngrok http 5000)
and paste  https://<your-ngrok-address>/webhook  in Meta > WhatsApp > Configuration > Webhook.
"""
import hashlib
import hmac
import threading
from collections import deque

from flask import Flask, abort, request

from dukaan import config
from dukaan.integrations import whatsapp
from dukaan.whatsapp_bot import handle

app = Flask(__name__)
_seen = deque(maxlen=500)


@app.get("/")
def home():
    return "Dukaan AI WhatsApp server is running."


@app.get("/webhook")
def verify():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == config.WA_VERIFY_TOKEN:
        return request.args.get("hub.challenge", "")
    abort(403)


def _signature_ok():
    secret = config.env("WHATSAPP_APP_SECRET")
    if not secret:
        return True
    sig = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(secret.encode(), request.get_data(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


@app.post("/webhook")
def incoming():
    if not _signature_ok():
        abort(403)
    for msg in whatsapp.parse_webhook(request.get_json(silent=True) or {}):
        if msg["id"] in _seen:
            continue
        _seen.append(msg["id"])
        threading.Thread(target=_safe_handle, args=(msg,), daemon=True).start()
    return "ok", 200  # answer Meta at once; the reply is sent from the background thread


def _safe_handle(msg):
    try:
        handle(msg)
    except Exception as e:  # noqa: BLE001
        print("Error handling message:", e)


if __name__ == "__main__":
    print("Dukaan AI WhatsApp server on http://localhost:5000  (webhook path: /webhook)")
    app.run(host="0.0.0.0", port=int(config.env("PORT", "5000") or 5000))
