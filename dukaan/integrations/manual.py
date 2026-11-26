"""Manual mode: for any platform without an API connection here
(Etsy, Daraz, Gumroad, Payhip, Instagram shop, your own website...).

Publishing writes a complete, ready-to-paste listing file into data/listings/
and adds the product to the WhatsApp catalog. You paste it into your platform yourself.
"""
import json
import time
from pathlib import Path

from .. import config, db

NAME = "Manual (any platform)"


def enabled():
    return True


def _dir():
    d = config.DATA / "listings"
    d.mkdir(parents=True, exist_ok=True)
    return d


def status():
    return {"connected": True, "platform": NAME, "platform_name": config.STORE_PLATFORM_NAME or "your store",
            "note": "No store API connected. Listings are saved as files for you to paste."}


def list_products(limit=50):
    return [{"id": p["id"], "name": p["name"], "price": p["price"], "description": p["description"][:300]}
            for p in db.list_products()][:limit]


def create_digital_product(name, price, description, pdf_path=None, image_paths=(), seo_keywords=()):
    return create_product(name, price, description, "digital", pdf_path, image_paths, seo_keywords)


def create_product(name, price, description, kind="digital", pdf_path=None, image_paths=(), seo_keywords=(),
                   stock=None):
    stamp = time.strftime("%Y%m%d-%H%M")
    safe = "".join(c if c.isalnum() else "_" for c in name)[:50]
    path = _dir() / f"{stamp}_{safe}.md"
    cur = config.load_profile().get("currency", "")
    ship = config.load_profile().get("shipping") or {}
    kind_line = (f"**Type:** Physical (shipped) · Stock: {stock if stock is not None else 'not tracked'} · "
                 f"Delivery: {ship.get('delivery_days', '')}\n\n" if kind == "physical" else
                 "**Type:** Digital download (PDF)\n\n")
    text = (f"# {name}\n\n**Price:** {float(price):g} {cur}\n\n{kind_line}## Description\n{description}\n\n"
            f"## Tags / keywords\n{', '.join(seo_keywords) or '-'}\n\n" +
            (f"## Files\n- PDF: {pdf_path or '-'}\n" if kind != "physical" else "## Photos\n") + "".join(f"- Image: {p}\n" for p in image_paths))
    path.write_text(text, encoding="utf-8")
    return {"listing_file": str(path), "platform": NAME, "kind": kind,
            "note": f"Ready to paste into {config.STORE_PLATFORM_NAME or 'your platform'}."}


def update_product(product_id, name=None, description=None, price=None):
    fields = {k: v for k, v in {"name": name, "description": description, "price": price}.items() if v is not None}
    try:
        db.update_product(int(product_id), **fields)
    except ValueError:
        pass
    path = _dir() / f"update_{product_id}_{time.strftime('%Y%m%d-%H%M')}.json"
    path.write_text(json.dumps({"product_id": product_id, **fields}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"updated_locally": True, "listing_file": str(path),
            "note": "Paste the new text into your platform."}


def list_orders(limit=20):
    return [{"number": o["id"], "status": o["status"], "total": f"{o['total']:g} {o['currency']}",
             "buyer": o["customer_name"] or o["customer"], "items": [i["name"] for i in o["items"]],
             "channel": "WhatsApp"} for o in db.list_orders(limit)]


def listing_files():
    return [str(p) for p in sorted(_dir().glob("*"))]
