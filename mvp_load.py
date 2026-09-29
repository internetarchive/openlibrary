#!/usr/bin/env python3
"""
mvp_load.py — Load Solr docs JSONL to isolated Solr on 8984
Batched POST /update?commitWithin=60000, final commit.
Never touches prod 8983.
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import httpx
import orjson

SOLR_BASE = os.environ.get("SOLR_BASE", "http://localhost:8984/solr/openlibrary")
DOCS = Path("solr_docs.jsonl")
PROGRESS = Path("PROGRESS_MVP_10k.md")
BATCH = int(os.environ.get("BATCH", "1000"))


async def solr_insert(docs, batch=BATCH):
    async with httpx.AsyncClient(timeout=60.0) as client:
        total = len(docs)
        for i in range(0, total, batch):
            chunk = docs[i : i + batch]
            # Solr JSON update expects list of docs; solr_insert_documents uses json.dumps(docs)
            # We'll POST as JSON array to /update with commitWithin
            start = time.time()
            resp = await client.post(
                f"{SOLR_BASE}/update",
                params={"commitWithin": "60000"},
                headers={"Content-Type": "application/json"},
                content=orjson.dumps(chunk),
            )
            elapsed = time.time() - start
            try:
                resp.raise_for_status()
            except Exception as e:
                print(f"Batch {i // batch} POST failed: {e} {resp.text[:500]}")
                raise
            print(f"Batch {i // batch + 1}/{(total + batch - 1) // batch} POST {len(chunk)} docs {elapsed:.2f}s status={resp.status_code}")
        # commit
        print("Committing...", flush=True)
        resp = await client.get(f"{SOLR_BASE}/update", params={"commit": "true"})
        resp.raise_for_status()
        print(f"Commit status {resp.status_code}", flush=True)
        # verify count
        resp = await client.get(f"{SOLR_BASE}/select", params={"q": "type:work", "rows": "0"})
        resp.raise_for_status()
        j = resp.json()
        count = j["response"]["numFound"]
        print(f"Solr count type:work = {count}", flush=True)
        return count


async def main():
    t0 = time.time()
    print(f"Loading {DOCS} to {SOLR_BASE}", flush=True)
    # Check Solr ping first
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(f"{SOLR_BASE}/admin/ping")
            print(f"Ping {SOLR_BASE}: {r.status_code} {r.text[:200]}", flush=True)
        except Exception as e:
            print(f"Ping failed: {e}", flush=True)
            raise

    docs = []
    with open(DOCS, "rb") as f:
        for line in f:
            line = line.strip()
            if line:
                docs.append(orjson.loads(line))
    print(f"Loaded {len(docs)} docs from {DOCS}", flush=True)

    if not docs:
        print("No docs to load", flush=True)
        return

    count = await solr_insert(docs, batch=BATCH)
    elapsed = time.time() - t0
    msg = f"Load: docs={len(docs)} solr_count={count} batch={BATCH} solr={SOLR_BASE} elapsed={elapsed:.2f}s"
    print(msg, flush=True)
    with open(PROGRESS, "a") as f:
        f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")


if __name__ == "__main__":
    asyncio.run(main())
