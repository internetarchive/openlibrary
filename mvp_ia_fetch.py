#!/usr/bin/env python3
"""
mvp_ia_fetch.py — Bulk-fetch IA lite metadata (collection, access-restricted-item) for every ocaid in the lake.

Produces <out-dir>/ia_lite.parquet (identifier VARCHAR, collections VARCHAR=JSON array, ari BOOLEAN) which
rust_solr consumes via --ia-metadata to compute REAL ebook_access/has_fulltext/public_scan_b (parity with
InternetArchiveProvider.get_access in openlibrary/book_providers.py).

Uses the IA scrape API (services/search/v1/scrape) with identifier:(a OR b ...) queries — exact matches,
no throttling. Prod's advancedsearch.php bulk path (data_provider.py) degrades to unrelated results when
called from outside prod, so we don't use it. On transient failures: retries w/ backoff, then recursively
splits the batch, then falls back to per-ocaid /metadata/<ocaid>.

Resumable: each batch writes parts/part-%08d.jsonl (atomic tmp+rename); existing part files are skipped.
Re-run anytime; finish with --merge-only to (re)build the parquet.

Usage:
  .venv/bin/python mvp_ia_fetch.py --limit 1000                      # tiny smoke test
  .venv/bin/python mvp_ia_fetch.py                                   # full fetch (~26k batches @250), resumable
  .venv/bin/python mvp_ia_fetch.py --merge-only                      # just rebuild ia_lite.parquet from parts/
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import sys
import time
from pathlib import Path

import duckdb
import httpx

SCRAPE_URL = "https://archive.org/services/search/v1/scrape"
METADATA_URL = "https://archive.org/metadata/{ocaid}/metadata"
FL_FIELDS = ["identifier", "collection", "access-restricted-item"]
BATCH_SIZE = 250
HEADERS = {"x-application-id": "ol-solr"}


def get_ocaids(bronze_editions: str, limit: int) -> list[str]:
    con = duckdb.connect()
    sql = f"SELECT DISTINCT trim(json_extract_string(JSON, '$.ocaid')) AS ocaid FROM '{bronze_editions}' WHERE ocaid IS NOT NULL AND ocaid != '' ORDER BY ocaid"
    if limit:
        sql += f" LIMIT {limit}"
    print(f"Collecting distinct ocaids from {bronze_editions} ...")
    rows = con.execute(sql).fetchall()
    print(f"  {len(rows):,} distinct ocaids")
    return [r[0] for r in rows]


def norm_doc(doc: dict) -> dict | None:
    """Normalize an IA doc -> {"identifier", "collection": [...], "ari": bool}."""
    ident = doc.get("identifier")
    if not ident:
        return None
    coll = doc.get("collection", [])
    if isinstance(coll, str):
        coll = [coll]
    elif not isinstance(coll, list):
        coll = []
    ari = doc.get("access-restricted-item", "false")
    return {
        "identifier": ident,
        "collection": [str(c) for c in coll],
        "ari": str(ari).lower() == "true",
    }


async def fetch_bulk(client: httpx.AsyncClient, ocaids: list[str], sem: asyncio.Semaphore) -> list[dict]:
    """Fetch lite metadata via the IA scrape API, which (unlike advancedsearch.php from outside
    prod) returns exact matches for the requested identifiers without throttling.
    Raises on empty results so the caller's retry/fallback path kicks in."""
    q = "identifier:(" + " OR ".join(ocaids) + ")"
    async with sem:
        r = await client.get(
            SCRAPE_URL,
            # count has a minimum of 100; over-requesting is harmless since q bounds the result set
            params={"q": q, "fields": ",".join(FL_FIELDS), "count": max(len(ocaids), 100)},
            timeout=30,
        )
    r.raise_for_status()
    wanted = set(ocaids)
    docs = [d for d in r.json().get("items", []) if d.get("identifier") in wanted]
    if not docs:
        raise ValueError(f"scrape returned no items for {len(ocaids)} ocaids")
    return docs


async def fetch_one(client: httpx.AsyncClient, ocaid: str, sem: asyncio.Semaphore) -> dict | None:
    try:
        async with sem:
            r = await client.get(METADATA_URL.format(ocaid=ocaid), timeout=30)
        r.raise_for_status()
        result = r.json().get("result")
        if not result or "error" in r.json():
            return None
        return norm_doc(
            {
                "identifier": ocaid,
                "collection": result.get("collection", []),
                "access-restricted-item": result.get("access-restricted-item", "false"),
            }
        )
    except Exception:
        return None


