#!/usr/bin/env python3
"""
mvp_gold.py — Build Gold parquet lake from Silver/Bronze
Gold = Solr docs ready (key, title, author_key, etc.) as parquet, not jsonl

Usage:
  LIMIT=10000 .venv/bin/python mvp_gold.py          # 10k sample
  LIMIT=100000 .venv/bin/python mvp_gold.py         # 100k sample for extrapolate
  .venv/bin/python mvp_gold.py --limit 10000 --out lake/gold/sample.parquet

Estimates full 14.4M via linear extrapolate from sample.
"""

import argparse
import asyncio
import os
import time
from pathlib import Path

import duckdb
import orjson
import pyarrow as pa
import pyarrow.parquet as pq

BRONZE_WORKS = Path("lake/bronze/works.parquet")
SILVER_EDITIONS = Path("lake/silver/editions.parquet")
BRONZE_AUTHORS = Path("lake/bronze/authors.parquet")
OUT_DIR = Path("lake/gold")
OUT_DIR.mkdir(parents=True, exist_ok=True)

START_AT = "/works/OL1W"

# reuse transform logic from mvp_transform
from openlibrary.solr.data_provider import DataProvider
from openlibrary.solr.updater.work import WorkSolrUpdater


class FakeDataProvider(DataProvider):
    def __init__(self, works_by_key, editions_by_work, authors_by_key):
        super().__init__()
        self.skip_ia_metadata = True
        self.works_by_key = works_by_key
        self.editions_by_work = editions_by_work
        self.authors_by_key = authors_by_key
        self.cache = {**works_by_key, **authors_by_key}
        for lst in editions_by_work.values():
            for ed in lst:
                self.cache[ed["key"]] = ed

    async def get_document(self, key):
        return self.cache.get(key) or self.authors_by_key.get(key) or self.works_by_key.get(key) or {"key": key, "type": {"key": "/type/delete"}}

    def get_editions_of_work(self, work):
        return self.editions_by_work.get(work["key"], [])

    def preload_editions_of_works(self, k):
        pass

    def preload_cover_dimensions(self):
        pass

    def get_cover_dimensions(self, cid):
        return None

    def get_work_ratings(self, k):
        return None

    def get_work_reading_log(self, k):
        return None

    async def get_trending_data(self, k):
        return {}

    def find_redirects(self, k):
        return []


