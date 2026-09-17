#!/usr/bin/env python3
"""
mvp_lists_to_solr.py — Stream lists from bronze parquet -> Solr (type:list/series) without per-list Solr.

Bulk DuckDB JOIN for subjects (not per-list Solr facet). Minimal fields for ListSearchScheme name search.

Usage:
  .venv/bin/python mvp_lists_to_solr.py --bronze lake/bronze/lists.parquet --solr http://localhost:8985/solr/openlibrary --batch 10000 --limit 1000 --dry-run
  .venv/bin/python mvp_lists_to_solr.py --solr http://localhost:8985/solr/openlibrary --batch 10000 --concurrency 8
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time

import duckdb
import httpx


def build_query(bronze: str, limit: int | None, with_subjects: bool = False) -> str:
    lim = f" LIMIT {limit}" if limit else ""
    # Extract list fields via DuckDB JSON
    # Handle seeds: array of {key} or {thing:{key}}
    if with_subjects:
        # Bulk subjects via JOIN with gold - for dry-run minimal still use base
        return f"""
        SELECT json_object(
          'key', Key,
          'type', CASE WHEN contains(Key, '/series/') THEN 'series' ELSE 'list' END,
          'list_type', CASE WHEN contains(Key, '/series/') THEN 'series' WHEN starts_with(Key, '/people/') THEN 'user_list' ELSE 'community_list' END,
          'name', json_extract_string(JSON, '$.name'),
          'seed', CAST(json_extract(JSON, '$.seeds') AS JSON),
          'seed_count', CAST(json_array_length(CAST(json_extract(JSON, '$.seeds') AS JSON)) AS INTEGER),
          'last_modified', json_extract_string(JSON, '$.last_modified.value') || 'Z'
        )::VARCHAR AS solr_json
        FROM '{bronze}'
        WHERE json_extract_string(JSON, '$.name') IS NOT NULL
        {lim}
        """
    else:
        return f"""
        SELECT json_object(
          'key', Key,
          'type', CASE WHEN contains(Key, '/series/') THEN 'series' ELSE 'list' END,
          'list_type', CASE WHEN contains(Key, '/series/')
            THEN 'series' WHEN starts_with(Key, '/people/') THEN 'user_list'
            ELSE 'community_list' END,
          'name', json_extract_string(JSON, '$.name'),
          'seed', (SELECT list_aggregate(list_transform(
            CAST(json_extract(JSON, '$.seeds') AS JSON[]),
            x -> coalesce(
              json_extract_string(CAST(x AS JSON), '$.key'),
              json_extract_string(CAST(x AS JSON), '$.thing.key'))), 'array_agg')),
          'seed_count', CAST(json_array_length(
            CAST(json_extract(JSON, '$.seeds') AS JSON)) AS INTEGER),
          'last_modified', json_extract_string(JSON, '$.last_modified.value') || 'Z'
        )::VARCHAR AS solr_json
        FROM '{bronze}'
        WHERE json_extract_string(JSON, '$.name') IS NOT NULL
        {lim}
        """


async def post_batches_async(batches: list[list[str]], solr_base: str, concurrency: int) -> tuple[int, float]:

    sem = asyncio.Semaphore(concurrency)
    t0 = time.time()
    async with httpx.AsyncClient(timeout=60.0) as client:

        async def _post(batch: list[str]) -> None:
            async with sem:
                # batch is list of JSON strings, need to make array of objects
                payload = b"[" + b",".join(s.encode() for s in batch) + b"]"
                res = await client.post(
                    f"{solr_base}/update?commitWithin=60000",
                    content=payload,
                    headers={"Content-Type": "application/json"},
                    params={"commitWithin": "60000"},
                )
                res.raise_for_status()

        await asyncio.gather(*[_post(b) for b in batches])
    return len(batches), time.time() - t0


def post_batches_sync(batches: list[list[str]], solr_base: str) -> tuple[int, float]:
    t0 = time.time()
    with httpx.Client(timeout=60.0) as client:
        for b in batches:
            payload = ("[" + ",".join(b) + "]").encode()
            res = client.post(
                f"{solr_base}/update?commitWithin=60000",
                content=payload,
                headers={"Content-Type": "application/json"},
                params={"commitWithin": "60000"},
            )
            res.raise_for_status()
    return len(batches), time.time() - t0


def main():  # noqa: PLR0915
    ap = argparse.ArgumentParser()
    ap.add_argument("--bronze", default="lake/bronze/lists.parquet")
    ap.add_argument("--solr", default="http://localhost:8985/solr/openlibrary")
    ap.add_argument("--batch", type=int, default=10000)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-commit", action="store_true")
    ap.add_argument("--concurrency", type=int, default=8, help="concurrent POSTs")
    ap.add_argument("--with-subjects", action="store_true", help="bulk JOIN gold for subject facets (slower)")
    ap.add_argument("--gold", default="lake/gold/rust_full.parquet")
    args = ap.parse_args()

    solr_base = args.solr.rstrip("/")
    limit = args.limit if args.limit > 0 else None

    print(f"[lists] bronze={args.bronze} solr={solr_base} batch={args.batch} conc={args.concurrency} limit={limit or 'all'}", flush=True)
    t0 = time.time()

    try:
        r = httpx.get(f"{solr_base}/admin/ping", params={"wt": "json"}, timeout=10)
        print(f"[ping] {r.status_code}", flush=True)
    except Exception as e:
        print(f"[ping failed] {e}")
        raise

    con = duckdb.connect()
    query = build_query(args.bronze, limit, with_subjects=False)
    print(f"[query] {query[:400]}...", flush=True)
    subj_map: dict[str, list[str]] = {}
    # For with_subjects, we need more complex GOLD join — handle separately
    if args.with_subjects:
        # Bulk subjects: join list seeds -> work -> subject_facet
        print("[with-subjects] building bulk JOIN...", flush=True)
        q0b = time.time()
        # Build mapping list_key -> distinct subjects via gold doc_json
        cur_subj = con.execute(f"""
            WITH base_lists AS (
              SELECT * FROM '{args.bronze}' {f"LIMIT {limit}" if limit else ""}
            ),
            list_seeds AS (
              SELECT Key AS list_key,
                     coalesce(json_extract_string(CAST(s AS JSON), '$.key'), json_extract_string(CAST(s AS JSON), '$.thing.key')) AS seed
              FROM base_lists, unnest(CAST(json_extract(JSON, '$.seeds') AS JSON[])) t(s)
              WHERE seed IS NOT NULL
            ),
            edition_seeds AS (
              SELECT DISTINCT seed AS edition_key FROM list_seeds WHERE starts_with(seed, '/books/')
            ),
            edition_map AS (
              SELECT Key AS edition_key, json_extract_string(JSON, '$.works[0].key') AS work_key
              FROM 'lake/silver/editions.parquet'
              WHERE Key IN (SELECT edition_key FROM edition_seeds)
            ),
            seed_works AS (
              SELECT ls.list_key, coalesce(em.work_key, ls.seed) AS work_key
              FROM list_seeds ls
              LEFT JOIN edition_map em ON em.edition_key = ls.seed
            ),
            filtered_gold AS (
              SELECT key, doc_json FROM '{args.gold}'
              WHERE key IN (SELECT DISTINCT work_key FROM seed_works)
            ),
            work_subjects AS (
              SELECT sw.list_key, unnest(CAST(json_extract(w.doc_json, '$.subject_facet') AS VARCHAR[])) AS subj
              FROM seed_works sw
              JOIN filtered_gold w ON w.key = sw.work_key
              WHERE json_extract(w.doc_json, '$.subject_facet') IS NOT NULL
            )
            SELECT list_key, array_agg(DISTINCT subj) AS subjects
            FROM work_subjects
            GROUP BY list_key
        """)
        rows_subj = cur_subj.fetchall()
        subj_map = dict(rows_subj)
        print(f"[with-subjects] aggregated {len(subj_map)} lists subjects in {time.time() - q0b:.2f}s", flush=True)
        query = build_query(args.bronze, limit, with_subjects=False)
    else:
        query = build_query(args.bronze, limit, with_subjects=False)

    cur = con.execute(query)
    # Stream fetchmany
    if args.dry_run:
        rows = cur.fetchmany(5)
        print(f"[dry-run] sample {len(rows)} docs:", flush=True)
        for r in rows:
            print(r[0][:800], flush=True)
        base = f"SELECT count(*) FROM '{args.bronze}' WHERE json_extract_string(JSON,'$.name') IS NOT NULL"
        if limit:
            base += f" LIMIT {limit}"
        cnt = con.execute(base).fetchone()[0]
        print(f"[dry-run] estimated {cnt} lists", flush=True)
        return

    # Collect all solr_json strings
    print("[fetch] collecting solr_json...", flush=True)
    f_t0 = time.time()
    rows = cur.fetchall()
    solr_jsons = [r[0] for r in rows if r[0]]
    print(f"[fetch] {len(solr_jsons)} docs in {time.time() - f_t0:.2f}s", flush=True)

    if args.with_subjects and subj_map:
        print(f"[with-subjects] merging {len(subj_map)} subject sets into docs...", flush=True)
        merged = []
        for s in solr_jsons:
            try:
                doc = json.loads(s)
                lst = doc.get("key")
                if subjects := subj_map.get(lst):
                    if isinstance(subjects, str):
                        try:
                            subjects = json.loads(subjects)
                        except json.JSONDecodeError, TypeError:
                            subjects = [subjects]
                    if subjects:
                        doc["subject"] = subjects
                        doc["subject_facet"] = subjects
                        doc["subject_key"] = [sb.lower().replace(" ", "_").replace(",", "") for sb in subjects]
                merged.append(json.dumps(doc))
            except Exception:  # noqa: BLE001
                merged.append(s)
        solr_jsons = merged
        print(f"[with-subjects] merged {len(solr_jsons)} docs", flush=True)

    batches = [solr_jsons[i : i + args.batch] for i in range(0, len(solr_jsons), args.batch)]
    print(f"[post] {len(batches)} batches conc={args.concurrency}...", flush=True)
    if args.concurrency > 1:
        _, post_t = asyncio.run(post_batches_async(batches, solr_base, args.concurrency))
    else:
        _, post_t = post_batches_sync(batches, solr_base)
    print(f"[post] done post_t={post_t:.2f}s total={len(solr_jsons)} docs/s={len(solr_jsons) / post_t:.1f}", flush=True)

    elapsed = time.time() - t0
    print(f"[all done] elapsed={elapsed:.2f}s", flush=True)

    if not args.no_commit:
        print("[commit] POST update?commit=true", flush=True)
        with httpx.Client(timeout=120.0) as client:
            res = client.get(f"{solr_base}/update", params={"commit": "true"})
            print(f"[commit] {res.status_code}", flush=True)
            res = client.get(f"{solr_base}/select", params={"q": "type:list", "rows": "0", "wt": "json"})
            try:
                cnt = res.json()["response"]["numFound"]
                print(f"[verify] type:list numFound={cnt}", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"[verify failed] {e}", flush=True)
            res = client.get(f"{solr_base}/select", params={"q": "type:series", "rows": "0", "wt": "json"})
            try:
                cnt = res.json()["response"]["numFound"]
                print(f"[verify] type:series numFound={cnt}", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"[verify series failed] {e}", flush=True)


if __name__ == "__main__":
    main()
