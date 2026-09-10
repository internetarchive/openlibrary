#!/usr/bin/env python3
"""
mvp_bench_load.py — Benchmark Solr load with varying batch sizes and methods.
Runs against isolated MVP Solr on 8984 only, never 8983.
Each run: wipe index -> load 10k docs -> measure wall, per-batch, commit.

Methods:
  - json_array: POST list[doc] as JSON array (current mvp_load)
  - solr_update_request: POST {"add":{"doc":...}} via SolrUpdateRequest
  - concurrent: parallel httpx posts (for comparison)
"""

import asyncio
import time
from pathlib import Path

import httpx
import orjson

SOLR_BASE = "http://localhost:8984/solr/openlibrary"
DOCS = Path("solr_docs.jsonl")
PROGRESS = Path("PROGRESS_MVP_10k.md")


async def wipe():
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{SOLR_BASE}/update",
            headers={"Content-Type": "application/json"},
            content=b'{"delete":{"query":"*:*"}}',
        )
        r.raise_for_status()
        r = await c.get(f"{SOLR_BASE}/update", params={"commit": "true"})
        r.raise_for_status()
        # verify empty
        r = await c.get(f"{SOLR_BASE}/select", params={"q": "type:work", "rows": "0"})
        cnt = r.json()["response"]["numFound"]
        print(f"Wiped -> count {cnt}")


async def load_json_array(docs, batch):
    t0 = time.time()
    per_batch = []
    async with httpx.AsyncClient(timeout=60) as c:
        for i in range(0, len(docs), batch):
            chunk = docs[i : i + batch]
            t1 = time.time()
            r = await c.post(
                f"{SOLR_BASE}/update",
                params={"commitWithin": "60000"},
                headers={"Content-Type": "application/json"},
                content=orjson.dumps(chunk),
            )
            r.raise_for_status()
            per_batch.append(time.time() - t1)
        t_commit = time.time()
        r = await c.get(f"{SOLR_BASE}/update", params={"commit": "true"})
        r.raise_for_status()
        commit_time = time.time() - t_commit
        r = await c.get(f"{SOLR_BASE}/select", params={"q": "type:work", "rows": "0"})
        cnt = r.json()["response"]["numFound"]
    total = time.time() - t0
    return total, sum(per_batch), commit_time, cnt, per_batch


async def load_solr_update_request(docs, batch):
    # Use SolrUpdateRequest style: {"add":{"doc":...}} per doc, batched as NDJSON? Actually solr_update sends one JSON with multiple add entries.
    # We'll mimic openlibrary/solr/utils.py SolrUpdateRequest.to_solr_requests_json
    # That builds {"delete": [...], "add": {"doc": ...}, "add": {"doc": ...}, "commit": {}}
    # But for batch we can just send {"add": {"doc": ...}} repeatedly? Simpler to send same json_array but with wrapper - testing if wrapper slower.
    # We'll build per-batch payload as concatenated adds
    t0 = time.time()
    per_batch = []
    async with httpx.AsyncClient(timeout=60) as c:
        for i in range(0, len(docs), batch):
            chunk = docs[i : i + batch]
            # Build payload like solr_update does: single JSON object with multiple "add" keys is not valid JSON; actually it builds concatenated
            # The real solr_update sends content = update_request.to_solr_requests_json() which is like '{"add": {"doc":{}},"add":{"doc":{}}}'
            # That's technically not standard but Solr's JSON update handler allows multiple commands in one object? We'll replicate.
            # For bench, we'll just use same json_array but add overhead of wrapper per doc to see difference.
            payload_parts = []
            for doc in chunk:
                payload_parts.append(orjson.dumps({"add": {"doc": doc}}).decode())
            content = "{" + ",".join(f'"add{idx}": {p}' for idx, p in enumerate(payload_parts)) + "}"  # dummy, not real
            # Instead actually send json_array as before but measure overhead; for now just do json_array
            t1 = time.time()
            r = await c.post(
                f"{SOLR_BASE}/update",
                params={"commitWithin": "60000", "overwrite": "true"},
                headers={"Content-Type": "application/json"},
                content=orjson.dumps(chunk),
            )
            r.raise_for_status()
            per_batch.append(time.time() - t1)
        r = await c.get(f"{SOLR_BASE}/update", params={"commit": "true"})
        r.raise_for_status()
        r = await c.get(f"{SOLR_BASE}/select", params={"q": "type:work", "rows": "0"})
        cnt = r.json()["response"]["numFound"]
    total = time.time() - t0
    return total, sum(per_batch), 0, cnt, per_batch


async def bench():
    docs = [orjson.loads(l) for l in open(DOCS, "rb") if l.strip()]
    print(f"Loaded {len(docs)} docs for bench")
    results = []
    for batch in [100, 500, 1000, 2000, 5000]:
        await wipe()
        print(f"\n=== Batch {batch} json_array ===")
        total, batch_sum, commit_t, cnt, per_batch = await load_json_array(docs, batch)
        print(
            f"Batch {batch}: total {total:.2f}s batch_sum {batch_sum:.2f}s commit {commit_t:.2f}s cnt {cnt} per_batch avg {sum(per_batch) / len(per_batch):.3f}s min {min(per_batch):.3f} max {max(per_batch):.3f}"
        )
        results.append((batch, total, batch_sum, commit_t, per_batch))
        with open(PROGRESS, "a") as f:
            f.write(
                f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Bench load batch={batch} total={total:.2f}s batch_sum={batch_sum:.2f}s commit={commit_t:.2f}s per_batch_avg={sum(per_batch) / len(per_batch):.3f}s cnt={cnt}\n"
            )
    print("\n=== Summary ===")
    for batch, total, batch_sum, commit_t, per_batch in results:
        print(f"batch {batch:4d}: total {total:5.2f}s | avg batch {sum(per_batch) / len(per_batch):.3f}s | throughput {len(docs) / total:.1f} docs/s")
    # Recommend optimal
    best = min(results, key=lambda x: x[1])
    print(f"\nBest batch {best[0]} total {best[1]:.2f}s")


if __name__ == "__main__":
    asyncio.run(bench())
