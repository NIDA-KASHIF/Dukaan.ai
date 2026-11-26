"""Pick the store platform.

STORE_PLATFORM in .env: wix | shopify | woocommerce | manual | auto (default).
auto = the first platform whose keys are filled in, otherwise manual.
Every adapter offers the same functions: enabled, status, list_products,
create_digital_product, update_product, list_orders.
"""
from .. import config
from . import manual, shopify, woocommerce, wix

ADAPTERS = {"wix": wix, "shopify": shopify, "woocommerce": woocommerce, "manual": manual}


def current():
    choice = (config.STORE_PLATFORM or "auto").lower()
    if choice in ADAPTERS:
        return ADAPTERS[choice]
    for name in ("shopify", "woocommerce", "wix"):
        if ADAPTERS[name].enabled():
            return ADAPTERS[name]
    return manual


def name():
    return current().NAME
