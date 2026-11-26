# 🛍️ Dukaan AI — AI Store Manager for Wix + WhatsApp

**Dukaan AI** aap ki online dukaan ka AI manager hai. Ye digital products (planners, journals, worksheets, coloring books) **khud banata hai**, unki listing aur SEO likhta hai, Wix website par daalta hai, social media posts likhta hai, aur WhatsApp par customers se baat kar ke order leta hai. Payment screenshot check kar ke PDF bhi bhej deta hai.

Is mein muft (free) AI lagta hai: Google Gemini, Groq ya OpenRouter. Har user apni free key daalta hai.

> *English summary: Dukaan AI is an open-source Python app that runs a digital-products store: it designs printable PDFs, writes SEO listings, publishes to Wix, writes marketing posts, and sells on WhatsApp (order → payment screenshot check → PDF delivery). Uses free AI keys (Gemini / Groq / OpenRouter). Every change to the live website and every delivery waits for the owner's approval by default.*

---

## ✨ Ye kya kya karta hai

| Agent | Kaam |
|---|---|
| 🧑‍💼 **Manager** | Aap ki baat samajhta hai, kaam ka plan banata hai, aur team se karwata hai |
| 🎨 **Product Designer** | Planner, journal, habit tracker, kids worksheet (tracing, maths, word search), flashcards aur coloring pages (mandala, patterns, letters) ki **print-ready PDF** banata hai. English, اردو aur العربية, A4/A5/Letter |
| ✍️ **Listing Writer** | Title, description, 13 SEO tags aur qeemat ka mashwara |
| 📣 **Marketing** | Instagram/TikTok/Facebook captions, hashtags, video scripts, WhatsApp broadcast, 7/30-din ka content plan |
| 📈 **Store Growth** | Wix store aur orders dekh kar kamzoriyan batata hai, naye product ideas deta hai, behtar descriptions tajweez karta hai |
| 💬 **Sales (WhatsApp)** | Customers ke sawalon ka jawab, order banana, bank details dena, screenshot check karna, PDF bhejna |
| 🧠 **Naye skills** | Agar aap koi naya kaam kahein jis ka agent nahi, to Manager **khud naya skill likh leta hai** aur agli dafa wahi istemal karta hai |

### 🛡️ Aap ki ijazat ke baghair kuch live nahi hota
- Wix par naya product daalna ya purana badalna → pehle **Approval** banta hai.
- Customer ko file bhejna → pehle **Approval** (jab tak `AUTO_DELIVER=false` hai).
- Approve karne ke do tareeqe hain: dashboard mein **✅ Approve** button, ya WhatsApp par `APPROVE 5` likh kar bhejna.

### 💰 Payment screenshot ki jaanch
AI screenshot parh kar ye cheezein check karta hai: rasid asli payment ki lagti hai, status "Successful" hai, raqam order ke barabar hai, paisa **aap ke account** mein gaya hai (naam ya account number match), Transaction ID nayi hai (dobara istemal nahi hui), tareekh 3 din ke andar hai, aur editing ke nishaan nahi.

> ⚠️ **Zaroori:** screenshot jaali bhi ho sakta hai, aur AI aap ka bank account nahi dekh sakta. Is liye default mein aap ko WhatsApp par message aata hai, aap bank app mein paisa dekh kar `APPROVE` likhte hain, tab file jati hai. `AUTO_DELIVER=true` sirf apni zimmedari par lagayein.

---

## 🚀 Install karna (10 minute)

