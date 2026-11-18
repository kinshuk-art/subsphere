"""SubSphere 3.1 payment safety helpers.
Sandbox-only: no live provider API calls and no payment credentials stored.
"""
import hashlib, hmac, json, os, sqlite3
from datetime import datetime, timezone

DB_PATH=os.environ.get("SUBSPHERE_DB","subsphere.db")

def _conn():
    c=sqlite3.connect(DB_PATH)
    c.row_factory=sqlite3.Row
    return c

def init_payment_db():
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS demo_payment_methods (
            id INTEGER PRIMARY KEY AUTOINCREMENT, method_type TEXT NOT NULL,
            display_label TEXT NOT NULL, provider TEXT NOT NULL,
            token_reference TEXT NOT NULL, created_at TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS demo_mandates (
            id INTEGER PRIMARY KEY AUTOINCREMENT, method_id INTEGER NOT NULL,
            amount REAL NOT NULL, currency TEXT NOT NULL, frequency TEXT NOT NULL,
            status TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY(method_id) REFERENCES demo_payment_methods(id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS processed_demo_webhooks (
            event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL, processed_at TEXT NOT NULL)""")

def add_demo_method(method_type,label,provider,token_ref):
    if any(x in (label+token_ref).lower() for x in ["cvv","pin","otp","password"]):
        raise ValueError("Sensitive authentication data must never be stored.")
    with _conn() as c:
        c.execute("INSERT INTO demo_payment_methods(method_type,display_label,provider,token_reference,created_at) VALUES(?,?,?,?,?)",
                  (method_type,label,provider,token_ref,datetime.now(timezone.utc).isoformat()))

def list_demo_methods():
    with _conn() as c:
        return [dict(r) for r in c.execute("SELECT id,method_type,display_label,provider,token_reference,created_at FROM demo_payment_methods ORDER BY id DESC")]

def create_demo_mandate(method_id,amount,currency,frequency):
    if amount<=0: raise ValueError("Amount must be positive")
    with _conn() as c:
        exists=c.execute("SELECT 1 FROM demo_payment_methods WHERE id=?",(method_id,)).fetchone()
        if not exists: raise ValueError("Unknown demo payment method")
        c.execute("INSERT INTO demo_mandates(method_id,amount,currency,frequency,status,created_at) VALUES(?,?,?,?,?,?)",
                  (method_id,amount,currency,frequency,"AUTHORIZED (DEMO)",datetime.now(timezone.utc).isoformat()))

def list_demo_mandates():
    with _conn() as c:
        return [dict(r) for r in c.execute("""SELECT m.id,m.method_id,p.display_label,m.amount,m.currency,m.frequency,m.status,m.created_at
            FROM demo_mandates m JOIN demo_payment_methods p ON p.id=m.method_id ORDER BY m.id DESC""")]

def sign_test_webhook(raw_body:bytes,secret:bytes)->str:
    return hmac.new(secret,raw_body,hashlib.sha256).hexdigest()

def verify_webhook(raw_body:bytes,signature:str,secret:bytes)->bool:
    expected=sign_test_webhook(raw_body,secret)
    return hmac.compare_digest(expected,signature.strip())

def record_webhook_once(event_id,event_type):
    if not event_id: raise ValueError("Webhook event must include a unique ID")
    try:
        with _conn() as c:
            c.execute("INSERT INTO processed_demo_webhooks(event_id,event_type,processed_at) VALUES(?,?,?)",
                      (event_id,event_type,datetime.now(timezone.utc).isoformat()))
        return True
    except sqlite3.IntegrityError:
        return False
