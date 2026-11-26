"""All tools the agents can use."""
import json
from pathlib import Path

from .. import autopilot, config, db
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
    return [{"id": p["id"], "name": p["name"], "kind": p["kind"], "price": p["price"], "currency": p["currency"],
             "stock": "unlimited" if p["stock"] is None else p["stock"], "description": p["description"][:200],
             "files": p["files"], "store_id": p["wix_id"]} for p in db.list_products()]


@tool("catalog_add",
      "Add a product to the WhatsApp catalog so customers can buy it. kind='digital' needs pdf_paths (sent after "
      "payment); kind='physical' is shipped (give stock, or leave it empty for unlimited).",
      {"name": {"type": "string"}, "price": {"type": "number"}, "description": {"type": "string"},
       "kind": {"type": "string", "enum": ["digital", "physical"]},
       "pdf_paths": {"type": "array", "items": {"type": "string"}},
       "stock": {"type": "integer"}, "image_paths": {"type": "array", "items": {"type": "string"}}},
      ["name", "price"])
def catalog_add(name, price, description="", kind="digital", pdf_paths=None, stock=None, image_paths=None):
    pdf_paths = pdf_paths or []
    missing = [p for p in pdf_paths + (image_paths or []) if not Path(p).exists()]
    if missing:
        return {"error": f"These files do not exist: {missing}"}
    if kind == "digital" and not pdf_paths:
        return {"error": "A digital product needs at least one file in pdf_paths."}
    pid = db.add_product(name, price, config.load_profile().get("currency", "PKR"), description, pdf_paths,
                         kind=kind, stock=stock, images=image_paths or [])
    return {"added": True, "product_id": pid, "kind": kind}


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
    kind = a.get("kind", "digital")
    extra = f"• Stock: {a.get('stock', 'not tracked')}\n" if kind == "physical" else ""
    return (f"Publish NEW {kind} product on {store.name()}:\n• Name: {a.get('name')}\n• Price: {a.get('price')}\n{extra}"
            f"• PDF: {Path(a.get('pdf_path') or '-').name}\n• Description:\n{(a.get('description') or '')[:700]}")


@tool("store_publish_product",
      "Create a new product on the online store (and add it to the WhatsApp catalog). kind='digital' (PDF) or "
      "'physical' (shipped; give stock and photos). In manual mode it saves a ready-to-paste listing file.",
      {"name": {"type": "string"}, "price": {"type": "number"},
       "kind": {"type": "string", "enum": ["digital", "physical"]}, "stock": {"type": "integer"},
       "description": {"type": "string", "description": "Full product description, plain text with line breaks"},
       "pdf_path": {"type": "string"}, "image_paths": {"type": "array", "items": {"type": "string"}},
       "seo_keywords": {"type": "array", "items": {"type": "string"}}},
      ["name", "price", "description"], needs_approval=True, summary=_publish_summary)
def store_publish_product(name, price, description, pdf_path=None, image_paths=None, seo_keywords=None,
                          kind="digital", stock=None):
    res = store.current().create_product(name, price, description, kind=kind, pdf_path=pdf_path,
                                         image_paths=image_paths or [], seo_keywords=seo_keywords or [], stock=stock)
    files = [pdf_path] if pdf_path and Path(pdf_path).exists() else []
    if files or kind == "physical":
        db.add_product(name, price, config.load_profile().get("currency", "PKR"), description, files,
                       str(res.get("id") or ""), kind=kind, stock=stock,
                       images=[p for p in (image_paths or []) if Path(p).exists()])
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


def _qty(item):
    return int(item.get("qty") or 1)


def deliver(order_id):
    """Fulfil a paid (or COD-confirmed) order.
    Digital items: files are sent on WhatsApp at once.
    Physical items: stock goes down, the owner gets a packing slip, the customer is told it will ship."""
    import time as _t
    order = db.get_order(order_id)
    if not order:
        return {"error": "order not found"}
    ful = dict(order.get("fulfillment") or {})
    store_name = config.load_profile().get("store_name", "")
    sent, physical = [], []
    for item in order["items"]:
        p = db.get_product(item["product_id"]) or {}
        if p.get("kind") == "physical":
            physical.append(item)
            continue
        if not ful.get("digital_sent"):
            for f in p.get("files", []):
                whatsapp.send_document(order["customer"], f, caption=p.get("name", ""))
                sent.append(Path(f).name)
    ful["digital_sent"] = True
    if physical and not ful.get("stock_taken"):
        for item in physical:
            db.change_stock(item["product_id"], -_qty(item))
        ful["stock_taken"] = True
    names = [i["name"] for i in order["items"]]
    if not ful.get("counted"):
        db.touch_customer(order["customer"], order.get("customer_name") or "")
        db.add_purchase(order["customer"], order["total"], names)
        ful["counted"] = True
    cod = order.get("payment_method") == "cod"
    if physical:
        ship = order.get("shipping") or {}
        days = (config.load_profile().get("shipping") or {}).get("delivery_days", "a few days")
        lines = [("✅ Order confirmed!" if cod else "✅ Payment received, thank you!") + f" Order #{order_id}"]
        if sent:
            lines.append("Your digital files have been sent above.")
        lines.append(f"📦 Your parcel ({', '.join(f'{_qty(i)} × {i['name']}' for i in physical)}) will be packed and "
                     f"shipped soon. Delivery: {days}. You will get the tracking number here.")
        if cod:
            lines.append(f"💵 Please keep {float(order['total']):g} {order['currency']} ready for the rider.")
        whatsapp.send_text(order["customer"], "\n".join(lines))
        slip = (f"📦 PACK & SHIP order #{order_id}" + (" (COD)" if cod else " (paid)") + "\n"
                + "\n".join(f"• {_qty(i)} × {i['name']}" for i in physical)
                + f"\nTo: {ship.get('name') or order.get('customer_name')}, {ship.get('phone') or order['customer']}"
                + f"\n{ship.get('address', '')}, {ship.get('city', '')}"
                + (f"\nCollect: {float(order['total']):g} {order['currency']}" if cod else "")
                + f"\n\nWhen sent, reply: SHIPPED {order_id} <courier> <tracking no>")
        agent_notify(slip)
        db.update_order(order_id, status="to_ship", fulfillment=ful,
                        paid_at=None if cod else (order.get("paid_at") or _t.time()))
    else:
        thanks = f"✅ Thank you! Your order #{order_id} has been delivered. JazakAllah for shopping with {store_name} 🤍"
        nxt = autopilot.upsell_for(order["customer"], names)
        if nxt:
            thanks += (f"\n\nYou might also like: *{nxt['name']}* ({nxt['price']:g} {nxt['currency']}). "
                       "Just reply if you'd like it.")
        whatsapp.send_text(order["customer"], thanks)
        db.update_order(order_id, status="delivered", fulfillment=ful, paid_at=order.get("paid_at") or _t.time())
    if order["payment"].get("transaction_id"):
        db.mark_payment_ref(order["payment"]["transaction_id"], order_id)
    return {"files_sent": sent, "to_ship": [i["name"] for i in physical],
            "status": "to_ship" if physical else "delivered"}


