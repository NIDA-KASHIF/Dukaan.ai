# 🛍️ Dukaan AI — AI Store Manager for Wix + WhatsApp

**Dukaan AI** is an AI manager for your online store. It **designs digital products itself** (planners, journals, worksheets, coloring books), writes their listings and SEO, publishes them to your Wix website, writes your social media posts, and sells on WhatsApp: it chats with customers, takes the order, checks the payment screenshot and sends the PDF.

It runs on **free AI**: Google Gemini, Groq or OpenRouter. Each user adds their own free key.

---

## ✨ What it does

| Agent | Job |
|---|---|
| 🧑‍💼 **Manager** | Understands your request, plans the steps, and gets the work done through the team |
| 🎨 **Product Designer** | Builds **print-ready PDFs**: planners, journals, habit trackers, kids' worksheets (tracing, maths, word search), flashcards and coloring pages (mandalas, patterns, letters). English, Urdu and Arabic; A4, A5 or Letter |
| ✍️ **Listing Writer** | Titles, descriptions, 13 SEO tags and price suggestions |
| 📣 **Marketing** | Instagram / TikTok / Facebook captions, hashtags, video scripts, WhatsApp broadcasts, 7- or 30-day content plans |
| 📈 **Store Growth** | Reviews your Wix store and orders, points out weak spots, suggests new products and better descriptions |
| 💬 **Sales (WhatsApp)** | Answers customers, creates orders, shares bank details, checks payment screenshots, sends the PDF |
| 🧠 **New skills** | If you ask for work no agent covers, the Manager **writes itself a new skill** and reuses it next time |

### 🛡️ Nothing goes live without your approval
- Adding a product to Wix or changing one → an **approval request** is created first.
- Sending files to a customer → an **approval request** first (while `AUTO_DELIVER=false`).
- Approve in two ways: the **✅ Approve** button in the dashboard, or by sending `APPROVE 5` on WhatsApp.

### 💰 Payment screenshot checks
The AI reads the screenshot and checks that it looks like a real receipt, the status is "Successful", the amount covers the order, the money went to **your** account (name or account number matches), the transaction ID is new (not reused), the date is within 3 days, and there are no visible signs of editing.

> ⚠️ **Important:** screenshots can be faked, and the AI cannot see your bank account. So by default you get a WhatsApp message, you check your bank app, and you reply `APPROVE`; only then are the files sent. Set `AUTO_DELIVER=true` only if you accept that risk.

---

## 🚀 Installation (about 10 minutes)

### 1. Requirements
- **Python 3.10 or newer**: [python.org/downloads](https://www.python.org/downloads/). On Windows, tick **"Add Python to PATH"** during installation.
- Download this repo: on GitHub click **Code → Download ZIP**, then unzip it.

### 2. Get a free AI key (at least one)
| Provider | Link | Notes |
|---|---|---|
| **Google Gemini** (recommended) | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | Good Urdu; can read screenshots |
| **Groq** | [console.groq.com/keys](https://console.groq.com/keys) | Very fast |
| **OpenRouter** | [openrouter.ai/keys](https://openrouter.ai/keys) | Use the `:free` models |

Add all three and the app switches to the next one automatically when one runs out of free usage.

### 3. Run it
**Windows:** double-click `start_windows.bat`. The first time, it opens the `.env` file in Notepad. Paste your key, save, and double-click again.

**Mac / Linux:**
```bash
./start_mac_linux.sh
```

**Or manually:**
```bash
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env        # then add your key to .env
streamlit run dashboard.py
```
The dashboard opens in your browser at `http://localhost:8501`.

### 4. First steps
Fill in your store name, bank details and policies under **⚙️ Store settings**. Then ask the **💬 Manager**, for example:
- *"Make a 30-day Ramadan planner in Urdu, A5 size"*
- *"Make a 20-page kids' pack of ABC tracing and maths worksheets"*
- *"Make a 25-page mandala coloring book"*
- *"Write an Etsy listing and 13 tags for this product"*
- *"Write this week's Instagram posts with hashtags"*
- *"Review the products on my website and tell me what to improve"*

To chat in the terminal instead: `python run_chat.py`

---

## 🌐 Connect your Wix website (optional)
1. Go to [manage.wix.com/account/api-keys](https://manage.wix.com/account/api-keys) and click **Generate API Key**. Give it the **Wix Stores**, **Media Manager** and **eCommerce / Orders** permissions.
2. **Site ID:** open your site's dashboard. The long ID after `manage.wix.com/dashboard/` in the address bar is your Site ID.
3. Put `WIX_API_KEY` and `WIX_SITE_ID` in `.env`.

The app detects whether your store uses **Catalog V1** or **V3** and works with both. On V3 the PDF is also attached to the product, so Wix can sell it directly.

## 💬 Connect WhatsApp (optional)
1. At [developers.facebook.com/apps](https://developers.facebook.com/apps), create an app and add **WhatsApp**.
2. From **API Setup**, copy the `Phone number ID` and a token. For a token that does not expire, create a **System User** token.
3. In `.env`, set `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `OWNER_WHATSAPP` (your own number, e.g. 923001234567) and `WHATSAPP_APP_SECRET` (App settings → Basic).
4. Start the server: `python run_whatsapp.py`
5. Make it reachable from the internet: `ngrok http 5000` or `cloudflared tunnel --url http://localhost:5000`
6. In Meta, go to **WhatsApp → Configuration → Webhook**:
   - URL: `https://<your-address>/webhook`
   - Verify token: `dukaan-verify` (or whatever you set in `.env`)
   - Subscribe to the **messages** field.

> **Note on your number:** if the number is currently used in the WhatsApp Business **app**, connecting it to the Cloud API usually moves it off the app. Some accounts are offered "coexistence", which keeps both working. Otherwise, use a separate number for the bot.

**As the owner, you can send on WhatsApp:**
`PENDING` (what is waiting for approval) · `APPROVE 5` · `REJECT 5` · `RESET` · or any task, e.g. *"make a new product"*.

### ☁️ Running 24/7 (Render / Railway)
- **Render:** on render.com choose **New → Blueprint** and select this repo (`render.yaml` sets everything up). Then add your keys. After deploying, add `/webhook` to the end of the link Render gives you and paste it into Meta.
- **Railway:** choose **New Project → Deploy from GitHub**. The `Dockerfile` is used automatically. Add the `.env` keys under **Variables**, and mount a **Volume** at `/data`.
- On the server, PDFs and orders are kept in `/data`. Make products in the dashboard on your computer, or place PDFs in `data/products` on the server.

---

## 📁 Project layout
```
dashboard.py          # owner dashboard (Streamlit)
run_chat.py           # terminal chat
run_whatsapp.py       # WhatsApp webhook server
dukaan/
  agent.py            # agent engine + approval gate
  llm.py              # Gemini / Groq / OpenRouter with automatic fallback
  payments.py         # payment screenshot checks
  whatsapp_bot.py     # owner + customer message handling
  skills/agents.py    # Manager, specialists, Sales agent
  skills/tools.py     # all tools
  pdfgen/             # printable PDF generator (24 page types)
  integrations/       # Wix + WhatsApp APIs
data/                 # your products, database, settings (never uploaded to GitHub)
tests/                # offline tests (no keys needed): python tests/test_offline.py
```

## 🔒 Security
- Never upload `.env` or `data/` to GitHub. `.gitignore` already excludes them.
- If a key is ever shared by mistake, create a new one right away.
- Free AI plans have daily limits. For many customers, use a paid key.

## ⚖️ License
MIT. Use it, change it, share it.
