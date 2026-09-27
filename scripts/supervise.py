#!/usr/bin/env python3
"""Run the crawl in slices.

EDGAR will occasionally hold a connection open without ever finishing the
response body, and there is no way to interrupt a thread that is blocked on a
socket read. Rather than fight it, run the fetcher under a wall-clock timeout
and start it again. It is resumable and the sample is seeded, so a restart
picks up exactly where the last one stopped.
"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = int(os.environ.get("DROP_SAMPLE", "1500"))
SEED = os.environ.get("DROP_SEED", "20260926")
PACE = os.environ.get("DROP_PACE", "0.3")
SLICE = int(os.environ.get("DROP_SLICE", "150"))


def count():
    path = os.path.join(ROOT, "data", "formd.jsonl")
    if not os.path.exists(path):
        return 0
    return sum(1 for line in open(path) if line.strip())


def main():
    target = SAMPLE
    rounds = 0
    while count() < target and rounds < 40:
        rounds += 1
        n = count()
        print(f"[supervisor] {n}/{target}, slice {rounds}", flush=True)
        cmd = [
            sys.executable, "-u", os.path.join(ROOT, "scripts", "fetch_formd.py"),
            "--start", "20260701", "--end", "20260926",
            "--sample", str(target), "--seed", SEED,
            "--workers", "2", "--pace", PACE, "--tries", "6",
            "--limit", str(SLICE),
        ]
        try:
            subprocess.run(cmd, timeout=150)
        except subprocess.TimeoutExpired:
            print("[supervisor] slice hit its wall clock, restarting", flush=True)
        time.sleep(1)
    print(f"[supervisor] done: {count()} filings on disk", flush=True)


if __name__ == "__main__":
    main()
