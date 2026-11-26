"""The team: one Manager agent who runs the store, specialist agents it can call,
and the Sales agent who talks to customers on WhatsApp."""
import json

from .. import config, db
from ..agent import Agent, tool
from ..pdfgen.pages import PAGE_TYPES_HELP
from ..integrations import store
from . import tools as T

LANG_RULE = ("Always reply in the same language the person writes in (Urdu script, Roman Urdu or English). "
             "Keep replies short and clear; use bullet points for lists.")

# ---------------------------------------------------------------- specialists
SPECIALISTS = {
    "product_designer": {
        "about": "Designs and builds printable PDF products: planners, journals, trackers, kids worksheets, "
                 "coloring books, flashcards. Give it the idea, audience, language, size and page count.",
        "system": f"""You are a senior digital-product designer (printable PDFs) for shops (Etsy, Shopify, Wix, WooCommerce, Gumroad...).
Turn the owner's idea into a complete, sellable product and BUILD it with the build_printable tool.
How you work:
1. Decide the audience, the promise (what problem it solves), title (and a short English title_en for the file name),
   subtitle, language (en / ur / ar), size (A4 default, A5 for journals), and a page plan.
2. Best sellers have: a cover, a how-to-use/intro section, varied useful pages, enough quantity
   (e.g. 30 daily pages, 12 monthly pages, 20+ coloring pages), and section dividers.
3. Write real, specific content: prompts/questions, checklist items, habits, quotes (no fake quotes from real people;
   Quran/hadith only if you are sure of the wording and reference).
4. Call build_printable ONCE with the full spec. Then report: file paths, page count, and 3 selling points.
{PAGE_TYPES_HELP}
{LANG_RULE}""",
        "tools": [T.build_printable, T.list_product_files],
    },
    "listing_writer": {
        "about": "Writes product titles, descriptions, SEO tags/keywords and price suggestions for physical and digital products on any platform (Etsy, Shopify, Wix, WooCommerce, Daraz, Gumroad...).",
        "system": f"""You are an e-commerce SEO copywriter for digital products on any platform (Etsy, Shopify, Wix, WooCommerce, Daraz, Gumroad, Payhip...). Follow the target platform's limits.
For each product give:
- Title (max 140 chars, main keyword first, no keyword stuffing)
- Description: hook line, what's included (bullets), who it is for, how it works (instant download / PDF on WhatsApp),
  for DIGITAL products: print sizes and a note that it is a digital file and nothing is shipped;
  for PHYSICAL products: size/material/colour as the owner described them (never invent), delivery time and charges
- Tags: 13 for Etsy (each max 20 chars); for other platforms 10-15 keyword phrases buyers search
- Suggested price with a short reason (compare to typical market prices; never invent competitor names or numbers you don't know)
Only claim features the product really has. {LANG_RULE}""",
        "tools": [T.catalog_list, T.list_product_files, T.store_profile],
    },
    "marketing": {
        "about": "Social media marketing: captions with hashtags for Instagram/TikTok/Facebook/Pinterest, "
                 "reel/video scripts, WhatsApp broadcast messages, 7- or 30-day content calendars, offers.",
        "system": f"""You are a social media marketer for a small digital-products shop in Pakistan and abroad.
Write ready-to-post content: captions with hashtags per platform, short video scripts with scene + voiceover lines,
WhatsApp status/broadcast text, content calendars with dates and post types, and simple offers.
Use the store's real products and prices (call catalog_list / store_profile). Never invent reviews, sales numbers or awards.
{LANG_RULE}""",
        "tools": [T.catalog_list, T.store_profile],
    },
    "store_growth": {
        "about": "Audits the online store and orders, finds what to improve (titles, descriptions, missing products, prices), "
                 "and proposes updates (each update needs owner approval).",
        "system": f"""You are a growth manager for an online digital-products store (Wix, Shopify, WooCommerce or any platform). Goal: make it the best store in its niche.
Check store_status, then read the store products, store orders and the WhatsApp orders. Then:
1. List the top problems (weak titles, short descriptions, missing SEO, products without images, gaps in the range).
2. Suggest 3-5 new product ideas based on what sells.
3. For concrete fixes, call store_update_product with the improved text (it waits for owner approval).
Be specific and honest; if the store is not connected, say what to connect. {LANG_RULE}""",
        "tools": [T.store_status, T.store_list_products, T.store_list_orders, T.orders_list, T.catalog_list,
                  T.store_update_product],
    },
}


def run_specialist(name, task):
    if name.startswith("skill:"):
        skills = T.custom_skills()
        key = name.split(":", 1)[1]
        if key not in skills:
            return {"error": f"No custom skill named {key}. Available: {list(skills)}"}
        agent = Agent(name, skills[key]["instructions"] + "\n\n" + LANG_RULE,
                      [T.build_printable, T.catalog_list, T.store_profile, T.store_list_products])
        return agent.run(task)
    spec = SPECIALISTS.get(name)
    if not spec:
        return {"error": f"Unknown agent {name}. Use one of {list(SPECIALISTS)} or skill:<name>"}
    return Agent(name, spec["system"], spec["tools"]).run(task)


