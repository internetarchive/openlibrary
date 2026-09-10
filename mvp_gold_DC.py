#!/usr/bin/env python3
"""mvp_gold_DC.py — D (silver work_key) + C (parallel 18) for 10k, timed"""

import asyncio
import time
from multiprocessing import Pool

import duckdb
import orjson

BRONZE_WORKS = "lake/bronze/works.parquet"
SILVER_EDITIONS = "lake/silver/editions.parquet"
BRONZE_AUTHORS = "lake/bronze/authors.parquet"
LIMIT = 10000
START_AT = "/works/OL1W"
WORKERS = 18


def prepare():
    con = duckdb.connect()
    t0 = time.time()
    # B1: create temp sample_keys once, reuse for editions (avoid re-scan BRONZE_WORKS)
    con.execute(f"CREATE TEMP TABLE sample_keys AS SELECT Key, JSON FROM '{BRONZE_WORKS}' WHERE Key >= '{START_AT}' ORDER BY Key LIMIT {LIMIT}")
    rows = con.execute("SELECT Key, JSON FROM sample_keys ORDER BY Key").fetchall()
    t1 = time.time()
    # B4: select work_key directly from silver, avoid Python parsing to get wkey
    # editions via silver work_key (D) — now uses sample_keys temp table (B1)
    edition_rows = con.execute(f"SELECT e.work_key, e.JSON FROM '{SILVER_EDITIONS}' e JOIN sample_keys s ON e.work_key = s.Key").fetchall()
    t2 = time.time()
    works = [orjson.loads(r[1]) for r in rows]
    work_keys = [r[0] for r in rows]
    # B4: group via work_key column, no JSON parse for wkey
    editions_by_work = {k: [] for k in work_keys}
    for wkey, j in edition_rows:
        if wkey in editions_by_work:
            # still need to parse JSON for edition doc, but not for wkey
            try:
                ed = orjson.loads(j)
            except:
                import json as _json

                ed = _json.loads(j)
            editions_by_work[wkey].append(ed)
    author_keys = set()
    for w in works:
        for a in w.get("authors", []):
            ak = a.get("author", {}).get("key") if isinstance(a.get("author"), dict) else a.get("author")
            if not ak and "key" in a:
                ak = a["key"]
            if ak:
                author_keys.add(ak)
    # B2: use ANY(?) instead of executemany INSERT
    # B3: avoid double orjson.loads
    con2 = duckdb.connect()
    # Use Python list directly via ANY — DuckDB can handle list parameter
    # Fallback if ANY not supported, use temp table via Arrow
    author_keys_list = list(author_keys)
    # Use DuckDB's ability to query with Python list via = ANY
    author_rows = con2.execute(f"SELECT JSON FROM '{BRONZE_AUTHORS}' WHERE Key = ANY(?)", [author_keys_list]).fetchall()
    authors = {}
    for r in author_rows:
        j = r[0]
        try:
            doc = orjson.loads(j)
        except:
            import json as _json

            doc = _json.loads(j)
        authors[doc["key"]] = doc
    t3 = time.time()
    print(f"Prepare: works {t1 - t0:.2f}s editions {t2 - t1:.2f}s authors {t3 - t2:.2f}s total {t3 - t0:.2f}s")
    return works, editions_by_work, authors, t3 - t0


def transform_chunk(args):
    chunk, editions_by_work, authors = args
    from openlibrary.solr.data_provider import DataProvider
    from openlibrary.solr.updater.work import WorkSolrUpdater

    class Fake(DataProvider):
        def __init__(self, wb, ebw, ab):
            super().__init__()
            self.skip_ia_metadata = True
            self.works_by_key = wb
            self.editions_by_work = ebw
            self.authors_by_key = ab
            self.cache = {**wb, **ab}
            for lst in ebw.values():
                for ed in lst:
                    self.cache[ed["key"]] = ed

        # C: redundant checks removed — cache already contains wb+ab
        async def get_document(self, k):
            return self.cache.get(k) or {"key": k, "type": {"key": "/type/delete"}}

        def get_editions_of_work(self, w):
            return self.editions_by_work.get(w["key"], [])

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

    async def run():
        provider = Fake({w["key"]: w for w in chunk}, editions_by_work, authors)
        updater = WorkSolrUpdater(provider)
        docs = []
        for w in chunk:
            upd, _ = await updater.update_key(w)
            docs.extend(upd.adds)
        return docs

    return asyncio.run(run())


def main():
    t0 = time.time()
    works, editions_by_work, authors, prep = prepare()
    # chunk + parallel
    chunk_size = (len(works) + WORKERS - 1) // WORKERS
    chunks = [works[i : i + chunk_size] for i in range(0, len(works), chunk_size)]
    args = []
    for chunk in chunks:
        ck = {w["key"] for w in chunk}
        ce = {k: editions_by_work[k] for k in ck if k in editions_by_work}
        cak = set()
        for w in chunk:
            for a in w.get("authors", []):
                ak = a.get("author", {}).get("key") if isinstance(a.get("author"), dict) else a.get("author")
                if not ak and "key" in a:
                    ak = a["key"]
                if ak:
                    cak.add(ak)
        ca = {k: authors[k] for k in cak if k in authors}
        args.append((chunk, ce, ca))
    t1 = time.time()
    with Pool(WORKERS) as pool:
        results = pool.map(transform_chunk, args)
    docs = [d for lst in results for d in lst]
    build = time.time() - t1
    total = time.time() - t0
    print(f"DC Transform {len(docs)} docs build {build:.2f}s {len(docs) / build:.1f} docs/s")
    print(f"DC Total {total:.2f}s (prep {prep:.2f}s + build {build:.2f}s)")
    # Estimate full 14.4M
    full = 14406749
    est_build = (full / 10000) * build
    est_total = (full / 10000) * total
    print(f"DC Estimate full {full}: build {est_build / 3600:.2f}h total {est_total / 3600:.2f}h")
    return total, build


if __name__ == "__main__":
    main()
