#!/usr/bin/env python3
"""
mvp_osp_to_solr.py — Push Open Syllabus Project citation counts onto work docs as atomic {"set":}
updates. Production computes osp_count during gold build via get_total_by_olid
(openlibrary/utils/open_syllabus_project.py) reading osp_totals.db (table data(olid,total), olid =
numeric work id); posting post-load reaches the same end state without touching the rust builder.

Ghost guard: only keys present in gold are posted — atomic updates on missing docs create stubs.

Usage:
  .venv/bin/python mvp_osp_to_solr.py --dry-run          # first rows + totals
  .venv/bin/python mvp_osp_to_solr.py                    # full run (~1.37M works, few minutes)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import time

import duckdb
import httpx


async def post_rows(rows: list[tuple[str, int]], update_url: str, batch: int, concurrency: int):
    sem = asyncio.Semaphore(concurrency)
    counter = [0]
    t0 = time.time()

    async def _post(client, payload: bytes, n: int):
        async with sem:
            for attempt in range(3):
                try:
                    res = await client.post(
                        update_url,
                        params={"commitWithin": "60000"},
                        content=payload,
                        headers={"Content-Type": "application/json"},
                    )
                    res.raise_for_status()
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(2**attempt)
            counter[0] += n
            if counter[0] % 100_000 < n:
                rate = counter[0] / max(time.time() - t0, 0.001)
                print(f"  {counter[0]:,} posted ({rate:.0f}/s)", flush=True)

    async with httpx.AsyncClient(timeout=120.0) as client:
        for i in range(0, len(rows), batch):
            chunk = rows[i : i + batch]
            docs = [{"key": k, "type": {"set": "work"}, "osp_count": {"set": total}} for k, total in chunk]
            await _post(client, json.dumps(docs).encode(), len(chunk))
    print(f"[post done] {counter[0]:,} works in {(time.time() - t0) / 60:.1f}m", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--osp-db", default="/mnt/HC_Volume_106672133/openlibrary/osp/osp_totals.db")
    ap.add_argument("--gold", default="/mnt/HC_Volume_106672133/openlibrary/lake_full/gold/rust_full.parquet")
    ap.add_argument("--solr", default="http://localhost:8985/solr/openlibrary")
    ap.add_argument("--batch", type=int, default=5000)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-commit", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = sqlite3.connect(args.osp_db)
    cur = conn.cursor()
    rows: list[tuple[str, int]] = []
    last = -1
    while True:
        batch = cur.execute("SELECT olid, total FROM data WHERE olid > ? ORDER BY olid LIMIT 200000", [last]).fetchall()
        if not batch:
            break
        last = batch[-1][0]
        rows.extend((f"/works/OL{olid}W", total) for olid, total in batch)
        if args.limit and len(rows) >= args.limit:
            rows = rows[: args.limit]
            break
    print(f"[osp] {len(rows):,} candidate works from {args.osp_db}")

    con = duckdb.connect()
    con.execute(f"CREATE OR REPLACE TEMP TABLE gold_keys AS SELECT key AS k FROM read_parquet(['{args.gold}'])")
    # ghost guard: ACTUALLY drop keys absent from gold (atomic updates would create stub docs)
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE cand AS
        SELECT unnest(?::VARCHAR[]) AS k, unnest(?::INTEGER[]) AS total
        """,
        [[k for k, _ in rows], [t for _, t in rows]],
    )
    kept = con.execute("SELECT c.k, c.total FROM cand c SEMI JOIN gold_keys g ON c.k = g.k ORDER BY c.k").fetchall()
    print(f"[osp] {len(kept):,} in gold; skipping {len(rows) - len(kept):,} absent (ghost guard)")
    rows = kept

    if args.dry_run:
        for k, total in rows[:5]:
            print(f"  {k}: {total}")
        return

    asyncio.run(post_rows(rows, f"{args.solr.rstrip('/')}/update", args.batch, args.concurrency))
    if not args.no_commit:
        r = httpx.post(f"{args.solr.rstrip('/')}/update", params={"commit": "true"}, headers={"Content-Type": "application/json"}, content=b"{}", timeout=300)
        r.raise_for_status()
        print("[commit] done", flush=True)


if __name__ == "__main__":
    main()