@tool("delegate",
      "Give a task to a specialist agent and get its result. Agents: product_designer, listing_writer, "
      "marketing, store_growth, or a custom skill as 'skill:<name>'.",
      {"agent": {"type": "string"}, "task": {"type": "string", "description": "Full task with all details it needs"}},
      ["agent", "task"])
def delegate(agent, task):
    return run_specialist(agent, task)


# ---------------------------------------------------------------- manager
def manager_system():
    prof = config.load_profile()
    skills = T.custom_skills()
    team = "\n".join(f"- {k}: {v['about']}" for k, v in SPECIALISTS.items())
    team += "".join(f"\n- skill:{k}: {v['when']}" for k, v in skills.items())
    notes = "\n".join(f"- {n}" for n in prof.get("notes", [])[-25:]) or "- (none yet)"
    return f"""You are Dukaan AI, the manager of the online store "{prof.get('store_name')}".
You run the whole store for the owner: physical and digital products, website, listings, marketing, orders,
shipping and customers.

About the store: {prof.get('about')}
Currency: {prof.get('currency')}. Website: {prof.get('website') or 'not set'}.
Online store platform: {store.name()} (in manual mode, publishing saves a ready-to-paste listing for the owner).
Things the owner told you before:
{notes}

Your team (use the delegate tool):
{team}

How you work:
- Understand what the owner wants, plan the steps, and do them yourself with tools and your team.
  Example "make and sell a Ramadan planner": product_designer builds the PDF -> listing_writer writes the listing ->
  store_publish_product (owner approves) -> catalog_add happens automatically -> marketing writes the posts.
- Physical products: add them with catalog_add(kind='physical', stock, photos) or store_publish_product(kind='physical').
  When the owner says a parcel was sent, call mark_shipped (courier + tracking); when it arrives, mark_delivered.
  Keep stock right with update_stock.
- If the owner asks for a kind of work no agent covers, use create_skill to teach yourself, then delegate to it.
- Anything that changes the live website or sends files waits for the owner's approval. Never pretend something
  was published before it is approved and done. Tell the owner the approval number.
- When the owner tells you a lasting preference or fact, save it with remember.
- Autopilot runs in the background: bank SMS matching (if the owner pastes a bank SMS, call record_bank_sms),
  reminders to customers who did not pay, customer memory and upsell, and the morning brief (todays_brief).
- Be honest about limits: you cannot see the bank account; you cannot post to Instagram/TikTok yourself
  (you write the posts and the owner posts them).
{LANG_RULE}"""


MANAGER_TOOLS = [delegate, T.mark_shipped, T.mark_delivered, T.update_stock, T.build_printable, T.list_product_files, T.catalog_list, T.catalog_add,
                 T.store_status, T.store_list_products, T.store_list_orders, T.store_publish_product, T.store_update_product,
                 T.orders_list, T.approvals_list, T.deliver_order, T.remember, T.create_skill, T.store_profile,
                 T.todays_brief, T.customers_list, T.record_bank_sms]


def manager():
    return Agent("manager", manager_system(), MANAGER_TOOLS, max_steps=14)


# ---------------------------------------------------------------- sales (customers)
_current_customer = {"wa": None, "name": ""}


@tool("show_catalog", "Show the products customers can buy: id, name, price, type (digital/physical) and stock.")
def show_catalog():
    out = []
    for p in db.list_products():
        item = {"id": p["id"], "name": p["name"], "price": p["price"], "currency": p["currency"],
                "type": "digital download (PDF on WhatsApp)" if p["kind"] == "digital" else "physical (delivered by courier)",
                "description": p["description"][:400]}
        if p["kind"] == "physical" and p["stock"] is not None:
            item["in_stock"] = p["stock"]
        out.append(item)
    return out


@tool("shipping_info", "Delivery charges, delivery time, cash-on-delivery and courier details for physical products.")
def shipping_info():
    return config.load_profile().get("shipping") or {}


@tool("start_order",
      "Create an order once the customer clearly chose product(s). For PHYSICAL products you must first collect the "
      "customer's full name, phone number, full address and city, and ask how they will pay: 'bank' (transfer) or "
      "'cod' (cash on delivery, only if allowed and only when the order has no digital items).",
      {"product_ids": {"type": "array", "items": {"type": "integer"}},
       "quantities": {"type": "array", "items": {"type": "integer"}, "description": "Same order as product_ids; default 1"},
       "payment_method": {"type": "string", "enum": ["bank", "cod"]},
       "name": {"type": "string"}, "phone": {"type": "string"}, "address": {"type": "string"},
       "city": {"type": "string"}},
      ["product_ids"])
