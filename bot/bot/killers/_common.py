import argparse
import json
import random
import sys


def cli_args():
    p = argparse.ArgumentParser()
    p.add_argument("--cc", required=True, help="number|mm|yy|cvv")
    p.add_argument("--zip", required=True)
    p.add_argument("--rounds", type=int, default=4)
    return p.parse_args()


def parse_cc(cc_str):
    parts = cc_str.replace(" ", "").split("|")
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


def emit(gateway, status, attempts, duration, raw="", **extra):
    out = {
        "gateway": gateway,
        "status": status,
        "attempts": attempts,
        "duration": round(duration, 2),
        "raw": (raw or "")[:400],
    }
    out.update(extra)
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()


def log(msg):
    sys.stderr.write(str(msg) + "\n")
    sys.stderr.flush()
