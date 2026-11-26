"""Owner dashboard.  Run:  streamlit run dashboard.py"""
import json
from pathlib import Path

import streamlit as st

from dukaan import agent, config, db
from dukaan.integrations import manual, store, whatsapp
from dukaan.llm import NoProviderError
from dukaan.skills import agents, tools

st.set_page_config(page_title="Dukaan AI", page_icon="🛍️", layout="wide")
st.title("🛍️ Dukaan AI")
st.caption("Your AI store manager — products, your online store (Wix, Shopify, WooCommerce or any platform), listings, marketing and WhatsApp sales.")

with st.sidebar:
    st.subheader("Connections")
    prov = config.configured_providers()
    st.write(("✅ AI: " + ", ".join(prov)) if prov else "❌ AI: add a free key in .env")
    plat = store.current()
    st.write(f"🏬 Store: {plat.NAME}" + ("" if plat is not manual else " — listings saved to paste"))
    st.write("✅ WhatsApp connected" if whatsapp.enabled() else "⚪ WhatsApp not connected")
    st.write("🟢 Auto-deliver ON" if config.AUTO_DELIVER else "🛡️ Owner approves each delivery")
    pend = db.pending_approvals()
    st.metric("Waiting for approval", len(pend))

tab_chat, tab_appr, tab_orders, tab_products, tab_skills, tab_settings = st.tabs(
    ["💬 Manager", "✅ Approvals", "🧾 Orders", "📦 Products", "🧠 Skills", "⚙️ Store settings"])

# ------------------------------------------------------------------ chat
with tab_chat:
    st.write("Ask anything: *Make a 30-day Ramadan planner in Urdu and list it on my website*, "
             "*Improve my product descriptions*, *Write this week's Instagram posts* ...")
    for h in db.history("owner", 30):
        with st.chat_message(h["role"]):
            st.markdown(h["content"])
    prompt = st.chat_input("Message your store manager")
    if prompt:
        with st.chat_message("user"):
            st.markdown(prompt)
        hist = db.history("owner")
        db.add_message("owner", "user", prompt)
        with st.chat_message("assistant"):
            with st.spinner("Working on it..."):
                try:
                    reply = agents.manager().run(prompt, hist)
                except NoProviderError as e:
                    reply = f"⚠️ {e}"
            st.markdown(reply)
        db.add_message("owner", "assistant", reply)
        st.rerun()
    if st.button("Start a new conversation"):
        db.clear_history("owner")
        st.rerun()

# ------------------------------------------------------------------ approvals
with tab_appr:
    items = db.pending_approvals()
    if not items:
        st.info("Nothing is waiting. When the AI wants to publish on your store or send files, it will appear here.")
    for a in items:
        with st.container(border=True):
            st.markdown(f"**#{a['id']} · {a['kind']}**")
            st.text(a["summary"])
            c1, c2 = st.columns(2)
            if c1.button("✅ Approve", key=f"ok{a['id']}"):
                st.success(agent.run_approved(a["id"]))
                st.rerun()
            if c2.button("✖ Reject", key=f"no{a['id']}"):
                st.warning(agent.reject(a["id"]))
                st.rerun()

# ------------------------------------------------------------------ orders
with tab_orders:
    orders = db.list_orders()
    if not orders:
        st.info("No WhatsApp orders yet.")
    for o in orders:
        with st.expander(f"#{o['id']} · {o['customer_name'] or o['customer']} · {o['total']:g} {o['currency']} · {o['status']}"):
            st.write("Items:", ", ".join(i["name"] for i in o["items"]))
            pay = o["payment"]
            if pay:
                for c in pay.get("checks", []):
                    st.write("✔", c)
                for p in pay.get("problems", []):
                    st.write("✖", p)
            if o["status"] != "delivered" and st.button("Send files now", key=f"d{o['id']}"):
                st.write(tools.deliver(o["id"]))

