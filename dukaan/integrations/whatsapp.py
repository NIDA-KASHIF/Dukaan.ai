"""WhatsApp Cloud API (Meta): send text, send PDF documents, download images customers send."""
import mimetypes
from pathlib import Path

import requests

from .. import config


def enabled():
    return bool(config.WA_TOKEN and config.WA_PHONE_NUMBER_ID)


def _url(path):
    return f"https://graph.facebook.com/{config.WA_API_VERSION}/{path}"


def _auth():
    return {"Authorization": f"Bearer {config.WA_TOKEN}"}


def send_text(to, text):
    if not enabled():
        print(f"[WhatsApp off] to {to}: {text}")
        return {"offline": True}
    out = []
    for chunk in [text[i:i + 3900] for i in range(0, len(text), 3900)] or [""]:
        r = requests.post(_url(f"{config.WA_PHONE_NUMBER_ID}/messages"), headers=_auth(), timeout=30, json={
            "messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": chunk}})
        out.append(r.json())
    return out


def upload_media(path):
    path = Path(path)
    mime = mimetypes.guess_type(path.name)[0] or "application/pdf"
    with open(path, "rb") as f:
        r = requests.post(_url(f"{config.WA_PHONE_NUMBER_ID}/media"), headers=_auth(), timeout=180,
                          data={"messaging_product": "whatsapp", "type": mime},
                          files={"file": (path.name, f, mime)})
    r.raise_for_status()
    return r.json()["id"]


def send_document(to, path, caption=""):
    if not enabled():
        print(f"[WhatsApp off] would send {path} to {to}")
        return {"offline": True}
    media_id = upload_media(path)
    r = requests.post(_url(f"{config.WA_PHONE_NUMBER_ID}/messages"), headers=_auth(), timeout=60, json={
        "messaging_product": "whatsapp", "to": to, "type": "document",
        "document": {"id": media_id, "filename": Path(path).name, "caption": caption[:1000]}})
    r.raise_for_status()
    return r.json()


def download_media(media_id):
    """Returns (bytes, mime_type) for an image/document a customer sent."""
    meta = requests.get(_url(media_id), headers=_auth(), timeout=30).json()
    r = requests.get(meta["url"], headers=_auth(), timeout=60)
    r.raise_for_status()
    return r.content, meta.get("mime_type", "image/jpeg")


def parse_webhook(payload):
    """Turn Meta's webhook JSON into a simple list of incoming messages."""
    out = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name", "") for c in value.get("contacts", [])}
            for m in value.get("messages", []):
                item = {"from": m.get("from"), "name": names.get(m.get("from"), ""), "type": m.get("type"),
                        "text": "", "media_id": None, "id": m.get("id")}
                if m["type"] == "text":
                    item["text"] = m["text"]["body"]
                elif m["type"] in ("image", "document"):
                    item["media_id"] = m[m["type"]]["id"]
                    item["text"] = m[m["type"]].get("caption", "")
                elif m["type"] == "interactive":
                    i = m["interactive"]
                    item["text"] = (i.get("button_reply") or i.get("list_reply") or {}).get("title", "")
                out.append(item)
    return out
