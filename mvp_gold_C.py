#!/usr/bin/env python3
"""mvp_gold_C.py — Parallel workers (18) for transform only, independent test C"""

import asyncio
import time
from multiprocessing import Pool
from pathlib import Path

import duckdb
import orjson

BRONZE_WORKS = Path("lake/bronze/works.parquet")
SILVER_EDITIONS = Path("lake/silver/editions.parquet")
BRONZE_AUTHORS = Path("lake/bronze/authors.parquet")
START_AT = "/works/OL1W"
LIMIT = 10000
WORKERS = 18


# Prepare data once
def prepare():
    con = duckdb.connect()
    rows = con.execute(f"SELECT Key, JSON FROM '{BRONZE_WORKS}' WHERE Key >= '{START_AT}' ORDER BY Key LIMIT {LIMIT}").fetchall()
    works = [orjson.loads(r[1]) for r in rows]
    work_keys = [r[0] for r in rows]
    # editions via silver
    edition_rows = con.execute(
        f"SELECT e.JSON FROM '{SILVER_EDITIONS}' e JOIN (SELECT Key FROM '{BRONZE_WORKS}' WHERE Key >= '{START_AT}' ORDER BY Key LIMIT {LIMIT}) s ON e.work_key = s.Key"
    ).fetchall()
    editions = [orjson.loads(r[0]) for r in edition_rows]
    editions_by_work = {k: [] for k in work_keys}
    for ed in editions:
        wkey = ed.get("works", [{}])[0].get("key") if ed.get("works") else None
        if wkey in editions_by_work:
            editions_by_work[wkey].append(ed)
    author_keys = set()
    for w in works:
        for a in w.get("authors", []):
            ak = a.get("author", {}).get("key") if isinstance(a.get("author"), dict) else a.get("author")
            if not ak and "key" in a:
                ak = a["key"]
            if ak:
                author_keys.add(ak)
    con2 = duckdb.connect()
    con2.execute("CREATE TEMP TABLE ak (Key VARCHAR)")
    con2.executemany("INSERT INTO ak VALUES (?)", [(k,) for k in author_keys])
    author_rows = con2.execute(f"SELECT a.JSON FROM '{BRONZE_AUTHORS}' a JOIN ak ON a.Key = ak.Key").fetchall()
    authors = {orjson.loads(r[0])["key"]: orjson.loads(r[0]) for r in author_rows}
    return works, editions_by_work, authors


# Worker function
def transform_chunk(args):
    chunk, editions_by_work, authors = args
    # Need to recreate provider per process

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
            return self.cache.get(k) or self.authors_by_key.get(k) or self.works_by_key.get(k) or {"key": k, "type": {"key": "/type/delete"}}

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

    # Build lookup
    works_by_key = {w["key"]: w for w in chunk}

    # But need full editions/authors dicts passed
    # For chunk, filter editions_by_work to chunk keys only to reduce size? Pass full but okay
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
    works, editions_by_work, authors = prepare()
    prep = time.time() - t0
    print(f"Prepare done {prep:.2f}s works {len(works)} editions {sum(len(v) for v in editions_by_work.values())} authors {len(authors)}")
    # Chunk works
    chunk_size = (len(works) + WORKERS - 1) // WORKERS
    chunks = [works[i : i + chunk_size] for i in range(0, len(works), chunk_size)]
    print(f"Chunks {len(chunks)} size {chunk_size} workers {WORKERS}")
    t1 = time.time()
    # Filter editions per chunk to reduce pickle size
    args = []
    for chunk in chunks:
        chunk_keys = {w["key"] for w in chunk}
        chunk_editions = {k: editions_by_work[k] for k in chunk_keys if k in editions_by_work}
        # Filter authors to chunk's authors only
        chunk_author_keys = set()
        for w in chunk:
            for a in w.get("authors", []):
                ak = a.get("author", {}).get("key") if isinstance(a.get("author"), dict) else a.get("author")
                if not ak and "key" in a:
                    ak = a["key"]
                if ak:
                    chunk_author_keys.add(ak)
        chunk_authors = {k: authors[k] for k in chunk_author_keys if k in authors}
        args.append((chunk, chunk_editions, chunk_authors))
    with Pool(WORKERS) as pool:
        results = pool.map(transform_chunk, args)
    docs = [d for lst in results for d in lst]
    build = time.time() - t1
    print(f"Parallel transform {len(docs)} docs build {build:.2f}s {len(docs) / build:.1f} docs/s vs baseline 377 docs/s")
    total = time.time() - t0
    print(f"Total with prepare {total:.2f}s")
    # Compare to baseline 26.5s build, 78s total
    print(f"C speedup vs baseline build 26.51s: {26.51 / build:.2f}x")


if __name__ == "__main__":
    main()
