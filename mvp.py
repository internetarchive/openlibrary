#!/usr/bin/env python3
"""
mvp.py — Orchestrator: sample -> transform -> (optional) load
Usage:
  python mvp.py --sample          # only sample
  python mvp.py --transform       # only transform (needs sample outputs)
  python mvp.py --load            # only load (needs transform output)
  python mvp.py --no-load         # sample+transform without solr load
  python mvp.py                   # full pipeline sample+transform+load
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

PROGRESS = Path("PROGRESS_MVP_10k.md")


def run_step(cmd):
    print(f"\n=== Running: {' '.join(cmd)} ===", flush=True)
    start = time.time()
    result = subprocess.run(cmd, check=False)
    elapsed = time.time() - start
    print(f"=== Done {cmd[0]} exit={result.returncode} {elapsed:.2f}s ===\n", flush=True)
    if result.returncode != 0:
        sys.exit(result.returncode)
    return elapsed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true", help="only sample")
    ap.add_argument("--transform", action="store_true", help="only transform")
    ap.add_argument("--load", action="store_true", help="only load")
    ap.add_argument("--no-load", action="store_true", help="skip solr load")
    args = ap.parse_args()

    py = sys.executable  # use current venv python

    only = args.sample or args.transform or args.load
    if args.sample and not (args.transform or args.load):
        run_step([py, "mvp_sample.py"])
        return
    if args.transform:
        run_step([py, "mvp_transform.py"])
        return
    if args.load:
        run_step([py, "mvp_load.py"])
        return

    # full
    t0 = time.time()
    run_step([py, "mvp_sample.py"])
    run_step([py, "mvp_transform.py"])
    if not args.no_load:
        run_step([py, "mvp_load.py"])
    total = time.time() - t0
    msg = f"MVP full pipeline total {total:.2f}s"
    print(msg)
    with open(PROGRESS, "a") as f:
        f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")


if __name__ == "__main__":
    main()
