#!/usr/bin/env python3
"""
mvp_transform.py — Transform sampled works/editions/authors to Solr docs
Uses FakeDataProvider (in-mem) + WorkSolrUpdater (same code as prod).
Stubs ratings/reading_log/cover/ia_metadata per MVP scope (skip IA).
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import orjson

from openlibrary.solr.data_provider import DataProvider
from openlibrary.solr.updater.work import WorkSolrUpdater

WORKS = Path("works.json")
EDITIONS = Path("editions_by_work.json")
AUTHORS = Path("authors.json")
OUT_DOCS = Path("solr_docs.jsonl")
PROGRESS = Path("PROGRESS_MVP_10k.md")


class FakeDataProvider(DataProvider):
    """In-memory DataProvider; stubs everything MVP skips."""

    def __init__(self, works_by_key, editions_by_work, authors_by_key):
        super().__init__()
        # Skip IA fetching entirely per user request
        self.skip_ia_metadata = True
        self.works_by_key = works_by_key
        self.editions_by_work = editions_by_work
        self.authors_by_key = authors_by_key
        # caches for compat with LocalPostgres provider expectations
        self.cache = {**works_by_key, **authors_by_key}
        # also cache editions by key
        for lst in editions_by_work.values():
            for ed in lst:
                self.cache[ed["key"]] = ed
        self.covers_cache: dict[int, list[int]] = {}

    async def get_document(self, key: str):
        if key in self.cache:
            return self.cache[key]
        # Also check authors/works
        if key in self.authors_by_key:
            return self.authors_by_key[key]
        if key in self.works_by_key:
            return self.works_by_key[key]
        # fallback: not found -> delete type
        return {"key": key, "type": {"key": "/type/delete"}}

    def get_editions_of_work(self, work: dict):
        return self.editions_by_work.get(work["key"], [])

    def preload_editions_of_works(self, work_keys):
        pass

    def preload_cover_dimensions(self):
        pass

    def get_cover_dimensions(self, cover_id: int):
        return None

    def get_work_ratings(self, work_key: str):
        return None

    def get_work_reading_log(self, work_key: str):
        return None

    async def get_trending_data(self, work_key: str):
        return {}

    def find_redirects(self, key: str):
        return []

    def clear_cache(self):
        super().clear_cache()
        # keep our caches — don't wipe


async def transform():
    t0 = time.time()
    print("Loading sample data...", flush=True)
    with open(WORKS, "rb") as f:
        works = orjson.loads(f.read())
    with open(EDITIONS, "rb") as f:
        editions_by_work = orjson.loads(f.read())
    with open(AUTHORS, "rb") as f:
        authors = orjson.loads(f.read())

    print(f"Loaded {len(works)} works, {len(authors)} authors", flush=True)
    # editions_by_work keys are work keys, values lists
    total_editions = sum(len(v) for v in editions_by_work.values())
    print(f"Total editions: {total_editions}", flush=True)

    works_by_key = {w["key"]: w for w in works}
    provider = FakeDataProvider(works_by_key, editions_by_work, authors)
    updater = WorkSolrUpdater(provider)

    docs = []
    t_build = 0.0
    errors = 0
    for idx, work in enumerate(works):
        t1 = time.time()
        try:
            update, new_keys = await updater.update_key(work)
            # update.adds is list[SolrDocument]
            docs.extend(update.adds)
        except Exception as e:
            print(f"Error updating {work.get('key')}: {e}")
            errors += 1
        t_build += time.time() - t1
        if (idx + 1) % 1000 == 0:
            print(f"Transformed {idx + 1}/{len(works)} docs={len(docs)}", flush=True)

    print(f"Transform done: {len(docs)} docs, build time {t_build:.2f}s", flush=True)

    # Write jsonl
    with open(OUT_DOCS, "wb") as out:
        out.writelines(orjson.dumps(d) + b"\n" for d in docs)
    print(f"Wrote {OUT_DOCS} {len(docs)} docs", flush=True)

    elapsed = time.time() - t0
    msg = f"Transform: works={len(works)} docs={len(docs)} editions={total_editions} errors={errors} build={t_build:.2f}s elapsed={elapsed:.2f}s"
    print(msg, flush=True)
    with open(PROGRESS, "a") as f:
        f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    return docs


if __name__ == "__main__":
    asyncio.run(transform())
