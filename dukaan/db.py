"""SQLite storage: approvals, orders, local product catalog, chat history, used payment IDs."""
import json
import sqlite3
import threading
import time

from . import config

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS approvals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created REAL, kind TEXT, summary TEXT, payload TEXT,
  status TEXT DEFAULT 'pending', result TEXT
);
CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT, price REAL, currency TEXT, description TEXT,
  files TEXT, wix_id TEXT, active INTEGER DEFAULT 1, created REAL
);
CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created REAL, customer TEXT, customer_name TEXT, items TEXT, total REAL, currency TEXT,
  status TEXT DEFAULT 'awaiting_payment', payment TEXT, note TEXT
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created REAL, channel TEXT, role TEXT, content TEXT
);
CREATE TABLE IF NOT EXISTS customers (
  wa TEXT PRIMARY KEY, name TEXT, first_seen REAL, last_seen REAL,
  orders INTEGER DEFAULT 0, spent REAL DEFAULT 0, products TEXT DEFAULT '[]', notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS bank_payments (
  id INTEGER PRIMARY KEY AUTOINCREMENT, created REAL, amount REAL, ref TEXT, sender TEXT,
  raw TEXT, source TEXT, order_id INTEGER, how TEXT
);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS used_payments (
  ref TEXT PRIMARY KEY, order_id INTEGER, created REAL
);
"""


def conn():
    c = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


MIGRATIONS = ["ALTER TABLE orders ADD COLUMN nudges INTEGER DEFAULT 0",
              "ALTER TABLE orders ADD COLUMN last_nudge REAL",
              "ALTER TABLE orders ADD COLUMN paid_at REAL",
              "ALTER TABLE products ADD COLUMN kind TEXT DEFAULT 'digital'",
              "ALTER TABLE products ADD COLUMN stock INTEGER",
              "ALTER TABLE products ADD COLUMN images TEXT DEFAULT '[]'",
              "ALTER TABLE orders ADD COLUMN payment_method TEXT DEFAULT 'bank'",
              "ALTER TABLE orders ADD COLUMN shipping TEXT DEFAULT '{}'",
              "ALTER TABLE orders ADD COLUMN fulfillment TEXT DEFAULT '{}'"]


def init():
    with _lock, conn() as c:
        c.executescript(SCHEMA)
        for m in MIGRATIONS:
            try:
                c.execute(m)
            except sqlite3.OperationalError:
                pass  # column already exists


def q(sql, args=(), one=False):
    with _lock, conn() as c:
        cur = c.execute(sql, args)
        rows = [dict(r) for r in cur.fetchall()]
        c.commit()
        if sql.strip().upper().startswith("INSERT"):
            return cur.lastrowid
    return (rows[0] if rows else None) if one else rows


# ---------- approvals ----------
def add_approval(kind, summary, payload):
    return q("INSERT INTO approvals(created,kind,summary,payload) VALUES(?,?,?,?)",
             (time.time(), kind, summary, json.dumps(payload, ensure_ascii=False)))


def pending_approvals():
    return q("SELECT * FROM approvals WHERE status='pending' ORDER BY id")


def get_approval(aid):
    return q("SELECT * FROM approvals WHERE id=?", (aid,), one=True)


def set_approval(aid, status, result=""):
    q("UPDATE approvals SET status=?, result=? WHERE id=?", (status, str(result)[:4000], aid))


# ---------- products ----------
def add_product(name, price, currency, description, files=(), wix_id="", kind="digital", stock=None, images=()):
    """kind: 'digital' (files sent on WhatsApp) or 'physical' (shipped; stock None = unlimited)."""
    kind = "physical" if str(kind).lower().startswith("phys") else "digital"
    return q("INSERT INTO products(name,price,currency,description,files,wix_id,created,kind,stock,images) "
             "VALUES(?,?,?,?,?,?,?,?,?,?)",
             (name, float(price), currency, description, json.dumps(list(files)), wix_id, time.time(), kind,
              None if stock in (None, "") else int(stock), json.dumps(list(images))))


def _product_row(r):
    r["files"] = json.loads(r["files"] or "[]")
    r["images"] = json.loads(r.get("images") or "[]")
    r["kind"] = r.get("kind") or "digital"
    return r


def list_products(active_only=True):
    rows = q("SELECT * FROM products" + (" WHERE active=1" if active_only else "") + " ORDER BY id")
    return [_product_row(r) for r in rows]


def get_product(pid):
    r = q("SELECT * FROM products WHERE id=?", (pid,), one=True)
    return _product_row(r) if r else None


def update_product(pid, **fields):
    for k in ("files", "images"):
        if k in fields:
            fields[k] = json.dumps(fields[k])
    sets = ",".join(f"{k}=?" for k in fields)
    q(f"UPDATE products SET {sets} WHERE id=?", (*fields.values(), pid))


# ---------- orders ----------
def add_order(customer, customer_name, items, total, currency, status="awaiting_payment",
              payment_method="bank", shipping=None):
    return q("INSERT INTO orders(created,customer,customer_name,items,total,currency,status,payment_method,shipping) "
             "VALUES(?,?,?,?,?,?,?,?,?)",
             (time.time(), customer, customer_name, json.dumps(items), total, currency, status, payment_method,
              json.dumps(shipping or {}, ensure_ascii=False)))


def _order_row(r):
    r["items"] = json.loads(r["items"] or "[]")
    r["payment"] = json.loads(r["payment"] or "{}")
    r["shipping"] = json.loads(r.get("shipping") or "{}")
    r["fulfillment"] = json.loads(r.get("fulfillment") or "{}")
    r["payment_method"] = r.get("payment_method") or "bank"
    return r


def get_order(oid):
    r = q("SELECT * FROM orders WHERE id=?", (oid,), one=True)
    return _order_row(r) if r else None


def open_order_for(customer):
    r = q("SELECT id FROM orders WHERE customer=? AND status IN ('awaiting_payment','payment_review','cod_pending') "
          "ORDER BY id DESC LIMIT 1", (customer,), one=True)
    return get_order(r["id"]) if r else None


def list_orders(limit=100):
    rows = q("SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,))
    return [_order_row(r) for r in rows]


def update_order(oid, **fields):
    for k in ("payment", "shipping", "fulfillment"):
        if k in fields:
            fields[k] = json.dumps(fields[k], ensure_ascii=False)
    sets = ",".join(f"{k}=?" for k in fields)
    q(f"UPDATE orders SET {sets} WHERE id=?", (*fields.values(), oid))


def payment_ref_used(ref):
    return bool(q("SELECT ref FROM used_payments WHERE ref=?", (ref,), one=True))


def mark_payment_ref(ref, order_id):
    q("INSERT OR IGNORE INTO used_payments(ref,order_id,created) VALUES(?,?,?)", (ref, order_id, time.time()))


def change_stock(pid, delta):
    """Add (or with a negative delta, remove) stock. Unlimited stock (NULL) stays unlimited."""
    q("UPDATE products SET stock = MAX(0, stock + ?) WHERE id=? AND stock IS NOT NULL", (int(delta), pid))


# ---------- chat history ----------
def add_message(channel, role, content):
    q("INSERT INTO messages(created,channel,role,content) VALUES(?,?,?,?)",
      (time.time(), channel, role, content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)))


def history(channel, limit=16):
    rows = q("SELECT role,content FROM messages WHERE channel=? ORDER BY id DESC LIMIT ?", (channel, limit))
    return list(reversed(rows))


def clear_history(channel):
    q("DELETE FROM messages WHERE channel=?", (channel,))


# ---------- customers ----------
def touch_customer(wa, name=""):
    now = time.time()
    q("INSERT INTO customers(wa,name,first_seen,last_seen) VALUES(?,?,?,?) "
      "ON CONFLICT(wa) DO UPDATE SET last_seen=excluded.last_seen, "
      "name=CASE WHEN excluded.name!='' THEN excluded.name ELSE customers.name END", (wa, name or "", now, now))


def get_customer(wa):
    r = q("SELECT * FROM customers WHERE wa=?", (wa,), one=True)
    if r:
        r["products"] = json.loads(r["products"] or "[]")
    return r


def add_purchase(wa, total, product_names):
    c = get_customer(wa) or {"products": []}
    prods = list(dict.fromkeys(c["products"] + list(product_names)))
    q("UPDATE customers SET orders=orders+1, spent=spent+?, products=? WHERE wa=?",
      (float(total), json.dumps(prods, ensure_ascii=False), wa))


def list_customers(limit=200):
    rows = q("SELECT * FROM customers ORDER BY last_seen DESC LIMIT ?", (limit,))
    for r in rows:
        r["products"] = json.loads(r["products"] or "[]")
    return rows


def last_customer_message_time(wa):
    r = q("SELECT MAX(created) AS t FROM messages WHERE channel=? AND role='user'", (f"wa:{wa}",), one=True)
    return (r or {}).get("t")


# ---------- bank payments ----------
def add_bank_payment(amount, ref, sender, raw, source):
    return q("INSERT INTO bank_payments(created,amount,ref,sender,raw,source) VALUES(?,?,?,?,?,?)",
             (time.time(), amount, ref or "", sender or "", raw[:2000], source))


def bank_payments(limit=50, unmatched_only=False):
    sql = "SELECT * FROM bank_payments" + (" WHERE order_id IS NULL" if unmatched_only else "") + " ORDER BY id DESC LIMIT ?"
    return q(sql, (limit,))


def set_bank_match(bid, order_id, how):
    q("UPDATE bank_payments SET order_id=?, how=? WHERE id=?", (order_id, how, bid))


# ---------- key/value ----------
def kv_get(k, default=None):
    r = q("SELECT v FROM kv WHERE k=?", (k,), one=True)
    return r["v"] if r else default


def kv_set(k, v):
    q("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))


init()
