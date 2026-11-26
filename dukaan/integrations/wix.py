"""Wix Stores REST API (works with both Catalog V1 and Catalog V3 stores).

Auth: an account-level API key in the Authorization header, plus the wix-site-id header.
Docs: https://dev.wix.com/docs/api-reference/articles/rest-authentication/rest-api-authentication
"""
import mimetypes
from pathlib import Path

import requests

from .. import config

NAME = "Wix"
BASE = "https://www.wixapis.com"
_version_cache = {}


class WixError(RuntimeError):
    pass


def enabled():
    return bool(config.WIX_API_KEY and config.WIX_SITE_ID)


def _headers():
    if not enabled():
        raise WixError("Wix is not connected. Add WIX_API_KEY and WIX_SITE_ID to .env")
    return {"Authorization": config.WIX_API_KEY, "wix-site-id": config.WIX_SITE_ID,
            "Content-Type": "application/json"}


def _req(method, path, body=None, params=None):
    r = requests.request(method, BASE + path, headers=_headers(), json=body, params=params, timeout=60)
    if r.status_code >= 400:
        raise WixError(f"Wix {method} {path} -> {r.status_code}: {r.text[:500]}")
    return r.json() if r.text else {}


def catalog_version():
    """'V1_CATALOG' or 'V3_CATALOG'."""
    if "v" not in _version_cache:
        _version_cache["v"] = _req("GET", "/stores/v3/provision/version").get("catalogVersion", "V1_CATALOG")
    return _version_cache["v"]


def status():
    return {"connected": True, "platform": NAME, "catalog": catalog_version()}


# ---------------- products ----------------
def list_products(limit=100):
    if catalog_version() == "V3_CATALOG":
        data = _req("POST", "/stores/v3/products/query",
                    {"fields": ["URL", "CURRENCY"], "query": {"cursorPaging": {"limit": min(limit, 100)}}})
        out = []
        for p in data.get("products", []):
            out.append({
                "id": p.get("id"), "name": p.get("name"), "slug": p.get("slug"),
                "visible": p.get("visible"), "type": p.get("productType"),
                "price": (p.get("actualPriceRange") or {}).get("minValue", {}).get("amount"),
                "description": (p.get("plainDescription") or "")[:300],
                "seo_tags": len(((p.get("seoData") or {}).get("tags")) or []),
                "revision": p.get("revision"),
            })
        return out
    data = _req("POST", "/stores/v1/products/query", {"query": {"paging": {"limit": min(limit, 100)}}})
    return [{
        "id": p.get("id"), "name": p.get("name"), "slug": p.get("slug"), "visible": p.get("visible"),
        "type": p.get("productType"), "price": (p.get("priceData") or {}).get("price"),
        "description": (p.get("description") or "")[:300],
    } for p in data.get("products", [])]


def upload_file(path):
    """Upload a local file (PDF or image) to the Wix Media Manager. Returns the file dict (id, url)."""
    path = Path(path)
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    up = _req("POST", "/site-media/v1/files/generate-upload-url", {"mimeType": mime, "fileName": path.name})
    r = requests.put(up["uploadUrl"], params={"filename": path.name}, data=path.read_bytes(),
                     headers={"Content-Type": mime}, timeout=180)
    if r.status_code >= 400:
        raise WixError(f"Upload failed: {r.status_code} {r.text[:300]}")
    return r.json().get("file", {})


def create_digital_product(name, price, description, pdf_path=None, image_paths=(), seo_keywords=()):
    """Create a digital product. In V3 the PDF is attached so Wix can sell it directly."""
    images = [upload_file(p)["url"] for p in image_paths if p and Path(p).exists()][:3]
    if catalog_version() == "V3_CATALOG":
        variant = {"price": {"actualPrice": {"amount": f"{float(price):g}"}}, "visible": True,
                   "inventoryItem": {"inStock": True}}
        if pdf_path and Path(pdf_path).exists():
            variant["digitalProperties"] = {"digitalFile": {"id": upload_file(pdf_path)["id"]}}
        product = {"name": name, "productType": "DIGITAL", "plainDescription": description,
                   "variantsInfo": {"variants": [variant]}}
        if images:
            product["media"] = {"itemsInfo": {"items": [{"url": u, "altText": name} for u in images]}}
        if seo_keywords:
            product["seoData"] = {"tags": [{"type": "meta", "props": {"name": "keywords",
                                                                      "content": ", ".join(seo_keywords)}}]}
        res = _req("POST", "/stores/v3/products-with-inventory", {"product": product, "fields": ["URL"]})
        p = res.get("product", {})
        return {"id": p.get("id"), "name": p.get("name"), "url": p.get("url"),
                "sellable_on_wix": "digitalProperties" in variant,
                "inventory_error": (res.get("inventoryResults") or {}).get("error")}
    # Catalog V1: description is HTML. The PDF is delivered on WhatsApp by this app.
    html = "".join(f"<p>{line}</p>" for line in description.split("\n") if line.strip())
    res = _req("POST", "/stores/v1/products", {"product": {
        "name": name, "productType": "digital", "description": html, "visible": True,
        "priceData": {"price": float(price)}}})
    p = res.get("product", {})
    if images and p.get("id"):
        _req("POST", f"/stores/v1/products/{p['id']}/media", {"media": [{"url": u} for u in images]})
    return {"id": p.get("id"), "name": p.get("name"),
            "note": "Catalog V1: attach the PDF in the Wix dashboard if you also want Wix to deliver it."}


def update_product(product_id, name=None, description=None, price=None):
    if catalog_version() == "V3_CATALOG":
        current = _req("GET", f"/stores/v3/products/{product_id}").get("product", {})
        patch = {"id": product_id, "revision": current.get("revision")}
        if name:
            patch["name"] = name
        if description:
            patch["plainDescription"] = description
        res = _req("PATCH", f"/stores/v3/products/{product_id}", {"product": patch})
        note = "Price changes on V3 are per variant; change price in the Wix dashboard." if price else ""
        return {"id": product_id, "updated": True, "note": note, "revision": res.get("product", {}).get("revision")}
    patch = {}
    if name:
        patch["name"] = name
    if description:
        patch["description"] = "".join(f"<p>{line}</p>" for line in description.split("\n") if line.strip())
    if price is not None:
        patch["priceData"] = {"price": float(price)}
    _req("PATCH", f"/stores/v1/products/{product_id}", {"product": patch})
    return {"id": product_id, "updated": True}


def list_orders(limit=20):
    data = _req("POST", "/ecom/v1/orders/search",
                {"search": {"cursorPaging": {"limit": min(limit, 100)},
                            "sort": [{"fieldName": "createdDate", "order": "DESC"}]}})
    out = []
    for o in data.get("orders", []):
        out.append({
            "number": o.get("number"), "created": o.get("createdDate"),
            "status": o.get("status"), "payment": o.get("paymentStatus"),
            "total": ((o.get("priceSummary") or {}).get("total") or {}).get("formattedAmount"),
            "buyer": (o.get("buyerInfo") or {}).get("email"),
            "items": [((li.get("productName") or {}).get("original")) for li in o.get("lineItems", [])],
        })
    return out