async def build_gold(limit: int, out_path: Path):
    t0 = time.time()
    con = duckdb.connect()
    # Sample works via DuckDB (fast, 0.74s for 10k)
    print(f"Sampling {limit} works from {BRONZE_WORKS} START_AT {START_AT}")
    t1 = time.time()
    rows = con.execute(f"SELECT Key, JSON FROM '{BRONZE_WORKS}' WHERE Key >= '{START_AT}' ORDER BY Key LIMIT {limit}").fetchall()
    print(f"Works sample {len(rows)} in {time.time() - t1:.2f}s first {rows[0][0]}")
    works = [orjson.loads(r[1]) for r in rows]
    work_keys = [r[0] for r in rows]
    work_keys_set = set(work_keys)

    # Editions via silver work_key (1.8s for 10k)
    t2 = time.time()
    con.execute("CREATE TEMP TABLE sample_keys (Key VARCHAR)")
    con.executemany("INSERT INTO sample_keys VALUES (?)", [(k,) for k in work_keys])
    edition_rows = con.execute(
        f"SELECT JSON FROM '{SILVER_EDITIONS}' JOIN sample_keys s ON silver.work_key = s.Key".replace("silver", str(SILVER_EDITIONS))
        if False
        else f"SELECT e.JSON FROM '{SILVER_EDITIONS}' e JOIN sample_keys s ON e.work_key = s.Key"
    ).fetchall()
    # Actually use silver path
    # Re-run correctly
    con.execute("DROP TABLE sample_keys")
    con.execute(
        "CREATE TEMP TABLE sample_keys2 AS SELECT Key FROM (SELECT Key FROM 'lake/bronze/works.parquet' WHERE Key >= '/works/OL1W' ORDER BY Key LIMIT 10000) ".replace(
            "10000", str(limit)
        )
    )
    # simpler: reuse rows
    # For now use python fallback for editions? Use DuckDB silver
    t2 = time.time()
    con2 = duckdb.connect()
    # Use silver join
    edition_rows = con2.execute(
        f"SELECT e.JSON FROM '{SILVER_EDITIONS}' e JOIN (SELECT Key FROM '{BRONZE_WORKS}' WHERE Key >= '{START_AT}' ORDER BY Key LIMIT {limit}) s ON e.work_key = s.Key"
    ).fetchall()
    print(f"Editions query {len(edition_rows)} in {time.time() - t2:.2f}s")
    editions = [orjson.loads(r[0]) for r in edition_rows]
    editions_by_work = {k: [] for k in work_keys}
    for ed in editions:
        wkey = ed.get("works", [{}])[0].get("key") if ed.get("works") else None
        if wkey in editions_by_work:
            editions_by_work[wkey].append(ed)
    print(f"Grouped editions {len(editions)}")

    # Authors via bronze
    author_keys = set()
    for w in works:
        for a in w.get("authors", []):
            ak = a.get("author", {}).get("key") if isinstance(a.get("author"), dict) else a.get("author")
            if not ak and "key" in a:
                ak = a["key"]
            if ak:
                author_keys.add(ak)
    print(f"Author keys {len(author_keys)}")
    t3 = time.time()
    con3 = duckdb.connect()
    con3.execute("CREATE TEMP TABLE ak (Key VARCHAR)")
    con3.executemany("INSERT INTO ak VALUES (?)", [(k,) for k in author_keys])
    author_rows = con3.execute(f"SELECT a.JSON FROM '{BRONZE_AUTHORS}' a JOIN ak ON a.Key = ak.Key").fetchall()
    print(f"Authors query {len(author_rows)} in {time.time() - t3:.2f}s")
    authors = {orjson.loads(r[0])["key"]: orjson.loads(r[0]) for r in author_rows}

    # Transform
    works_by_key = {w["key"]: w for w in works}
    provider = FakeDataProvider(works_by_key, editions_by_work, authors)
    updater = WorkSolrUpdater(provider)
    docs = []
    t_build = time.time()
    for w in works:
        upd, _ = await updater.update_key(w)
        docs.extend(upd.adds)
    build_time = time.time() - t_build
    print(f"Transform {len(docs)} docs build {build_time:.2f}s {len(docs) / build_time:.1f} docs/s")

    # Write Gold parquet
    t4 = time.time()
    # Define gold schema: flatten SolrDocument to parquet
    # Use pyarrow to write all docs as JSON string + extracted columns for demo
    # Keep full doc as JSON plus key column for DuckDB pushdown
    table = pa.table(
        {
            "key": [d.get("key") for d in docs],
            "doc_json": [orjson.dumps(d).decode() for d in docs],
            "title": [d.get("title") for d in docs],
            "edition_count": [d.get("edition_count") for d in docs],
        }
    )
    pq.write_table(table, out_path, compression="zstd")
    write_time = time.time() - t4
    size = out_path.stat().st_size / 1e6
    print(f"Wrote Gold {out_path} {len(docs)} rows {size:.1f}MB in {write_time:.2f}s")

    total = time.time() - t0
    print(f"Total Gold {limit} in {total:.2f}s")
    # Estimate full 14.4M
    full = 14406749
    est_transform = (full / limit) * build_time
    est_write = (full / limit) * write_time
    est_total = est_transform + est_write + 60  # + sample overhead
    print(
        f"Estimate full {full} via linear extrapolate: transform {est_transform / 3600:.2f}h + write {est_write / 3600:.2f}h + overhead ~ {est_total / 3600:.2f}h total"
    )
    return total, build_time, write_time


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=int(os.environ.get("LIMIT", "10000")))
    ap.add_argument("--out", type=str, default="lake/gold/sample.parquet")
    args = ap.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(build_gold(args.limit, out))
