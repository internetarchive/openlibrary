#!/usr/bin/env python3
"""mvp_gold_DCA2.py — D+C + A (IPC pickle elimination via initializer)
Builds on mvp_gold_DC.py B+C improvements (43.98s) + adds A:
- Pool initializer loads global paths, workers query silver/bronze per chunk (no pickle of 18k editions)
- Only chunk_keys+chunk_works JSON pickled (small)
"""

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

# Global for workers (set via initializer)
GLOBAL_SILVER = None
GLOBAL_BRONZE_AUTHORS = None
GLOBAL_BRONZE_WORKS = None


def init_worker(silver_path, bronze_authors, bronze_works):
    global GLOBAL_SILVER, GLOBAL_BRONZE_AUTHORS, GLOBAL_BRONZE_WORKS
    GLOBAL_SILVER = silver_path
    GLOBAL_BRONZE_AUTHORS = bronze_authors
    GLOBAL_BRONZE_WORKS = bronze_works
    # Warm DuckDB (optional)
    # con=duckdb.connect(); con.execute("SELECT 1")


def transform_chunk_keys(args):
    """Takes (chunk_works_json_list, chunk_keys) — fetches editions/authors per chunk via DuckDB, no large pickle"""
    chunk_works, chunk_keys = args
    # chunk_works is list of (Key, JSON) tuples for this chunk
    # Fetch editions for this chunk via work_key IN chunk_keys
    con_ed = duckdb.connect()
    # Use ANY with list
    edition_rows = con_ed.execute(f"SELECT work_key, JSON FROM '{GLOBAL_SILVER}' WHERE work_key = ANY(?)", [chunk_keys]).fetchall()
    editions_by_work = {k: [] for k in chunk_keys}
    for wkey, j in edition_rows:
        if wkey in editions_by_work:
            try:
                ed = orjson.loads(j)
            except:
                import json as _json

                ed = _json.loads(j)
            editions_by_work[wkey].append(ed)
    # Fetch authors for this chunk's works
    # Extract author_keys from chunk_works JSON
    author_keys = set()
    works = []
    for key, jstr in chunk_works:
        try:
            w = orjson.loads(jstr)
        except:
            import json as _json

            w = _json.loads(jstr)
        works.append(w)
        for a in w.get("authors", []):
            ak = a.get("author", {}).get("key") if isinstance(a.get("author"), dict) else a.get("author")
            if not ak and "key" in a:
                ak = a["key"]
            if ak:
                author_keys.add(ak)
    authors = {}
    if author_keys:
        con_au = duckdb.connect()
        author_keys_list = list(author_keys)
        author_rows = con_au.execute(f"SELECT JSON FROM '{GLOBAL_BRONZE_AUTHORS}' WHERE Key = ANY(?)", [author_keys_list]).fetchall()
        for r in author_rows:
            j = r[0]
            try:
                doc = orjson.loads(j)
            except:
                import json as _json

                doc = _json.loads(j)
            authors[doc["key"]] = doc
    # Now transform this chunk
    import asyncio

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
        provider = Fake({w["key"]: w for w in works}, editions_by_work, authors)
        updater = WorkSolrUpdater(provider)
        docs = []
        for w in works:
            upd, _ = await updater.update_key(w)
            docs.extend(upd.adds)
        return docs

    return asyncio.run(run())


def main():
    t0 = time.time()
    con = duckdb.connect()
    # Single sample_keys temp table for D (B1)
    con.execute(f"CREATE TEMP TABLE sample_keys AS SELECT Key, JSON FROM '{BRONZE_WORKS}' WHERE Key >= '{START_AT}' ORDER BY Key LIMIT {LIMIT}")
    rows = con.execute("SELECT Key, JSON FROM sample_keys ORDER BY Key").fetchall()
    print(f"Sample {len(rows)} works in {time.time() - t0:.2f}s first {rows[0][0]}")
    # Chunk works for parallel
    chunk_size = (len(rows) + WORKERS - 1) // WORKERS
    chunks = [rows[i : i + chunk_size] for i in range(0, len(rows), chunk_size)]
    # Prepare args: each chunk gets list of (Key,JSON) and list of Keys
    args = [(chunk, [k for k, _ in chunk]) for chunk in chunks]
    print(f"Chunks {len(args)} size ~{chunk_size} workers {WORKERS}")
    t1 = time.time()
    with Pool(WORKERS, initializer=init_worker, initargs=(str(SILVER_EDITIONS), str(BRONZE_AUTHORS), str(BRONZE_WORKS))) as pool:
        results = pool.map(transform_chunk_keys, args)
    docs = [d for lst in results for d in lst]
    build = time.time() - t1
    total = time.time() - t0
    print(f"D+C+A Transform {len(docs)} docs build {build:.2f}s {len(docs) / build:.1f} docs/s")
    print(f"D+C+A Total {total:.2f}s")
    full = 14406749
    est_build = (full / LIMIT) * build
    est_total = (full / LIMIT) * total
    print(f"D+C+A Estimate full {full}: build {est_build / 3600:.2f}h total {est_total / 3600:.2f}h")
    # Compare to D+C 43.98s
    print(f"Speedup vs D+C 43.98s: {43.98 / total:.2f}x total, vs build 19.44s: {19.44 / build:.2f}x")


if __name__ == "__main__":
    main()
