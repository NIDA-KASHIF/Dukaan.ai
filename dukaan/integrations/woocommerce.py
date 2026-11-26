"""WooCommerce (WordPress) REST API v3.

Setup: WordPress admin > WooCommerce > Settings > Advanced > REST API > Add key >
Permissions: Read/Write > copy the Consumer key and Consumer secret. Your site must use https.
"""
import html

import requests

from .. import config

NAME = "WooCommerce"


class WooError(RuntimeError):
    pass


def enabled():
    return bool(config.WOO_URL and config.WOO_KEY and config.WOO_SECRET)


def _req(method, path, body=None, params=None):
    if not enabled():
        raise WooError("WooCommerce is not connected. Add WOO_URL, WOO_KEY and WOO_SECRET to .env")
    base = config.WOO_URL.rstrip("/") + "/wp-json/wc/v3"
    r = requests.request(method, base + path, auth=(config.WOO_KEY, config.WOO_SECRET),
                         json=body, params=params, timeout=60)
    if r.status_code >= 400:
        raise WooError(f"WooCommerce {method} {path} -> {r.status_code}: {r.text[:400]}")
    return r.json()


def _html(text):
    return "".join(f"<p>{html.escape(line)}</p>" for line in (text or "").split("\n") if line.strip())


def status():
    _req("GET", "/products", params={"per_page": 1})
    return {"connected": True, "platform": NAME, "url": config.WOO_URL}


def list_products(limit=50):
    return [{"id": p["id"], "name": p["name"], "slug": p["slug"], "status": p["status"], "price": p["price"],
             "url": p.get("permalink"), "virtual": p.get("virtual"),
             "description": (p.get("short_description") or p.get("description") or "")[:300]}
            for p in _req("GET", "/products", params={"per_page": min(limit, 100)})]


def create_product(name, price, description, kind="digital", pdf_path=None, image_paths=(), seo_keywords=(),
                   stock=None):
    physical = kind == "physical"
    first = (description or "").strip().split("\n")[0]
    body = {"name": name, "type": "simple", "status": "publish", "regular_price": f"{float(price):g}",
            "description": _html(description), "short_description": _html(first),
            "virtual": not physical, "downloadable": not physical,
            "tags": [{"name": k} for k in list(seo_keywords)[:20]]}
    if physical and stock is not None:
        body.update(manage_stock=True, stock_quantity=int(stock))
    p = _req("POST", "/products", body)
    note = ("Add product photos in WordPress." if physical else
            "Add images and (optionally) the downloadable file in WordPress. Dukaan AI delivers the PDF on WhatsApp.")
    return {"id": p["id"], "url": p.get("permalink"), "platform": NAME, "kind": kind, "note": note}


def create_digital_product(name, price, description, pdf_path=None, image_paths=(), seo_keywords=()):
    return create_product(name, price, description, "digital", pdf_path, image_paths, seo_keywords)


def update_product(product_id, name=None, description=None, price=None):
    body = {}
    if name:
        body["name"] = name
    if description:
        body["description"] = _html(description)
    if price is not None:
        body["regular_price"] = f"{float(price):g}"
    _req("PUT", f"/products/{product_id}", body)
    return {"id": product_id, "updated": True}


def list_orders(limit=20):
    return [{"number": o["number"], "created": o["date_created"], "status": o["status"],
             "total": f'{o["total"]} {o["currency"]}', "buyer": (o.get("billing") or {}).get("email"),
             "items": [li["name"] for li in o.get("line_items", [])]}
            for o in _req("GET", "/orders", params={"per_page": min(limit, 100)})]
