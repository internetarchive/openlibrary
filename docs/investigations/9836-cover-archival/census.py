#!/usr/bin/env python3
"""Count the covers inside every bulk cover zip on archive.org.

Read-only: it only GETs public archive.org metadata and zip listings.
It never touches Open Library production.

Each batch should hold BATCH_SIZE covers (see openlibrary/coverstore/archive.py).
A batch that holds fewer was either skipped for covers already marked
failed (usually a handful) or uploaded before its ID range was full (#9836).

Usage:
    python census.py 0014                 # full-size tier of covers_0014
    python census.py 0008 0009 --tiers "" s m l
    python census.py 0014 --only-short --ranges

Positive control: `python census.py 0014 --tiers ""` must report
covers_0014_61.zip = 10000 and covers_0014_62.zip = 4073. If it reports 0
for everything, the listing format changed and the counts cannot be trusted.
"""

import argparse
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from itertools import pairwise

BATCH_SIZE = 10_000
UA = "openlibrary-cover-census/1.0 (+https://github.com/internetarchive/openlibrary/issues/9836)"


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except OSError:
            if attempt == 2:
                raise
    raise AssertionError("unreachable")


def list_zips(item: str) -> list[str]:
    md = json.loads(get(f"https://archive.org/metadata/{item}"))
    pattern = re.compile(rf"{re.escape(item)}_(\d{{2}})\.zip")
    return sorted(f["name"] for f in md.get("files", []) if pattern.fullmatch(f["name"]))


def cover_ids_in_zip(item: str, zipname: str) -> list[int]:
    html = get(f"https://archive.org/download/{item}/{zipname}/").decode("utf-8", "replace")
    return sorted({int(m) for m in re.findall(r"(\d{10})(?:-[SML])?\.jpg", html)})


def census(item_ids: list[str], tiers: list[str], workers: int):
    jobs: list[tuple[str, str]] = []
    for item_id in item_ids:
        for tier in tiers:
            item = f"{tier}_covers_{item_id}" if tier else f"covers_{item_id}"
            jobs.extend((item, z) for z in list_zips(item))

    def run(job):
        item, zipname = job
        return item, zipname, cover_ids_in_zip(item, zipname)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        yield from pool.map(run, jobs)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("item_ids", nargs="+", help="4-digit item ids, e.g. 0014")
    p.add_argument("--tiers", nargs="+", default=[""], help='"" (full), s, m, l')
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--only-short", action="store_true", help=f"print only batches with < {BATCH_SIZE} covers")
    p.add_argument("--ranges", action="store_true", help="print min/max id and internal gaps")
    args = p.parse_args()

    total = short = 0
    for _item, zipname, ids in census(args.item_ids, args.tiers, args.workers):
        total += 1
        n = len(ids)
        if n < BATCH_SIZE:
            short += 1
        elif args.only_short:
            continue
        line = f"{zipname} {n}"
        if args.ranges and ids:
            gaps = sum(b - a - 1 for a, b in pairwise(ids))
            line += f" min={ids[0]} max={ids[-1]} gaps={gaps}"
        print(line, flush=True)
    print(f"# checked {total} zips, {short} hold fewer than {BATCH_SIZE}", file=sys.stderr)


if __name__ == "__main__":
    main()