# ------------------------------------------------------------------ products
with tab_products:
    st.subheader("Products sold on WhatsApp")
    for p in db.list_products(active_only=False):
        with st.expander(f"#{p['id']} {p['name']} — {p['price']:g} {p['currency']}" + ("" if p["active"] else " (hidden)")):
            name = st.text_input("Name", p["name"], key=f"n{p['id']}")
            price = st.number_input("Price", value=float(p["price"]), key=f"p{p['id']}")
            desc = st.text_area("Description", p["description"], key=f"ds{p['id']}")
            files = st.text_area("Files (one path per line)", "\n".join(p["files"]), key=f"f{p['id']}")
            active = st.checkbox("For sale", bool(p["active"]), key=f"a{p['id']}")
            if st.button("Save", key=f"s{p['id']}"):
                db.update_product(p["id"], name=name, price=price, description=desc,
                                  files=[x.strip() for x in files.splitlines() if x.strip()], active=int(active))
                st.success("Saved")
    st.subheader("Add a product")
    with st.form("add"):
        n = st.text_input("Name")
        pr = st.number_input("Price", min_value=0.0, step=100.0)
        d = st.text_area("Description")
        up = st.file_uploader("PDF file(s)", type=["pdf", "zip", "png", "jpg"], accept_multiple_files=True)
        made = [str(x) for x in sorted(config.PRODUCTS_DIR.glob("*.pdf"))]
        chosen = st.multiselect("…or pick PDFs the AI made", made)
        if st.form_submit_button("Add product") and n:
            paths = list(chosen)
            for f in up or []:
                dest = config.PRODUCTS_DIR / f.name
                dest.write_bytes(f.getvalue())
                paths.append(str(dest))
            db.add_product(n, pr, config.load_profile().get("currency", "PKR"), d, paths)
            st.success("Added")
    if store.current() is manual:
        st.subheader("Ready-to-paste listings")
        for f in manual.listing_files():
            with st.expander(Path(f).name):
                st.code(Path(f).read_text(encoding="utf-8"))
    st.subheader("Files made by the AI")
    for pdf in sorted(config.PRODUCTS_DIR.glob("*.pdf")):
        c1, c2 = st.columns([3, 1])
        c1.write(pdf.name)
        c2.download_button("Download", pdf.read_bytes(), pdf.name, key=f"dl{pdf.name}")

# ------------------------------------------------------------------ skills
with tab_skills:
    st.write("Built-in agents:")
    for k, v in agents.SPECIALISTS.items():
        st.markdown(f"- **{k}** — {v['about']}")
    st.write("Skills the AI taught itself (or you added):")
    sk = tools.custom_skills()
    for k, v in sk.items():
        with st.expander(f"skill:{k}"):
            st.code(v["instructions"])
            if st.button("Delete", key=f"del{k}"):
                (config.CUSTOM_SKILLS_DIR / f"{k}.md").unlink(missing_ok=True)
                st.rerun()
    with st.form("newskill"):
        st.write("Teach a new skill in your own words")
        sn = st.text_input("Name (e.g. eid-card-maker)")
        sw = st.text_input("When to use it")
        si = st.text_area("Instructions (step by step)")
        if st.form_submit_button("Save skill") and sn and si:
            tools.create_skill.fn(sn, sw, si)
            st.success("Saved")

# ------------------------------------------------------------------ settings
with tab_settings:
    prof = config.load_profile()
    st.write("These details are used by the AI when it talks to customers and makes products.")
    prof["store_name"] = st.text_input("Store name", prof["store_name"])
    prof["website"] = st.text_input("Website", prof.get("website", ""))
    prof["currency"] = st.text_input("Currency", prof["currency"])
    prof["about"] = st.text_area("What you sell", prof["about"])
    prof["tone"] = st.text_input("Tone with customers", prof["tone"])
    prof["policies"] = st.text_area("Policies (delivery, refunds, discounts)", prof["policies"])
    pm = st.text_area("Payment methods (JSON list)", json.dumps(prof["payment_methods"], ensure_ascii=False, indent=2), height=200)
    if st.button("Save settings"):
        try:
            prof["payment_methods"] = json.loads(pm)
            config.save_profile(prof)
            st.success("Saved")
        except json.JSONDecodeError as e:
            st.error(f"Payment methods are not valid JSON: {e}")
    st.caption(f"Data folder: {Path(config.DATA).resolve()}")
