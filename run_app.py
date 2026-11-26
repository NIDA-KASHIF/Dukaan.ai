"""Dukaan AI app: the chat interface + the WhatsApp webhook, in one server.

Run:   python run_app.py        then open http://localhost:8000
On a public server set APP_PASSWORD in .env so only you can open the interface.
"""
import hashlib
import hmac
import threading
from collections import deque
from functools import wraps
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, request, send_from_directory, session

from dukaan import agent, config, db
from dukaan.integrations import manual, store, whatsapp
from dukaan.llm import NoProviderError
from dukaan.skills import agents, tools
from dukaan.whatsapp_bot import handle

WEB = Path(__file__).resolve().parent / "web"
app = Flask(__name__, static_folder=None)
app.secret_key = config.env("APP_SECRET_KEY") or hashlib.sha256(
    (config.env("APP_PASSWORD") + str(config.DATA)).encode()).hexdigest()
PASSWORD = config.env("APP_PASSWORD")
_chat_lock = threading.Lock()
_seen = deque(maxlen=500)


# ------------------------------------------------------------------ access control
def _local():
    return request.remote_addr in ("127.0.0.1", "::1") and not request.headers.get("X-Forwarded-For")


def owner_only(fn):
    @wraps(fn)
    def wrap(*a, **k):
        if PASSWORD:
            if not session.get("ok"):
                return (jsonify(error="login"), 401) if request.path.startswith("/api/") else redirect("/login")
        elif not _local():
            return "Set APP_PASSWORD in .env to use Dukaan AI from another device.", 403
        return fn(*a, **k)
    return wrap


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if PASSWORD and hmac.compare_digest(request.form.get("password", ""), PASSWORD):
            session["ok"] = True
            session.permanent = True
            return redirect("/")
        return send_from_directory(WEB, "login.html"), 401
    return send_from_directory(WEB, "login.html")


