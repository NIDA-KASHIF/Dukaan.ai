# 📱 Run Dukaan AI from your phone (no computer needed)

On your computer, Dukaan AI only works while the computer is on. To use it any time from your phone,
put it on an online server once. After that it runs 24/7, answers WhatsApp customers even while you
sleep, and you open it on your phone like any other app.

Everything below can be done **from a phone browser**.

## 1. Put it online (about 10 minutes, one time)

**Render (easiest)**
1. Open **render.com**, tap **Get Started**, and sign up with **GitHub**.
2. Tap **New + → Blueprint**, choose your **Dukaan.ai** repository, and tap **Connect**.
   Render reads `render.yaml` and sets everything up (server in Singapore, a disk for your data).
3. Fill in the settings it asks for. At least:
   - `APP_PASSWORD`: the password you will type on your phone (make it strong)
   - `GEMINI_API_KEY`: your free key from aistudio.google.com/apikey
   - your store keys (Shopify / WooCommerce / Wix) and WhatsApp keys, if you use them
4. Tap **Apply** and wait until it says **Live** (a few minutes).
5. Copy your link, e.g. `https://dukaan-ai.onrender.com`.

Cost: the blueprint uses Render's **Starter** plan with a 1 GB disk (a few dollars a month), because
the free plan sleeps when idle and deletes your data on every restart. Check Render's pricing page for
current prices.

**Railway (alternative)**: railway.app → **New Project → Deploy from GitHub repo** → Dukaan.ai.
Add the same settings under **Variables**, add a **Volume** mounted at `/data`, then
**Settings → Networking → Generate Domain**.

## 2. Install it on your phone

1. Open your link in **Chrome** (Android) or **Safari** (iPhone) and log in with `APP_PASSWORD`.
2. **Android:** tap ☰ → **Install on this phone** (or Chrome menu ⋮ → **Install app**).
   **iPhone:** tap **Share** → **Add to Home Screen**.
3. Dukaan AI now has its own icon. It opens full screen, like a normal app.
   Long-press the icon for shortcuts to **Approvals**, **Orders** and **Today's brief**.

## 3. Connect WhatsApp to the online server

In Meta → **WhatsApp → Configuration → Webhook**, set the callback URL to
`https://<your-link>/webhook` and the verify token to `WHATSAPP_VERIFY_TOKEN` (default `dukaan-verify`).
Now customers are answered 24/7, and approvals, packing slips and the morning brief come to your WhatsApp.

## 4. Optional: an Android app for the Play Store

Go to **pwabuilder.com**, paste your link, and choose **Package for stores → Android**.
You get an `.aab` file to upload in the Google Play Console.

## Good to know
- Your data (orders, customers, products) lives on the server disk, not on your phone.
- Products made by the AI (PDFs) are saved on the server; open them from ☰ → Products.
- Keep `APP_PASSWORD` secret. Without it, nobody can open your store manager.