def agent_notify(text):
    from ..agent import notify_owner
    notify_owner(text)


@tool("deliver_order", "Fulfil a paid order: send the digital files on WhatsApp and/or prepare physical items for shipping.",
      {"order_id": {"type": "integer"}}, ["order_id"], needs_approval=True,
      summary=lambda a: f"Fulfil order #{a.get('order_id')} (send files / prepare parcel)")
def deliver_order(order_id):
    return deliver(order_id)


@tool("mark_shipped", "Mark a physical order as shipped and send the customer the courier and tracking number.",
      {"order_id": {"type": "integer"}, "courier": {"type": "string"}, "tracking": {"type": "string"},
       "tracking_url": {"type": "string"}}, ["order_id", "courier", "tracking"])
def mark_shipped(order_id, courier, tracking, tracking_url=""):
    import time as _t
    order = db.get_order(int(order_id))
    if not order:
        return {"error": "order not found"}
    ful = dict(order.get("fulfillment") or {})
    ful.update(courier=courier, tracking=tracking, tracking_url=tracking_url, shipped_at=_t.time())
    db.update_order(order["id"], status="shipped", fulfillment=ful)
    msg = f"🚚 Your order #{order['id']} has been shipped with {courier}.\nTracking number: {tracking}"
    if tracking_url:
        msg += f"\nTrack it: {tracking_url}"
    if order.get("payment_method") == "cod":
        msg += f"\n💵 Please pay {float(order['total']):g} {order['currency']} to the rider."
    whatsapp.send_text(order["customer"], msg)
    return {"shipped": True, "order_id": order["id"]}


@tool("mark_delivered", "Mark a shipped physical order as delivered (and as paid, for cash on delivery).",
      {"order_id": {"type": "integer"}}, ["order_id"])
def mark_delivered(order_id):
    import time as _t
    order = db.get_order(int(order_id))
    if not order:
        return {"error": "order not found"}
    db.update_order(order["id"], status="delivered", paid_at=order.get("paid_at") or _t.time())
    store_name = config.load_profile().get("store_name", "")
    msg = f"🎉 Your order #{order['id']} has been delivered. JazakAllah for shopping with {store_name}! 🤍"
    nxt = autopilot.upsell_for(order["customer"], [i["name"] for i in order["items"]])
    if nxt:
        msg += f"\n\nYou might also like: *{nxt['name']}* ({nxt['price']:g} {nxt['currency']})."
    whatsapp.send_text(order["customer"], msg)
    return {"delivered": True}


@tool("update_stock", "Set or change the stock of a physical product in the catalog.",
      {"product_id": {"type": "integer"}, "stock": {"type": "integer", "description": "New stock count"}},
      ["product_id", "stock"])
def update_stock(product_id, stock):
    db.update_product(int(product_id), stock=int(stock))
    return {"product_id": product_id, "stock": int(stock)}


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


# ======================= autopilot =======================


@tool("todays_brief", "Get the store's daily report: yesterday's sales, unpaid orders, approvals, best seller, post idea.")
def todays_brief():
    return autopilot.build_brief()


@tool("customers_list", "List customers with what they bought and how much they spent.")
def customers_list():
    return [{"whatsapp": c["wa"], "name": c["name"], "orders": c["orders"], "spent": c["spent"],
             "bought": c["products"]} for c in db.list_customers(100)]


@tool("record_bank_sms",
      "Record a bank/wallet SMS the owner pasted (money received) and match it to a customer's order. "
      "If it matches, the order is confirmed (and delivered if bank auto-delivery is on).",
      {"sms_text": {"type": "string"}}, ["sms_text"])
def record_bank_sms(sms_text):
    return autopilot.record_bank_sms(sms_text, source="manager_chat")