@app.get("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ------------------------------------------------------------------ pages
@app.get("/")
@owner_only
def home():
    return send_from_directory(WEB, "index.html")


@app.get("/manifest.json")
def manifest():
    return send_from_directory(WEB, "manifest.json")


@app.get("/icon.svg")
def icon():
    return send_from_directory(WEB, "icon.svg")


@app.get("/files/<path:name>")
@owner_only
def files(name):
    return send_from_directory(config.PRODUCTS_DIR, name, as_attachment=request.args.get("dl") == "1")


# ------------------------------------------------------------------ API
def _status():
    plat = store.current()
    return {"ai": config.configured_providers(), "store": plat.NAME, "manual": plat is manual,
            "whatsapp": whatsapp.enabled(), "auto_deliver": config.AUTO_DELIVER,
            "pending": len(db.pending_approvals()), "store_name": config.load_profile().get("store_name")}


@app.get("/api/status")
@owner_only
def api_status():
    return jsonify(_status())


@app.get("/api/history")
@owner_only
def api_history():
    return jsonify(db.history("owner", 60))


@app.post("/api/reset")
@owner_only
def api_reset():
    db.clear_history("owner")
    return jsonify(ok=True)


@app.post("/api/chat")
@owner_only
def api_chat():
    text = (request.get_json(silent=True) or {}).get("message", "").strip()
    if not text:
        return jsonify(error="empty"), 400
    before = {a["id"] for a in db.pending_approvals()}
    with _chat_lock:
        hist = db.history("owner")
        db.add_message("owner", "user", text)
        try:
            reply = agents.manager().run(text, hist)
        except NoProviderError as e:
            reply = f"⚠️ {e}"
        except Exception as e:  # noqa: BLE001
            reply = f"⚠️ Something went wrong: {e}"
        db.add_message("owner", "assistant", reply)
    new = [a for a in db.pending_approvals() if a["id"] not in before]
    return jsonify(reply=reply, approvals=new, status=_status())


@app.post("/api/upload")
@owner_only
def api_upload():
    saved = []
    for f in request.files.getlist("files"):
        name = Path(f.filename or "file").name
        dest = config.PRODUCTS_DIR / name
        f.save(dest)
        saved.append(str(dest))
    return jsonify(saved=saved)


@app.get("/api/approvals")
@owner_only
def api_approvals():
    return jsonify(db.pending_approvals())


@app.post("/api/approvals/<int:aid>/<action>")
@owner_only
def api_approval_action(aid, action):
    msg = agent.run_approved(aid) if action == "approve" else agent.reject(aid)
    return jsonify(message=msg, status=_status())


@app.get("/api/orders")
@owner_only
def api_orders():
    return jsonify(db.list_orders())


@app.post("/api/orders/<int:oid>/deliver")
@owner_only
def api_deliver(oid):
    return jsonify(tools.deliver(oid))


@app.get("/api/products")
@owner_only
def api_products():
    made = [{"name": p.name, "size_kb": p.stat().st_size // 1024,
             "cover": (p.stem + "_cover.jpg") if (config.PRODUCTS_DIR / (p.stem + "_cover.jpg")).exists() else None}
            for p in sorted(config.PRODUCTS_DIR.glob("*.pdf"), key=lambda x: -x.stat().st_mtime)]
    listings = [{"name": Path(f).name, "text": Path(f).read_text(encoding="utf-8")} for f in manual.listing_files()]
    return jsonify(catalog=db.list_products(active_only=False), files=made, listings=listings)


@app.post("/api/products")
@owner_only
def api_add_product():
    d = request.get_json(silent=True) or {}
    files_ = [str(config.PRODUCTS_DIR / Path(f).name) for f in d.get("files", [])]
    pid = db.add_product(d.get("name", "Product"), float(d.get("price") or 0),
                         config.load_profile().get("currency", "PKR"), d.get("description", ""), files_)
    return jsonify(id=pid)


@app.post("/api/products/<int:pid>")
@owner_only
def api_edit_product(pid):
    d = request.get_json(silent=True) or {}
    fields = {k: d[k] for k in ("name", "price", "description", "active") if k in d}
    db.update_product(pid, **fields)
    return jsonify(ok=True)


@app.get("/api/skills")
@owner_only
def api_skills():
    return jsonify(builtin={k: v["about"] for k, v in agents.SPECIALISTS.items()}, custom=tools.custom_skills())


@app.post("/api/skills")
@owner_only
def api_add_skill():
    d = request.get_json(silent=True) or {}
    return jsonify(tools.create_skill.fn(d.get("name", "skill"), d.get("when", ""), d.get("instructions", "")))


@app.delete("/api/skills/<name>")
@owner_only
def api_del_skill(name):
    (config.CUSTOM_SKILLS_DIR / f"{Path(name).name}.md").unlink(missing_ok=True)
    return jsonify(ok=True)


@app.get("/api/profile")
@owner_only
def api_profile():
    return jsonify(config.load_profile())


@app.post("/api/profile")
@owner_only
def api_save_profile():
    prof = config.load_profile()
    prof.update({k: v for k, v in (request.get_json(silent=True) or {}).items() if k in config.DEFAULT_PROFILE})
    config.save_profile(prof)
    return jsonify(ok=True)


# ------------------------------------------------------------------ WhatsApp webhook
@app.get("/webhook")
def wa_verify():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == config.WA_VERIFY_TOKEN:
        return request.args.get("hub.challenge", "")
    abort(403)


@app.post("/webhook")
def wa_incoming():
    secret = config.env("WHATSAPP_APP_SECRET")
    if secret:
        sig = request.headers.get("X-Hub-Signature-256", "")
        good = "sha256=" + hmac.new(secret.encode(), request.get_data(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, good):
            abort(403)
    for msg in whatsapp.parse_webhook(request.get_json(silent=True) or {}):
        if msg["id"] in _seen:
            continue
        _seen.append(msg["id"])
        threading.Thread(target=_safe, args=(msg,), daemon=True).start()
    return "ok", 200


def _safe(msg):
    try:
        handle(msg)
    except Exception as e:  # noqa: BLE001
        print("WhatsApp error:", e)


@app.get("/health")
def health():
    return "ok"


if __name__ == "__main__":
    import webbrowser
    port = int(config.env("PORT", "8000") or 8000)
    print(f"\n  Dukaan AI is running:  http://localhost:{port}\n  (WhatsApp webhook path: /webhook)\n")
    if not config.env("NO_BROWSER"):
        threading.Timer(1.2, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    app.run(host="0.0.0.0" if PASSWORD else "127.0.0.1", port=port, threaded=True)
