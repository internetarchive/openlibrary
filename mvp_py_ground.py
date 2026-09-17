#!/usr/bin/env python3
"""
mvp_py_ground.py — Python ground-truth gold docs via the REAL WorkSolrUpdater (FakeDataProvider),
with IA lite metadata (from mvp_ia_fetch.py output) fed to both sides for availability parity.

Writes JSON {work_key: solr_doc} for diffing against rust_solr output.

Usage:
  .venv/bin/python mvp_py_ground.py --limit 10000 --out /tmp/opencode/py_10k.json \
      --ia-metadata /tmp/opencode/ia_test/ia_lite.parquet
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

import duckdb


def prepare(bronze_works: str, silver_editions: str, bronze_authors: str, limit: int, start_at: str):
    con = duckdb.connect()
    t0 = time.time()
    con.execute(f"CREATE TEMP TABLE sample_keys AS SELECT Key, JSON FROM '{bronze_works}' WHERE Key >= '{start_at}' ORDER BY Key LIMIT {limit}")
    rows = con.execute("SELECT Key, JSON FROM sample_keys ORDER BY Key").fetchall()
    edition_rows = con.execute(f"SELECT e.work_key, e.JSON FROM '{silver_editions}' e JOIN sample_keys s ON e.work_key = s.Key").fetchall()
    works = [json.loads(r[1]) for r in rows]
    work_keys = [r[0] for r in rows]
    editions_by_work = {k: [] for k in work_keys}
    for wkey, j in edition_rows:
        if wkey in editions_by_work:
            editions_by_work[wkey].append(json.loads(j))
    # Deterministic edition order (by key) to match rust pipeline
    for lst in editions_by_work.values():
        lst.sort(key=lambda e: e.get("key", ""))
    author_keys = set()
    for w in works:
        for a in w.get("authors", []):
            ak = a.get("author", {}).get("key") if isinstance(a.get("author"), dict) else a.get("author")
            if not ak and "key" in a:
                ak = a["key"]
            if ak:
                author_keys.add(ak)
    author_rows = con.execute(f"SELECT JSON FROM '{bronze_authors}' WHERE Key = ANY(?)", [list(author_keys)]).fetchall()
    authors = {}
    for (j,) in author_rows:
        doc = json.loads(j)
        authors[doc["key"]] = doc
    print(f"Prepare: {time.time() - t0:.2f}s ({len(works)} works)")
    return works, editions_by_work, authors


def load_ia_lite(path: str | None) -> dict[str, dict]:
    if not path:
        return {}
    con = duckdb.connect()
    out = {}
    for ident, colls, ari in con.execute(f"SELECT identifier, collections, ari FROM read_parquet('{path}')").fetchall():
        out[ident] = {
            "identifier": ident,
            "collection": json.loads(colls),
            "access-restricted-item": "true" if ari else "false",
            "boxid": [],
        }
    print(f"IA lite metadata: {len(out)} entries")
    return out


def prepare_chunk(chunks_path: str, chunk_index: int, bronze_works: str, silver_editions: str, bronze_authors: str):
    """Load one chunk exactly like rust_solr chunk mode: numeric-id window over bucketed
    works/editions plus orphan editions (-> fake works /works/OLxxxM)."""

    con = duckdb.connect()
    t0 = time.time()
    chunks = json.loads(open(chunks_path).read())
    c = chunks[chunk_index]
    lo, hi = int(c["lo"]), int(c["hi"])

    work_rows = con.execute(
        f"SELECT Key, JSON FROM '{bronze_works}' WHERE CAST(regexp_extract(Key, '^/works/OL(\\d+)W$', 1) AS BIGINT) BETWEEN {lo} AND {hi} ORDER BY Key"
    ).fetchall()
    works = [json.loads(j) for _, j in work_rows]
    work_keys = [k for k, _ in work_rows]

    editions_by_work: dict[str, list] = {k: [] for k in work_keys}
    ed_rows = con.execute(
        f"SELECT e.work_key, e.JSON FROM '{silver_editions}' e JOIN (SELECT unnest(?::VARCHAR[]) AS wk) s ON e.work_key = s.wk",
        [work_keys],
    ).fetchall()
    for wkey, j in ed_rows:
        if wkey in editions_by_work:
            editions_by_work[wkey].append(json.loads(j))
    # Deterministic edition order (by key) to match rust pipeline
    for lst in editions_by_work.values():
        lst.sort(key=lambda e: e.get("key", ""))

    # orphan editions in the same id window -> fed to the updater as editions (fake-work path)
    orphan_editions: list[dict] = []
    ol_base = silver_editions.rsplit("/", 1)[0]
    buckets = sorted({lo // 100000, hi // 100000} | set(range(lo // 100000 + 1, hi // 100000)))
    orphan_files: list[str] = []
    for b in buckets:
        orphan_files += sorted(str(p) for p in Path(f"{ol_base}/orphans_bucketed").glob(f"bucket={b}/*.parquet"))
    if orphan_files:
        file_list = ",".join(f"'{f}'" for f in orphan_files)
        orows = con.execute(f"SELECT JSON FROM read_parquet([{file_list}]) WHERE id BETWEEN {lo} AND {hi}").fetchall()
        for (j,) in orows:
            orphan_editions.append(json.loads(j))
    print(f"Chunk [{lo},{hi}]: {len(works)} works, {len(orphan_editions)} orphan editions ({time.time() - t0:.1f}s)")

    author_keys = set()
    for w in works:
        for a in w.get("authors", []):
            ak = a.get("author", {}).get("key") if isinstance(a.get("author"), dict) else a.get("author")
            if not ak and "key" in a:
                ak = a["key"]
            if ak:
                author_keys.add(ak)
    for ed in orphan_editions:
        for a in ed.get("authors") or []:
            ak = a.get("author", {}).get("key") if isinstance(a.get("author"), dict) else a.get("author")
            if not ak and "key" in a:
                ak = a["key"]
            if ak:
                author_keys.add(ak)
    author_rows = con.execute(f"SELECT JSON FROM '{bronze_authors}' WHERE Key = ANY(?)", [list(author_keys)]).fetchall()
    authors = {}
    for (j,) in author_rows:
        doc = json.loads(j)
        authors[doc["key"]] = doc
    return works, editions_by_work, authors, orphan_editions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10000)
    ap.add_argument("--start-at", default="/works/OL1W")
    ap.add_argument("--chunks", default=None, help="chunk manifest; overrides --limit/--start-at")
    ap.add_argument("--chunk-index", type=int, default=0)
    ap.add_argument("--bronze-works", default="/mnt/HC_Volume_106672133/openlibrary/lake_full/bronze/works.parquet")
    ap.add_argument("--silver-editions", default="/mnt/HC_Volume_106672133/openlibrary/lake_full/silver/editions.parquet")
    ap.add_argument("--bronze-authors", default="/mnt/HC_Volume_106672133/openlibrary/lake_full/bronze/authors.parquet")
    ap.add_argument("--ia-metadata", default=None)
    ap.add_argument("--out", default="/tmp/opencode/py_gold.json")
    args = ap.parse_args()

    from openlibrary.solr.data_provider import DataProvider
    from openlibrary.solr.updater.work import WorkSolrUpdater

    ia_lite = load_ia_lite(args.ia_metadata)

    class Fake(DataProvider):
        def __init__(self, wb, ebw, ab):
            super().__init__()
            self.works_by_key = wb
            self.editions_by_work = ebw
            self.authors_by_key = ab
            self.cache = {**wb, **ab}
            for lst in ebw.values():
                for ed in lst:
                    self.cache[ed["key"]] = ed
            # series docs so WorkSolrUpdater resolves series names like prod

            other = Path(args.bronze_works).parent / "other.parquet"
            if other.exists():
                con2 = duckdb.connect()
                for (j,) in con2.execute(f"SELECT JSON FROM read_parquet(['{other}']) WHERE Type = '/type/series'").fetchall():
                    d = json.loads(j)
                    self.cache[d["key"]] = d

        async def get_document(self, k):
            return self.cache.get(k) or {"key": k, "type": {"key": "/type/delete"}}

        def get_metadata(self, identifier):
            # Real IA data so py and rust compute identical ebook_access
            return ia_lite.get(identifier)

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

    if args.chunks:
        works, editions_by_work, authors, orphan_editions = prepare_chunk(
            args.chunks, args.chunk_index, args.bronze_works, args.silver_editions, args.bronze_authors
        )
    else:
        works, editions_by_work, authors = prepare(args.bronze_works, args.silver_editions, args.bronze_authors, args.limit, args.start_at)
        orphan_editions = []

    async def run():
        provider = Fake({w["key"]: w for w in works}, editions_by_work, authors)
        updater = WorkSolrUpdater(provider)
        docs = {}
        t0 = time.time()
        for w in works:
            upd, _new = await updater.update_key(w)
            for d in upd.adds:
                docs[d["key"]] = d
        # Orphan editions go through the real dispatch: update_key on the edition hits the
        # /type/edition branch (work.py:67) which builds the fake work and recurses.
        n_fake = 0
        for ed in orphan_editions:
            upd, _new = await updater.update_key(ed)
            for d in upd.adds:
                if d["key"] not in docs:
                    n_fake += 1
                docs[d["key"]] = d
        print(f"Transform: {len(docs)} docs ({n_fake} fake works) in {time.time() - t0:.2f}s")
        return docs

    docs = asyncio.run(run())
    with open(args.out, "w") as f:
        json.dump(docs, f)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
