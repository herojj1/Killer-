#!/usr/bin/env python3
import base64
import time
import requests

from _common import cli_args, parse_cc, fake_creds, emit, log

PUBLIC_KEY = "YOUR_PUBLIC_KEY"
PRIVATE_KEY = "YOUR_PRIVATE_KEY"
SANDBOX = True
BASE = "https://payments.sandbox.braintree-api.com/graphql" if SANDBOX else "https://payments.braintree-api.com/graphql"


def _headers():
    auth = base64.b64encode(f"{PUBLIC_KEY}:{PRIVATE_KEY}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Braintree-Version": "2019-01-01", "Content-Type": "application/json"}


def attempt(number, mm, yy, cvv, zip_code):
    query = """
    mutation Tokenize($input: TokenizeCreditCardInput!) {
      tokenizeCreditCard(input: $input) { paymentMethod { id } }
    }
    """
    variables = {"input": {"creditCard": {
        "number": number, "expirationMonth": mm,
        "expirationYear": ("20" + yy) if len(yy) == 2 else yy,
        "cvv": cvv, "billingAddress": {"postalCode": zip_code},
    }}}
    try:
        r = requests.post(BASE, headers=_headers(), json={"query": query, "variables": variables}, timeout=12)
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


def main():
    args = cli_args()
    cc = parse_cc(args.cc)
    if not cc:
        return emit("braintree", "error", 0, 0, "bad cc format")
    start = time.time()
    n = 0
    for _ in range(args.rounds):
        f = fake_creds(cc)
        s, _ = attempt(cc["number"], f["mm"], f["yy"], f["cvv"], f["zip"])
        n += 1
        log(f"[braintree] fake #{n}: {s}")
    status, raw = attempt(cc["number"], cc["mm"], cc["yy"], cc["cvv"], args.zip)
    n += 1
    log(f"[braintree] real #{n}: {status} {raw}")
    emit("braintree", status, n, time.time() - start, raw)


if __name__ == "__main__":
    main()