async def fetch_batch_with_fallback(client: httpx.AsyncClient, ocaids: list[str], sem: asyncio.Semaphore) -> list[dict]:
    """The scrape API intermittently returns 200-with-no-items for identical queries (bad backend
    windows lasting seconds~minutes), so retry with growing delays; persistent failures fall back
    to per-item /metadata calls (~8x the requests, but bounded)."""
    delays = [0.5, 1, 2, 4, 7, 11, 16]
    for delay in delays:
        try:
            docs = await fetch_bulk(client, ocaids, sem)
            return [d for d in (norm_doc(doc) for doc in docs) if d]
        except Exception:
            await asyncio.sleep(delay)
    out = await asyncio.gather(*(fetch_one(client, ocaid, sem) for ocaid in ocaids))
    return [d for d in out if d]


async def run_fetch(ocaids: list[str], parts_dir: Path, concurrency: int, batch_size: int) -> int:
    parts_dir.mkdir(parents=True, exist_ok=True)
    batches = list(itertools.batched(ocaids, batch_size, strict=False))
    sem = asyncio.Semaphore(concurrency)
    t0 = time.time()
    done = skipped = 0
    lock = asyncio.Lock()

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:

        async def _do(i: int, batch: list[str]):
            nonlocal done, skipped
            part = parts_dir / f"part-{i:08d}.jsonl"
            if part.exists():
                skipped += 1
                return
            docs = await fetch_batch_with_fallback(client, batch, sem)
            tmp = part.with_suffix(".tmp")
            tmp.write_text("".join(json.dumps(d) + "\n" for d in docs))
            tmp.rename(part)
            async with lock:
                done += 1
                rate = done / max(time.time() - t0, 0.001)
                eta = (len(batches) - done - skipped) / max(rate, 0.01)
                print(f"  batch {done + skipped:,}/{len(batches):,} -> {len(docs)} docs ({rate:.1f}/s, ETA {eta / 60:.0f}m)", flush=True)

        await asyncio.gather(*(_do(i, b) for i, b in enumerate(batches)))
    print(f"Fetched {done:,} new batches, skipped {skipped:,} existing")
    return done


def merge_parts(parts_dir: Path, out_parquet: Path) -> int:
    import pyarrow as pa
    import pyarrow.parquet as pq

    files = sorted(parts_dir.glob("part-*.jsonl"))
    print(f"Merging {len(files):,} part files -> {out_parquet}")
    seen: set[str] = set()
    schema = pa.schema([("identifier", pa.string()), ("collections", pa.string()), ("ari", pa.bool_())])
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    writer = pq.ParquetWriter(out_parquet, schema, compression="zstd", compression_level=3)
    total = dupes = bad = 0
    for f in files:
        ids, cols, aris = [], [], []
        for line in f.open():
            try:
                d = json.loads(line)
            except ValueError:
                bad += 1
                continue
            ident = d["identifier"]
            if ident in seen:
                dupes += 1
                continue
            seen.add(ident)
            ids.append(ident)
            cols.append(json.dumps(d["collection"]))
            aris.append(bool(d["ari"]))
        if ids:
            writer.write_table(pa.table({"identifier": ids, "collections": cols, "ari": aris}, schema=schema))
            total += len(ids)
    writer.close()
    print(f"  wrote {total:,} rows ({dupes:,} dupes, {bad:,} bad lines)")
    return total


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bronze-editions", default="/mnt/HC_Volume_106672133/openlibrary/lake_full/bronze/editions.parquet")
    ap.add_argument("--out-dir", default="/mnt/HC_Volume_106672133/openlibrary/lake_full/ia")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    ap.add_argument("--limit", type=int, default=0, help="Only fetch the first N ocaids (testing)")
    ap.add_argument("--merge-only", action="store_true")
    ap.add_argument("--no-merge", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    parts_dir = out_dir / "parts"
    out_parquet = out_dir / "ia_lite.parquet"

    if not args.merge_only:
        ocaids = get_ocaids(args.bronze_editions, args.limit)
        if not ocaids:
            sys.exit("No ocaids found")
        done = asyncio.run(run_fetch(ocaids, parts_dir, args.concurrency, args.batch_size))
        if done == 0 and not any(parts_dir.glob("part-*.jsonl")):
            sys.exit("Nothing fetched")

    if not args.no_merge:
        n = merge_parts(parts_dir, out_parquet)
        if n:
            print(f"Done. Wire into rust_solr with: rust_solr ... --ia-metadata {out_parquet}")


if __name__ == "__main__":
    main()
