#!/usr/bin/env python3
"""mvp_gold_DCA.py — D (silver) + C (parallel) + A (single denormalized query)"""

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


def prepare_single_query():
    con = duckdb.connect()
    t0 = time.time()
    # Single query: works + editions aggregated via list, plus author_keys via json_extract
    # We do works+editions in one query, authors still need second but we try to include via unnest
    # For true single query, use: SELECT w.Key, w.JSON as work_json, list(e.JSON) as editions, list(a.JSON) as authors
    # But authors need join via author_keys array; we can do via lateral
    q = f"""
    WITH sample AS (
      SELECT Key, JSON as work_json FROM '{BRONZE_WORKS}' WHERE Key >= '{START_AT}' ORDER BY Key LIMIT {LIMIT}
    ),
    edition_agg AS (
      SELECT s.Key as skey, list(e.JSON) as editions
      FROM sample s LEFT JOIN '{SILVER_EDITIONS}' e ON e.work_key = s.Key
      GROUP BY s.Key
    )
    SELECT s.work_json, edition_agg.editions
    FROM sample s JOIN edition_agg ON edition_agg.skey = s.Key
    ORDER BY s.Key
    """
    rows = con.execute(q).fetchall()
    t1 = time.time()
    print(f"Single query works+editions {len(rows)} in {t1 - t0:.2f}s")
    # Need also authors: we can get author_keys from work_json, then fetch authors in same query via unnest?
    # For DCA, we add authors via second join in same query using unnest of author_keys
    # Build author mapping via silver works author_keys if available? Use bronze works author_keys via json_extract
    # Simpler: keep authors as second query but count as part of single denormalized (still 1 main + 1 authors = 2 vs 3)
    # For true single, do:
    q2 = f"""
    WITH sample AS (
      SELECT Key, JSON as work_json FROM '{BRONZE_WORKS}' WHERE Key >= '{START_AT}' ORDER BY Key LIMIT {LIMIT}
    ),
    sample_authors AS (
      SELECT DISTINCT unnest(CAST(json_extract(work_json, '$.authors[*].author.key') AS VARCHAR[])) as akey
      FROM sample
    )
    SELECT count(*) FROM sample_authors
    """
    # just to test unnest speed
    t2 = time.time()
    cnt = con.execute(q2).fetchone()[0]
    print(f"Author keys via unnest count {cnt} in {time.time() - t2:.2f}s")
    return rows, time.time() - t0


def _transform_chunk_dca(args):
    chunk, ebw, ab = args
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

    async def run():
        provider = Fake({w["key"]: w for w in chunk}, ebw, ab)
        updater = WorkSolrUpdater(provider)
        docs = []
        for w in chunk:
            upd, _ = await updater.update_key(w)
            docs.extend(upd.adds)
        return docs

    return asyncio.run(run())


def prepare_and_transform():
    t0 = time.time()
    rows, qtime = prepare_single_query()
    # Parse rows into works/editions
    works = []
    editions_by_work = {}
    for r in rows:
        work_json, editions_json = r
        w = orjson.loads(work_json) if isinstance(work_json, str) else work_json
        works.append(w)
        if editions_json is None:
            eds = []
        else:
            eds = []
            for e in editions_json:
                if e is None:
                    continue
                if isinstance(e, str):
                    try:
                        eds.append(orjson.loads(e))
                    except:
                        eds.append(json.loads(e))
                else:
                    eds.append(e)
        editions_by_work[w["key"]] = eds
    # Authors via bronze join using unnest from silver? Use same as before but via single query's author_keys
    # For DCA, we will fetch authors via one IN using unnest result
    con = duckdb.connect()
    # Use unnest to get author keys directly
    t1 = time.time()
    author_keys_rows = con.execute(f"""
      SELECT DISTINCT unnest(CAST(json_extract(JSON, '$.authors[*].author.key') AS VARCHAR[])) as akey
      FROM '{BRONZE_WORKS}' WHERE Key >= '{START_AT}' ORDER BY Key LIMIT {LIMIT}
    """).fetchall()
    author_keys = {r[0] for r in author_keys_rows if r[0]}
    print(f"Author keys {len(author_keys)} in {time.time() - t1:.2f}s")
    t2 = time.time()
    con2 = duckdb.connect()
    con2.execute("CREATE TEMP TABLE ak (Key VARCHAR)")
    con2.executemany("INSERT INTO ak VALUES (?)", [(k,) for k in author_keys])
    author_rows = con2.execute(f"SELECT a.JSON FROM '{BRONZE_AUTHORS}' a JOIN ak ON a.Key = ak.Key").fetchall()
    authors = {orjson.loads(r[0])["key"]: orjson.loads(r[0]) for r in author_rows}
    print(f"Authors fetch {len(authors)} in {time.time() - t2:.2f}s")
    prep = time.time() - t0
    print(f"Prepare DCA total {prep:.2f}s")

    # Parallel transform same as DC
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
    t3 = time.time()
    with Pool(WORKERS) as pool:
        results = pool.map(_transform_chunk_dca, args)
    docs = [d for lst in results for d in lst]
    build = time.time() - t3
    total = time.time() - t0
    print(f"DCA Transform {len(docs)} docs build {build:.2f}s {len(docs) / build:.1f} docs/s")
    print(f"DCA Total {total:.2f}s (prep {prep:.2f}s + build {build:.2f}s)")
    full = 14406749
    est_build = (full / 10000) * build
    est_total = (full / 10000) * total
    print(f"DCA Estimate full {full}: build {est_build / 3600:.2f}h total {est_total / 3600:.2f}h")
    return total, build


if __name__ == "__main__":
    prepare_and_transform()
