"""Settings for Dukaan AI.

Secrets (API keys) come from the .env file.
Business details (store name, bank account, prices) come from data/store_profile.json,
which the owner can edit in the dashboard.
"""
import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA = Path(os.getenv("DUKAAN_DATA_DIR") or ROOT / "data")
PRODUCTS_DIR = DATA / "products"
CUSTOM_SKILLS_DIR = DATA / "custom_skills"
PROFILE_PATH = DATA / "store_profile.json"
DB_PATH = DATA / "dukaan.db"

for d in (DATA, PRODUCTS_DIR, CUSTOM_SKILLS_DIR):
    d.mkdir(parents=True, exist_ok=True)


def env(name, default=""):
    return os.getenv(name, default).strip()


def env_bool(name, default=False):
    v = env(name, "true" if default else "false").lower()
    return v in ("1", "true", "yes", "on")


# ---------- AI providers (all three speak the OpenAI-compatible API) ----------
PROVIDERS = {
    "gemini": {
        "key": env("GEMINI_API_KEY"),
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": env("GEMINI_MODEL", "gemini-2.5-flash"),
        "vision_model": env("GEMINI_VISION_MODEL", "") or env("GEMINI_MODEL", "gemini-2.5-flash"),
    },
    "groq": {
        "key": env("GROQ_API_KEY"),
        "base_url": "https://api.groq.com/openai/v1",
        "model": env("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "vision_model": env("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"),
    },
    "openrouter": {
        "key": env("OPENROUTER_API_KEY"),
        "base_url": "https://openrouter.ai/api/v1",
        "model": env("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"),
        "vision_model": env("OPENROUTER_VISION_MODEL", "") or env("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"),
    },
}
# Order to try. If the first one hits its free limit, the next one is used.
PROVIDER_ORDER = [p.strip() for p in env("AI_PROVIDER_ORDER", "gemini,groq,openrouter").split(",") if p.strip()]

# ---------- Store platform ----------
# wix | shopify | woocommerce | manual | auto  (auto = whichever keys are filled in, else manual)
STORE_PLATFORM = env("STORE_PLATFORM", "auto")
STORE_PLATFORM_NAME = env("STORE_PLATFORM_NAME")  # for manual mode, e.g. "Etsy" or "Daraz"

# ---------- Shopify ----------
SHOPIFY_STORE = env("SHOPIFY_STORE")  # e.g. mystore.myshopify.com
SHOPIFY_TOKEN = env("SHOPIFY_TOKEN")
SHOPIFY_API_VERSION = env("SHOPIFY_API_VERSION", "2025-07")

# ---------- WooCommerce ----------
WOO_URL = env("WOO_URL")  # e.g. https://mystore.com
WOO_KEY = env("WOO_KEY")
WOO_SECRET = env("WOO_SECRET")

# ---------- Wix ----------
WIX_API_KEY = env("WIX_API_KEY")
WIX_SITE_ID = env("WIX_SITE_ID")

# ---------- WhatsApp Cloud API (Meta) ----------
WA_TOKEN = env("WHATSAPP_TOKEN")
WA_PHONE_NUMBER_ID = env("WHATSAPP_PHONE_NUMBER_ID")
WA_VERIFY_TOKEN = env("WHATSAPP_VERIFY_TOKEN", "dukaan-verify")
WA_API_VERSION = env("WHATSAPP_API_VERSION", "v21.0")
OWNER_WHATSAPP = env("OWNER_WHATSAPP")  # e.g. 923001234567 (no +, no spaces)

# ---------- Safety switches ----------
# false = after a payment screenshot looks right, the owner still replies APPROVE <n> (recommended)
# true  = product is sent automatically when every payment check passes
AUTO_DELIVER = env_bool("AUTO_DELIVER", False)
PAYMENT_MAX_AGE_DAYS = int(env("PAYMENT_MAX_AGE_DAYS", "3") or 3)


DEFAULT_PROFILE = {
    "store_name": "My Store",
    "owner_name": "",
    "website": "",
    "currency": "PKR",
    "language": "Reply in the customer's language (Urdu, Roman Urdu or English).",
    "tone": "Warm, polite, short messages.",
    "about": "We sell printable digital products (PDF planners, journals, worksheets, coloring books).",
    "payment_methods": [
        {"type": "Bank transfer", "bank": "", "account_title": "", "account_number": "", "iban": ""}
    ],
    "policies": "Digital products are delivered as PDF on WhatsApp after payment is confirmed. No refunds on digital files once delivered.",
    "brand_colors": {"primary": "#8C2F45", "accent": "#B08A45", "paper": "#FFFDF9"},
    "notes": [],
}


def load_profile():
    if not PROFILE_PATH.exists():
        save_profile(DEFAULT_PROFILE)
    with open(PROFILE_PATH, encoding="utf-8") as f:
        data = json.load(f)
    merged = dict(DEFAULT_PROFILE)
    merged.update(data)
    return merged


def save_profile(profile):
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


def configured_providers():
    return [p for p in PROVIDER_ORDER if p in PROVIDERS and PROVIDERS[p]["key"]]
