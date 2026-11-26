"""All tools the agents can use."""
import json
from pathlib import Path

from .. import config, db
from ..agent import tool
from ..integrations import store, whatsapp
from ..pdfgen import render

# ======================= products made by the app =======================


@tool("build_printable",
      "Build a printable PDF product (planner, journal, worksheet, coloring book) from a spec. "
      "Returns paths of the PDF and its cover image.",
      {"spec": {"type": "object", "description": "Product spec: title, subtitle, brand, language (en/ur/ar), "
                "size (A4/A5/Letter), colors {primary, accent, paper}, pages [...] (see page types)."},
       "file_name": {"type": "string", "description": "Short English file name without extension"}},
      ["spec"])
def build_printable(spec, file_name=None):
    if isinstance(spec, str):
        spec = json.loads(spec)
    profile = config.load_profile()
    spec.setdefault("brand", profile.get("store_name", ""))
    spec.setdefault("colors", profile.get("brand_colors", {}))
    return render.build_pdf(spec, render.slug(file_name) if file_name else None)


@tool("list_product_files", "List PDF products already made and saved in the products folder.")
def list_product_files():
    return [{"pdf": str(p), "size_kb": p.stat().st_size // 1024} for p in sorted(config.PRODUCTS_DIR.glob("*.pdf"))]


# ======================= local catalog (what WhatsApp sells) =======================


@tool("catalog_list", "List the products this store sells on WhatsApp, with id, price and files.")
def catalog_list():
    return [{"id": p["id"], "name": p["name"], "price": p["price"], "currency": p["currency"],
             "description": p["description"][:200], "files": p["files"], "store_id": p["wix_id"]}
            for p in db.list_products()]


@tool("catalog_add",
      "Add a product to the WhatsApp catalog so customers can buy it. pdf_paths are the files sent after payment.",
      {"name": {"type": "string"}, "price": {"type": "number"}, "description": {"type": "string"},
       "pdf_paths": {"type": "array", "items": {"type": "string"}}},
      ["name", "price", "pdf_paths"])
def catalog_add(name, price, pdf_paths, description=""):
    missing = [p for p in pdf_paths if not Path(p).exists()]
    if missing:
        return {"error": f"These files do not exist: {missing}"}
    pid = db.add_product(name, price, config.load_profile().get("currency", "PKR"), description, pdf_paths)
    return {"added": True, "product_id": pid}


# ======================= online store (Wix / Shopify / WooCommerce / manual) =======================


@tool("store_status", "Check which store platform is connected (Wix, Shopify, WooCommerce or manual).")
def store_status():
    try:
        return store.current().status()
    except Exception as e:  # noqa: BLE001
        return {"connected": False, "platform": store.name(), "error": str(e)}


@tool("store_list_products", "List products on the online store (name, price, description start, status).")
def store_list_products():
    return store.current().list_products()


@tool("store_list_orders", "List recent orders from the online store.",
      {"limit": {"type": "integer", "description": "How many, default 20"}})
def store_list_orders(limit=20):
    return store.current().list_orders(limit)


def _publish_summary(a):
    return (f"Publish NEW product on {store.name()}:\n• Name: {a.get('name')}\n• Price: {a.get('price')}\n"
            f"• PDF: {Path(a.get('pdf_path') or '-').name}\n• Description:\n{(a.get('description') or '')[:700]}")


@tool("store_publish_product",
      "Create a new digital product on the online store (and add it to the WhatsApp catalog). "
      "In manual mode it saves a ready-to-paste listing file.",
      {"name": {"type": "string"}, "price": {"type": "number"},
       "description": {"type": "string", "description": "Full product description, plain text with line breaks"},
       "pdf_path": {"type": "string"}, "image_paths": {"type": "array", "items": {"type": "string"}},
       "seo_keywords": {"type": "array", "items": {"type": "string"}}},
      ["name", "price", "description"], needs_approval=True, summary=_publish_summary)
def store_publish_product(name, price, description, pdf_path=None, image_paths=None, seo_keywords=None):
    res = store.current().create_digital_product(name, price, description, pdf_path, image_paths or [],
                                                 seo_keywords or [])
    if pdf_path and Path(pdf_path).exists():
        db.add_product(name, price, config.load_profile().get("currency", "PKR"), description, [pdf_path],
                       str(res.get("id") or ""))
    return res


def _update_summary(a):
    parts = [f"UPDATE {store.name()} product {a.get('product_id')}"]
    if a.get("name"):
        parts.append(f"• New name: {a['name']}")
    if a.get("price") is not None:
        parts.append(f"• New price: {a['price']}")
    if a.get("description"):
        parts.append(f"• New description:\n{a['description'][:700]}")
    return "\n".join(parts)


@tool("store_update_product", "Change the name, description or price of an existing store product.",
      {"product_id": {"type": "string"}, "name": {"type": "string"}, "description": {"type": "string"},
       "price": {"type": "number"}},
      ["product_id"], needs_approval=True, summary=_update_summary)
def store_update_product(product_id, name=None, description=None, price=None):
    return store.current().update_product(product_id, name, description, price)


# ======================= orders & approvals =======================


@tool("orders_list", "List recent WhatsApp orders and their status.")
def orders_list():
    return [{"id": o["id"], "customer": o["customer"], "name": o["customer_name"], "total": o["total"],
             "status": o["status"], "items": o["items"]} for o in db.list_orders(30)]


@tool("approvals_list", "List actions waiting for the owner's approval.")
def approvals_list():
    return [{"id": a["id"], "summary": a["summary"][:300]} for a in db.pending_approvals()]


def deliver(order_id):
    """Send every file of the order to the customer on WhatsApp and mark it delivered."""
    order = db.get_order(order_id)
    if not order:
        return {"error": "order not found"}
    sent = []
    for item in order["items"]:
        p = db.get_product(item["product_id"])
        for f in (p or {}).get("files", []):
            whatsapp.send_document(order["customer"], f, caption=p["name"])
            sent.append(Path(f).name)
    store = config.load_profile().get("store_name", "")
    whatsapp.send_text(order["customer"], f"✅ Thank you! Your order #{order_id} has been delivered. "
                                           f"JazakAllah for shopping with {store} 🤍")
    db.update_order(order_id, status="delivered")
    if order["payment"].get("transaction_id"):
        db.mark_payment_ref(order["payment"]["transaction_id"], order_id)
    return {"delivered": sent}


@tool("deliver_order", "Send the purchased PDF files of an order to the customer on WhatsApp.",
      {"order_id": {"type": "integer"}}, ["order_id"], needs_approval=True,
      summary=lambda a: f"Send the files of order #{a.get('order_id')} to the customer")
def deliver_order(order_id):
    return deliver(order_id)


# ======================= memory & self-improvement =======================


@tool("remember", "Save a fact about the store or the owner's preferences for the future.",
      {"note": {"type": "string"}}, ["note"])
def remember(note):
    prof = config.load_profile()
    prof.setdefault("notes", []).append(note)
    prof["notes"] = prof["notes"][-60:]
    config.save_profile(prof)
    return {"saved": True}


@tool("create_skill",
      "Teach yourself a NEW skill when the owner asks for a kind of work you have no agent for. "
      "Write clear step-by-step instructions; afterwards use it with delegate(agent='skill:<name>').",
      {"name": {"type": "string", "description": "short-english-name"},
       "when_to_use": {"type": "string"}, "instructions": {"type": "string"}},
      ["name", "when_to_use", "instructions"])
def create_skill(name, when_to_use, instructions):
    safe = render.slug(name).lower()
    path = config.CUSTOM_SKILLS_DIR / f"{safe}.md"
    path.write_text(f"# {name}\nWhen to use: {when_to_use}\n\n{instructions}\n", encoding="utf-8")
    return {"created": f"skill:{safe}"}


def custom_skills():
    out = {}
    for p in sorted(config.CUSTOM_SKILLS_DIR.glob("*.md")):
        text = p.read_text(encoding="utf-8")
        when = next((ln[len("When to use:"):].strip() for ln in text.splitlines() if ln.startswith("When to use:")), "")
        out[p.stem] = {"when": when, "instructions": text}
    return out


@tool("store_profile", "Read the store profile: name, currency, payment methods, policies, saved notes.")
def store_profile():
    prof = config.load_profile()
    for m in prof.get("payment_methods", []):
        if m.get("account_number"):
            m["account_number"] = "****" + str(m["account_number"])[-4:]
    return prof
