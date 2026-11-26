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
CREATE TABLE IF NOT EXISTS used_payments (
  ref TEXT PRIMARY KEY, order_id INTEGER, created REAL
);
"""


def conn():
    c = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _lock, conn() as c:
        c.executescript(SCHEMA)


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
def add_product(name, price, currency, description, files, wix_id=""):
    return q("INSERT INTO products(name,price,currency,description,files,wix_id,created) VALUES(?,?,?,?,?,?,?)",
             (name, float(price), currency, description, json.dumps(files), wix_id, time.time()))


def list_products(active_only=True):
    rows = q("SELECT * FROM products" + (" WHERE active=1" if active_only else "") + " ORDER BY id")
    for r in rows:
        r["files"] = json.loads(r["files"] or "[]")
    return rows


def get_product(pid):
    r = q("SELECT * FROM products WHERE id=?", (pid,), one=True)
    if r:
        r["files"] = json.loads(r["files"] or "[]")
    return r


def update_product(pid, **fields):
    if "files" in fields:
        fields["files"] = json.dumps(fields["files"])
    sets = ",".join(f"{k}=?" for k in fields)
    q(f"UPDATE products SET {sets} WHERE id=?", (*fields.values(), pid))


# ---------- orders ----------
def add_order(customer, customer_name, items, total, currency):
    return q("INSERT INTO orders(created,customer,customer_name,items,total,currency) VALUES(?,?,?,?,?,?)",
             (time.time(), customer, customer_name, json.dumps(items), total, currency))


def get_order(oid):
    r = q("SELECT * FROM orders WHERE id=?", (oid,), one=True)
    if r:
        r["items"] = json.loads(r["items"] or "[]")
        r["payment"] = json.loads(r["payment"] or "{}")
    return r


def open_order_for(customer):
    r = q("SELECT id FROM orders WHERE customer=? AND status IN ('awaiting_payment','payment_review') "
          "ORDER BY id DESC LIMIT 1", (customer,), one=True)
    return get_order(r["id"]) if r else None


def list_orders(limit=100):
    rows = q("SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,))
    for r in rows:
        r["items"] = json.loads(r["items"] or "[]")
        r["payment"] = json.loads(r["payment"] or "{}")
    return rows


def update_order(oid, **fields):
    if "payment" in fields:
        fields["payment"] = json.dumps(fields["payment"], ensure_ascii=False)
    sets = ",".join(f"{k}=?" for k in fields)
    q(f"UPDATE orders SET {sets} WHERE id=?", (*fields.values(), oid))


def payment_ref_used(ref):
    return bool(q("SELECT ref FROM used_payments WHERE ref=?", (ref,), one=True))


def mark_payment_ref(ref, order_id):
    q("INSERT OR IGNORE INTO used_payments(ref,order_id,created) VALUES(?,?,?)", (ref, order_id, time.time()))


# ---------- chat history ----------
def add_message(channel, role, content):
    q("INSERT INTO messages(created,channel,role,content) VALUES(?,?,?,?)",
      (time.time(), channel, role, content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)))


def history(channel, limit=16):
    rows = q("SELECT role,content FROM messages WHERE channel=? ORDER BY id DESC LIMIT ?", (channel, limit))
    return list(reversed(rows))


def clear_history(channel):
    q("DELETE FROM messages WHERE channel=?", (channel,))


init()
