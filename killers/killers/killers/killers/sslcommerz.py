#!/usr/bin/env python3
import random
import time
import requests

from _common import cli_args, parse_cc, fake_creds, emit, log

STORE_ID = "YOUR_STORE_ID"
STORE_PASSWD = "YOUR_STORE_PASSWORD"
SANDBOX = True
URL = ("https://sandbox.sslcommerz.com/gwprocess/v4/api.php"
       if SANDBOX else "https://securepay.sslcommerz.com/gwprocess/v4/api.php")


def attempt(number, mm, yy, cvv, zip_code):
    payload = {
        "store_id": STORE_ID, "store_passwd": STORE_PASSWD,
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
        "card_number": number, "card_expiry": f"{mm}/{yy}", "card_cvc": cvv,
    }
    try:
        r = requests.post(URL, data=payload, timeout=12)
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


def main():
    args = cli_args()
    cc = parse_cc(args.cc)
    if not cc:
        return emit("sslcommerz", "error", 0, 0, "bad cc format")
    start = time.time()
    n = 0
    for _ in range(args.rounds):
        f = fake_creds(cc)
        s, _ = attempt(cc["number"], f["mm"], f["yy"], f["cvv"], f["zip"])
        n += 1
        log(f"[sslcommerz] fake #{n}: {s}")
    status, raw = attempt(cc["number"], cc["mm"], cc["yy"], cc["cvv"], args.zip)
    n += 1
    log(f"[sslcommerz] real #{n}: {status} {raw}")
    emit("sslcommerz", status, n, time.time() - start, raw)


if __name__ == "__main__":
    main()
