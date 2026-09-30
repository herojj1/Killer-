#!/usr/bin/env python3
import time
import uuid
import requests

from _common import cli_args, parse_cc, fake_creds, emit, log

ACCESS_TOKEN = "YOUR_SQUARE_TOKEN"
LOCATION_ID = "YOUR_LOCATION_ID"
SANDBOX = True
BASE = "https://connect.squareupsandbox.com" if SANDBOX else "https://connect.squareup.com"


def attempt(number, mm, yy, cvv, zip_code):
    try:
        payload = {
            "idempotency_key": str(uuid.uuid4()),
            "autocomplete": False,
            "amount_money": {"amount": 100, "currency": "USD"},
            "source_id": "cnon:card-nonce-ok",
            "card_details": {"card": {"number": number, "exp_month": int(mm), "exp_year": int("20" + yy), "cvv": cvv, "postal_code": zip_code}},
            "location_id": LOCATION_ID,
        }
        r = requests.post(
            f"{BASE}/v2/payments",
            headers={"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json", "Square-Version": "2024-06-04"},
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


def main():
    args = cli_args()
    cc = parse_cc(args.cc)
    if not cc:
        return emit("square", "error", 0, 0, "bad cc format")
    start = time.time()
    n = 0
    for _ in range(args.rounds):
        f = fake_creds(cc)
        s, _ = attempt(cc["number"], f["mm"], f["yy"], f["cvv"], f["zip"])
        n += 1
        log(f"[square] fake #{n}: {s}")
    status, raw = attempt(cc["number"], cc["mm"], cc["yy"], cc["cvv"], args.zip)
    n += 1
    log(f"[square] real #{n}: {status} {raw}")
    emit("square", status, n, time.time() - start, raw)


if __name__ == "__main__":
    main()
