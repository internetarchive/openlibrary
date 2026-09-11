#!/usr/bin/env python3
"""
mvp_authors_to_solr.py — Stream authors from bronze parquet -> Solr (type:author) without Python dict overhead.

Uses DuckDB to produce Solr-ready NDJSON strings directly and streams via persistent httpx.Client.
No re-run of gold needed. Minimal required for AuthorSearchScheme (name, alternate_names) + optional work_count enrichment later.

Usage:
  python mvp_authors_to_solr.py --bronze lake/bronze/authors.parquet --solr http://localhost:8985/solr/openlibrary --batch 10000
  python mvp_authors_to_solr.py --limit 10000 --dry-run   # verify payload
"""

from __future__ import annotations

import argparse
import time

import duckdb
import httpx


def build_query(bronze: str, limit: int | None) -> str:
    lim = f" LIMIT {limit}" if limit else ""
    # Produce Solr-ready JSON string via DuckDB json_object — avoids Python orjson.loads
    # Fields per AuthorSolrBuilder + managed-schema.xml
    return f"""
    SELECT
      json_object(
        'key', Key,
        'type', 'author',
        'name', json_extract_string(JSON, '$.name'),
        'alternate_names', CAST(json_extract(JSON, '$.alternate_names') AS JSON),
        'birth_date', json_extract_string(JSON, '$.birth_date'),
        'death_date', json_extract_string(JSON, '$.death_date'),
        'date', json_extract_string(JSON, '$.date')
      )::VARCHAR AS solr_json
    FROM '{bronze}'
    WHERE json_extract_string(JSON, '$.name') IS NOT NULL
    {lim}
    """


def main():  # noqa: PLR0915
    ap = argparse.ArgumentParser()
    ap.add_argument("--bronze", default="lake/bronze/authors.parquet")
    ap.add_argument("--solr", default="http://localhost:8985/solr/openlibrary")
    ap.add_argument("--batch", type=int, default=10000)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true", help="validate payload, no POST")
    ap.add_argument("--no-commit", action="store_true")
    args = ap.parse_args()

    limit = args.limit if args.limit > 0 else None
    solr_base = args.solr.rstrip("/")
    docs_url = f"{solr_base}/update/json/docs"
    update_url = f"{solr_base}/update"

    print(f"[authors] bronze={args.bronze} solr={solr_base} batch={args.batch} limit={limit or 'all'}", flush=True)
    t0 = time.time()

    # Check Solr ping
    try:
        r = httpx.get(f"{solr_base}/admin/ping", params={"wt": "json"}, timeout=10)
        print(f"[ping] {r.status_code} {r.text[:200]}", flush=True)
    except Exception as e:
        print(f"[ping failed] {e}")
        raise

    con = duckdb.connect()
    # Use streaming cursor: execute then fetchmany without materializing all
    query = build_query(args.bronze, limit)
    print(f"[query] {query[:500]}...", flush=True)
    q_t0 = time.time()
    cur = con.execute(query)
    q_elapsed = time.time() - q_t0
    print(f"[duckdb] query prepared {q_elapsed:.2f}s", flush=True)

    # Dry-run peek
    if args.dry_run:
        rows = cur.fetchmany(5)
        print(f"[dry-run] sample {len(rows)} docs:", flush=True)
        for r in rows:
            print(r[0][:500], flush=True)
        # Count
        base = f"SELECT count(*) FROM '{args.bronze}' WHERE json_extract_string(JSON,'$.name') IS NOT NULL"
        if limit:
            base += f" LIMIT {limit}"
        cnt = con.execute(base).fetchone()[0]
        print("[dry-run] estimated count (duckdb count) queried via separate count", flush=True)
        print("[dry-run] would-be ndjson lines: check via COUNT(*)", flush=True)
        return

    headers = {"Content-Type": "application/json"}
    total = 0
    batches = 0
    post_t = 0.0

    with httpx.Client(timeout=60.0) as client:
        while True:
            rows = cur.fetchmany(args.batch)
            if not rows:
                break
            # rows is list[tuple[str]]
            # NDJSON per Solr /update/json/docs: one JSON per line (docs endpoint accepts array, but NDJSON is streaming)
            # We send as JSON array for /update/json/docs compatibility: [doc1,doc2,...]
            # Build array without parsing: b"[" + b",".join(row[0].encode()) + b"]"
            # But NDJSON (newline) also accepted by /update/json/docs since Solr 9 — use newline to avoid 5MB bracket copy overhead
            # We'll send newline-delimited (NDJSON) — Solr docs handler parses line-delimited when Content-Type json and payload not array-wrapped
            # To be safe for array endpoint, we send array:
            payload = b"[" + b",".join(r[0].encode("utf-8") for r in rows) + b"]"
            # Use /update/json/docs?commitWithin=60000 (same as fast_solr_inserts.md tuning)
            url = f"{docs_url}?commitWithin=60000"
            st = time.time()
            res = client.post(url, content=payload, headers=headers, params={"commitWithin": "60000"})
            post_t += time.time() - st
            try:
                res.raise_for_status()
            except Exception:
                print(f"[batch {batches} failed] {res.status_code} {res.text[:1000]}", flush=True)
                raise
            total += len(rows)
            batches += 1
            if batches % 10 == 0 or len(rows) < args.batch:
                print(f"[batch {batches}] {len(rows)} docs -> total {total} post_avg {post_t / batches:.2f}s", flush=True)

    elapsed = time.time() - t0
    print(f"[done] total={total} batches={batches} elapsed={elapsed:.2f}s post_time={post_t:.2f}s docs/s={total / elapsed:.1f}", flush=True)

    if not args.no_commit and total > 0:
        print("[commit] POST update?commit=true", flush=True)
        with httpx.Client(timeout=120.0) as client:
            res = client.get(update_url, params={"commit": "true"})
            print(f"[commit] {res.status_code} {res.text[:500]}", flush=True)
            # verify
            res = client.get(f"{solr_base}/select", params={"q": "type:author", "rows": "0", "wt": "json"})
            try:
                j = res.json()
                cnt = j["response"]["numFound"]
                print(f"[verify] type:author numFound={cnt}", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"[verify failed] {e} {res.text[:1000]}", flush=True)

            res = client.get(f"{solr_base}/select", params={"q": "mark", "fq": "type:author", "rows": "3", "wt": "json", "fl": "key,name,work_count"})
            print(f"[sample author search 'mark'] {res.text[:2000]}", flush=True)


if __name__ == "__main__":
    main()
