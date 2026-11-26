"""Shopify Admin GraphQL API.

Setup: Shopify admin > Settings > Apps and sales channels > Develop apps > Create an app >
Admin API scopes: write_products, read_products, read_orders > Install > copy the Admin API access token.
"""
import html

import requests

from .. import config

NAME = "Shopify"


class ShopifyError(RuntimeError):
    pass


def enabled():
    return bool(config.SHOPIFY_STORE and config.SHOPIFY_TOKEN)


def _gql(query, variables=None):
    if not enabled():
        raise ShopifyError("Shopify is not connected. Add SHOPIFY_STORE and SHOPIFY_TOKEN to .env")
    shop = config.SHOPIFY_STORE.replace("https://", "").replace("http://", "").strip("/")
    if "." not in shop:
        shop += ".myshopify.com"
    r = requests.post(f"https://{shop}/admin/api/{config.SHOPIFY_API_VERSION}/graphql.json",
                      headers={"X-Shopify-Access-Token": config.SHOPIFY_TOKEN, "Content-Type": "application/json"},
                      json={"query": query, "variables": variables or {}}, timeout=60)
    if r.status_code >= 400:
        raise ShopifyError(f"Shopify {r.status_code}: {r.text[:400]}")
    data = r.json()
    if data.get("errors"):
        raise ShopifyError(str(data["errors"])[:500])
    return data["data"]


def _user_errors(block):
    errs = (block or {}).get("userErrors") or []
    if errs:
        raise ShopifyError("; ".join(f"{e.get('field')}: {e.get('message')}" for e in errs))


def _html(text):
    return "".join(f"<p>{html.escape(line)}</p>" for line in (text or "").split("\n") if line.strip())


def status():
    d = _gql("{ shop { name currencyCode primaryDomain { url } } }")["shop"]
    return {"connected": True, "platform": NAME, "shop": d["name"], "currency": d["currencyCode"],
            "url": d["primaryDomain"]["url"]}


def list_products(limit=50):
    q = """query($n:Int!){ products(first:$n, sortKey:UPDATED_AT, reverse:true){ nodes{
      id title handle status description tags onlineStoreUrl
      variants(first:1){ nodes{ price } } } } }"""
    return [{"id": p["id"], "name": p["title"], "slug": p["handle"], "status": p["status"],
             "price": (p["variants"]["nodes"] or [{}])[0].get("price"), "tags": p["tags"],
             "url": p.get("onlineStoreUrl"), "description": (p["description"] or "")[:300]}
            for p in _gql(q, {"n": min(limit, 100)})["products"]["nodes"]]


def create_digital_product(name, price, description, pdf_path=None, image_paths=(), seo_keywords=()):
    q = """mutation($p:ProductCreateInput!){ productCreate(product:$p){
      product{ id handle variants(first:1){ nodes{ id } } } userErrors{ field message } } }"""
    res = _gql(q, {"p": {"title": name, "descriptionHtml": _html(description), "status": "ACTIVE",
                         "productType": "Digital download", "tags": list(seo_keywords)[:250]}})["productCreate"]
    _user_errors(res)
    prod = res["product"]
    vid = prod["variants"]["nodes"][0]["id"]
    q2 = """mutation($id:ID!, $v:[ProductVariantsBulkInput!]!){ productVariantsBulkUpdate(productId:$id, variants:$v){
      userErrors{ field message } } }"""
    _user_errors(_gql(q2, {"id": prod["id"], "v": [{"id": vid, "price": f"{float(price):.2f}",
                                                      "inventoryItem": {"requiresShipping": False}}]})
                 ["productVariantsBulkUpdate"])
    return {"id": prod["id"], "handle": prod["handle"], "platform": NAME,
            "note": "Add product images in Shopify admin. The PDF is delivered on WhatsApp by Dukaan AI "
                    "(or attach it with Shopify's free Digital Downloads app)."}


def update_product(product_id, name=None, description=None, price=None):
    if name or description:
        p = {"id": product_id}
        if name:
            p["title"] = name
        if description:
            p["descriptionHtml"] = _html(description)
        q = "mutation($p:ProductUpdateInput!){ productUpdate(product:$p){ userErrors{ field message } } }"
        _user_errors(_gql(q, {"p": p})["productUpdate"])
    if price is not None:
        q = "query($id:ID!){ product(id:$id){ variants(first:100){ nodes{ id } } } }"
        vids = [v["id"] for v in _gql(q, {"id": product_id})["product"]["variants"]["nodes"]]
        q2 = """mutation($id:ID!, $v:[ProductVariantsBulkInput!]!){ productVariantsBulkUpdate(productId:$id, variants:$v){
          userErrors{ field message } } }"""
        _user_errors(_gql(q2, {"id": product_id, "v": [{"id": v, "price": f"{float(price):.2f}"} for v in vids]})
                     ["productVariantsBulkUpdate"])
    return {"id": product_id, "updated": True}


def list_orders(limit=20):
    q = """query($n:Int!){ orders(first:$n, sortKey:CREATED_AT, reverse:true){ nodes{
      name createdAt displayFinancialStatus displayFulfillmentStatus email
      totalPriceSet{ shopMoney{ amount currencyCode } } lineItems(first:10){ nodes{ title } } } } }"""
    return [{"number": o["name"], "created": o["createdAt"], "payment": o["displayFinancialStatus"],
             "status": o["displayFulfillmentStatus"], "buyer": o.get("email"),
             "total": f'{o["totalPriceSet"]["shopMoney"]["amount"]} {o["totalPriceSet"]["shopMoney"]["currencyCode"]}',
             "items": [li["title"] for li in o["lineItems"]["nodes"]]}
            for o in _gql(q, {"n": min(limit, 100)})["orders"]["nodes"]]