### 1. Zaroori cheezein
- **Python 3.10 ya naya**: [python.org/downloads](https://www.python.org/downloads/). Windows par install karte waqt **"Add Python to PATH"** zaroor tick karein.
- Is repo ko download karein: GitHub par **Code → Download ZIP**, phir unzip karein.

### 2. Free AI key lein (kam az kam ek)
| Provider | Link | Note |
|---|---|---|
| **Google Gemini** (behtareen) | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | Urdu achhi, screenshot bhi parhta hai |
| **Groq** | [console.groq.com/keys](https://console.groq.com/keys) | Bohot tez |
| **OpenRouter** | [openrouter.ai/keys](https://openrouter.ai/keys) | `:free` wale models |

Teeno laga dein to ek ki free limit khatam hone par app khud doosri par chali jati hai.

### 3. Chalayein
**Windows:** `start_windows.bat` par double-click karein. Pehli dafa ye `.env` file Notepad mein kholega. Us mein apni key paste karein, save karein, aur dobara double-click karein.

**Mac / Linux:**
```bash
./start_mac_linux.sh
```

**Ya khud se:**
```bash
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env        # phir .env mein key daalein
streamlit run dashboard.py
```
Browser mein dashboard khul jayega: `http://localhost:8501`

### 4. Pehla kaam
**⚙️ Store settings** mein apni dukaan ka naam, bank details aur policies likhein. Phir **💬 Manager** se kahein, maslan:
- *"Ek 30 din ka Ramadan planner Urdu mein banao, A5 size"*
- *"Kids ke liye ABC tracing aur maths worksheets ka 20 page pack banao"*
- *"Mandala coloring book 25 pages"*
- *"Is product ki Etsy listing aur 13 tags likho"*
- *"Is hafte ki Instagram posts aur hashtags likho"*
- *"Meri website ke products dekho aur batao kya behtar karun"*

Terminal mein chat karni ho to: `python run_chat.py`

---

## 🌐 Wix website jorna (optional)
1. [manage.wix.com/account/api-keys](https://manage.wix.com/account/api-keys) par **Generate API Key** karein. Permissions mein **Wix Stores**, **Media Manager** aur **eCommerce/Orders** chunein.
2. **Site ID:** apni site ka dashboard kholein. Address bar mein `manage.wix.com/dashboard/` ke baad jo lambi ID hai, wahi Site ID hai.
3. `.env` mein `WIX_API_KEY` aur `WIX_SITE_ID` daal dein.

App khud pata lagati hai ke store **Catalog V1** par hai ya **V3** par, aur dono par chalti hai. V3 par PDF product ke saath Wix par bhi attach ho jati hai.

## 💬 WhatsApp jorna (optional)
1. [developers.facebook.com/apps](https://developers.facebook.com/apps) par app banayein → **WhatsApp** add karein.
2. **API Setup** se `Phone number ID` aur token lein. Hamesha chalne ke liye **System User** ka permanent token banayein.
3. `.env` mein `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `OWNER_WHATSAPP` (aap ka apna number, jaise 923001234567) aur `WHATSAPP_APP_SECRET` (App settings → Basic) daalein.
4. Server chalayein: `python run_whatsapp.py`
5. Isay internet par laane ke liye `ngrok http 5000` ya `cloudflared tunnel --url http://localhost:5000` chalayein.
6. Meta mein **WhatsApp → Configuration → Webhook**:
   - URL: `https://<aap-ka-address>/webhook`
   - Verify token: `dukaan-verify` (ya jo `.env` mein rakha)
   - **messages** field subscribe karein.

**Aap (owner) WhatsApp par ye likh sakte hain:**
`PENDING` (kya approval ka intezar hai) · `APPROVE 5` · `REJECT 5` · `RESET` · ya koi bhi kaam, jaise *"naya product banao"*.

### ☁️ 24 ghante chalane ke liye (Render / Railway)
- **Render:** render.com par **New → Blueprint** chunein aur ye repo select karein (`render.yaml` sab set kar deta hai). Phir apni keys daalein. Deploy ke baad jo link milega, us ke aakhir mein `/webhook` laga kar Meta mein daal dein.
- **Railway:** **New Project → Deploy from GitHub** chunein. `Dockerfile` khud istemal hoga. **Variables** mein `.env` wali keys daalein, aur ek **Volume** `/data` par mount karein.
- Server par banne wali PDFs aur orders `/data` mein rehte hain. Products ki PDFs dashboard (computer) par banayein, ya server par `data/products` mein rakhein.

---

## 📁 Folder
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
data/                 # your products, database, settings (not uploaded to GitHub)
tests/                # offline tests (no keys needed): python tests/test_offline.py
```

## 🔒 Hifazat
- `.env` aur `data/` kabhi GitHub par upload na karein. `.gitignore` inhein pehle se rok deta hai.
- Agar koi key ghalti se share ho jaye to usi waqt nayi bana lein.
- Free AI ki rozana limits hoti hain. Zyada customers hon to paid key lagayein.

## ⚖️ License
MIT. Istemal karein, badlein, aage share karein.
