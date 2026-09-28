#!/usr/bin/env python3
"""
Wait for EDGAR to stop rate-limiting us, then pull the sample.

EDGAR answers 429 without a Retry-After header, so there is nothing to obey
except patience: probe one known-good document every couple of minutes and only
start the crawl once the door opens again. Everything runs slowly enough to stay
under the limit.
"""
import argparse
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from fetch_formd import configure_contact

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE = "https://www.sec.gov/Archives/edgar/data/2143346/000214334626000001/primary_doc.xml"
HEADERS = {}
SAMPLE = int(os.environ.get("DROP_SAMPLE", "1500"))
PACE = os.environ.get("DROP_PACE", "1.2")
WORKERS = os.environ.get("DROP_WORKERS", "2")


def probe():
    try:
        req = urllib.request.Request(PROBE, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:  # noqa: BLE001
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--contact", help="operator contact email for the SEC User-Agent (or set DROP_SEC_CONTACT)")
    args = ap.parse_args()
    try:
        user_agent = configure_contact(args.contact)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    HEADERS.update({
        "User-Agent": user_agent,
        "Accept-Encoding": "gzip",
        "Accept": "*/*",
    })
    waited = 0
    while True:
        code = probe()
        if code == 200:
            print(f"[runner] EDGAR answered 200 after {waited}s of cooling off", flush=True)
            break
        print(f"[runner] probe -> {code}; waiting", flush=True)
        time.sleep(120)
        waited += 120

    cmd = [
        sys.executable, "-u", os.path.join(ROOT, "scripts", "fetch_formd.py"),
        "--start", "20260701", "--end", "20260926",
        "--sample", str(SAMPLE), "--seed", "20260926",
        "--workers", WORKERS, "--pace", PACE, "--tries", "12",
    ]
    print("[runner] " + " ".join(cmd), flush=True)
    env = os.environ.copy()
    if args.contact:
        env["DROP_SEC_CONTACT"] = args.contact
    os.execvpe(cmd[0], cmd, env)


if __name__ == "__main__":
    main()