def start_order(product_ids, quantities=None, payment_method="bank", name="", phone="", address="", city=""):
    prof = config.load_profile()
    ship_cfg = prof.get("shipping") or {}
    currency = prof.get("currency", "PKR")
    quantities = list(quantities or [])
    items, subtotal, physical, digital = [], 0.0, False, False
    for n, pid in enumerate(product_ids):
        p = db.get_product(int(pid))
        if not p or not p["active"]:
            return {"error": f"Product {pid} not found"}
        qty = max(1, int(quantities[n]) if n < len(quantities) and quantities[n] else 1)
        if p["kind"] == "physical":
            physical = True
            if p["stock"] is not None and p["stock"] < qty:
                return {"error": f"Only {p['stock']} of '{p['name']}' left in stock."}
        else:
            digital, qty = True, 1
        items.append({"product_id": p["id"], "name": p["name"], "price": p["price"], "qty": qty, "kind": p["kind"]})
        subtotal += p["price"] * qty
    shipping = {}
    fee = 0.0
    if physical:
        missing = [k for k, v in {"name": name, "phone": phone, "address": address, "city": city}.items() if not str(v).strip()]
        if missing:
            return {"error": "Ask the customer for: " + ", ".join(missing) + " (needed to ship the parcel)."}
        free_over = float(ship_cfg.get("free_over") or 0)
        fee = 0.0 if (free_over and subtotal >= free_over) else float(ship_cfg.get("flat_fee") or 0)
        shipping = {"name": name, "phone": phone, "address": address, "city": city, "fee": fee}
    payment_method = "cod" if str(payment_method).lower() == "cod" else "bank"
    if payment_method == "cod":
        if not physical or digital:
            return {"error": "Cash on delivery is only for physical items. Digital files need bank payment first."}
        if not ship_cfg.get("cod", False):
            return {"error": "This store does not offer cash on delivery. Please use bank transfer."}
        fee += float(ship_cfg.get("cod_fee") or 0)
        shipping["fee"] = fee
    total = subtotal + fee
    status = "cod_pending" if payment_method == "cod" else "awaiting_payment"
    oid = db.add_order(_current_customer["wa"], name or _current_customer["name"], items, total, currency,
                       status=status, payment_method=payment_method, shipping=shipping)
    out = {"order_id": oid, "items": [f"{i['qty']} × {i['name']}" for i in items], "subtotal": subtotal,
           "delivery_charges": fee, "total": total, "currency": currency, "payment_method": payment_method}
    if payment_method == "cod":
        out["next"] = ("Read the order back (items, total, address) and ask the customer to reply CONFIRM. "
                       "When they confirm, call confirm_cod_order.")
    else:
        out["next"] = "Share payment_details and ask the customer to send the payment screenshot here."
    return out


@tool("confirm_cod_order", "Confirm a cash-on-delivery order after the customer replied CONFIRM (or clearly said yes).",
      {"order_id": {"type": "integer"}}, ["order_id"])
def confirm_cod_order(order_id):
    o = db.get_order(int(order_id))
    if not o or o["customer"] != _current_customer["wa"] or o["status"] != "cod_pending":
        return {"error": "No cash-on-delivery order waiting for confirmation."}
    return T.deliver(o["id"])


@tool("payment_details", "Get the store's bank/wallet details to share with a customer who wants to pay.")
def payment_details():
    return config.load_profile().get("payment_methods", [])


@tool("my_order_status", "Check the status of this customer's latest order, including courier tracking.")
def my_order_status():
    rows = [o for o in db.list_orders(50) if o["customer"] == _current_customer["wa"]]
    if not rows:
        return {"orders": []}
    o = rows[0]
    out = {"order_id": o["id"], "status": o["status"], "total": o["total"],
           "items": [f"{i.get('qty', 1)} × {i['name']}" for i in o["items"]]}
    f = o.get("fulfillment") or {}
    if f.get("tracking"):
        out.update(courier=f.get("courier"), tracking=f.get("tracking"), tracking_url=f.get("tracking_url"))
    return out


def sales_system():
    prof = config.load_profile()
    return f"""You are the friendly sales assistant of "{prof.get('store_name')}" on WhatsApp.
About: {prof.get('about')}
Policies: {prof.get('policies')}
Tone: {prof.get('tone')}

Your job: answer questions about the products (show_catalog), help the customer choose, and create the order.
- DIGITAL products: start_order -> share payment_details -> ask for the payment screenshot here. Files are sent
  automatically after the payment is confirmed. Never send or promise a file before that.
- PHYSICAL products: check shipping_info (charges, delivery time, cash on delivery). Before start_order, collect
  full name, phone, full address and city, and ask: bank transfer or cash on delivery (if offered).
  Bank: share payment_details and ask for the screenshot. Cash on delivery: read the order back with the total
  and ask them to reply CONFIRM, then call confirm_cod_order. Tracking is shared when the parcel ships.
- Orders can mix both; cash on delivery is only for orders with physical items only.
Rules:
- Use only real products and prices from show_catalog. No discounts unless the policies allow them.
- If they ask something you cannot answer or want to talk to a person, say the owner will reply soon.
- Never share private details about other customers or the owner.
{LANG_RULE}"""


def sales_agent(customer_wa, customer_name=""):
    _current_customer["wa"], _current_customer["name"] = customer_wa, customer_name
    return Agent("sales", sales_system(), [show_catalog, shipping_info, start_order, confirm_cod_order,
                                           payment_details, my_order_status],
                 max_steps=6, temperature=0.3)
