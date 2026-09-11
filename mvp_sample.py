#!/usr/bin/env python3
"""
mvp_sample.py — Sample 10k works START_AT=/works/OL1W from OL dump
Uses DuckDB read_csv if possible, falls back to Python gzip csv.

Outputs:
  sample.parquet (Key, JSON) — 10k works
  sample.jsonl — same as JSON lines for debug
  editions_by_work.json — dict work_key -> list[edition_dict]
  authors.json — dict author_key -> author_dict
Logs to PROGRESS_MVP_10k.md
"""

from __future__ import annotations

import csv
import gzip
import json
import os
import sys
import time
from pathlib import Path

import orjson

OL_DUMP = os.environ.get("OL_DUMP") or "/storage/openlibrary/ol_dump_2026-07-31.txt.gz"
# Auto-find latest if not exists
if not os.path.exists(OL_DUMP):
    candidates = list(Path("/storage/openlibrary").glob("ol_dump*.txt.gz"))
    if candidates:
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        OL_DUMP = str(candidates[0])
print(f"Using OL_DUMP={OL_DUMP}", file=sys.stderr)

START_AT = "/works/OL1W"
LIMIT = 10000
OUT_SAMPLE_PARQUET = Path("sample.parquet")
OUT_SAMPLE_JSONL = Path("sample.jsonl")
OUT_EDITIONS = Path("editions_by_work.json")
OUT_AUTHORS = Path("authors.json")
OUT_WORKS = Path("works.json")
PROGRESS = Path("PROGRESS_MVP_10k.md")

USE_DUCKDB = False  # Fast fallback: python streaming; duckdb slow on 7G + ORDER BY, fallback is primary per Risk


def log_progress(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"\n[{ts}] {msg}\n"
    print(line, end="")
    with open(PROGRESS, "a") as f:
        f.write(line)


def sample_via_duckdb():
    import duckdb

    con = duckdb.connect()
    # Large line size needed — some edition JSON >2.5MB
    q = f"""
        SELECT "Key", "JSON"
        FROM read_csv(
            '{OL_DUMP}',
            delim=chr(9),
            quote=chr(8),
            header=false,
            columns={{'Type': 'VARCHAR', 'Key': 'VARCHAR', 'Rev': 'VARCHAR', 'LastModified': 'VARCHAR', 'JSON': 'VARCHAR'}},
            auto_detect=false,
            strict_mode=false,
            max_line_size=10000000
        )
        WHERE "Type" = '/type/work' AND "Key" >= '{START_AT}'
        ORDER BY "Key"
        LIMIT {LIMIT}
    """
    print(f"DuckDB query: {q[:400]}...", file=sys.stderr)
    start = time.time()
    try:
        # Try direct read_csv
        rel = con.execute(q)
        rows = rel.fetchall()
        elapsed = time.time() - start
        print(f"DuckDB fetched {len(rows)} rows in {elapsed:.2f}s", file=sys.stderr)
        return rows
    except Exception as e:
        print(f"DuckDB read_csv failed: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        raise


def sample_via_python():
    print("Falling back to Python gzip split reader...", file=sys.stderr)
    csv.field_size_limit(10 * 1024 * 1024)
    start = time.time()
    works = []
    # File is sorted by Key (field 2) globally via sort -k2,3, so scanning sequentially
    # and taking first LIMIT matches where key >= START_AT yields correct ORDER BY Key LIMIT
    # without full scan sort. We still need to skip works < START_AT.
    scanned = 0
    with gzip.open(OL_DUMP, "rt", encoding="utf-8") as f:
        for line in f:
            scanned += 1
            if scanned % 5000000 == 0:
                print(f"Scanned {scanned} lines, collected {len(works)}", file=sys.stderr)
            parts = line.rstrip("\n").split("\t", 4)
            if len(parts) != 5:
                continue
            type_, key, rev, lastmod, json_str = parts
            if type_ != "/type/work":
                continue
            if key < START_AT:
                continue
            works.append((key, json_str))
            if len(works) >= LIMIT:
                print(f"Collected LIMIT {LIMIT} at scanned {scanned}", file=sys.stderr)
                break
    # Already in file order == ORDER BY Key, so no sort needed if we broke early
    # But to be safe if we didn't guarantee, sort
    works.sort(key=lambda x: x[0])
    result = works[:LIMIT]
    elapsed = time.time() - start
    print(f"Python collected {len(result)} works in {elapsed:.2f}s (scanned {scanned} lines)", file=sys.stderr)
    return result


def python_collect_editions_authors(work_keys_set):
    """Single pass streaming to collect editions_by_work (legacy 2-pass helper)."""
    editions_by_work: dict[str, list[dict]] = {k: [] for k in work_keys_set}
    edition_count = 0
    start = time.time()
    with gzip.open(OL_DUMP, "rt", encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t", 4)
            if len(parts) != 5:
                continue
            type_, key, rev, lastmod, json_str = parts
            if type_ != "/type/edition":
                continue
            try:
                doc = orjson.loads(json_str)
            except Exception:
                try:
                    doc = json.loads(json_str)
                except Exception:
                    continue
            works = doc.get("works")
            if not works or not isinstance(works, list):
                continue
            wkey = works[0].get("key") if isinstance(works[0], dict) else None
            if wkey in work_keys_set:
                editions_by_work[wkey].append(doc)
                edition_count += 1
    elapsed = time.time() - start
    print(f"Collected {edition_count} editions for {len(work_keys_set)} works in {elapsed:.2f}s", file=sys.stderr)
    return editions_by_work


def collect_authors(author_keys):
    """Fetch authors by keys from dump (legacy)."""
    authors: dict[str, dict] = {}
    if not author_keys:
        return authors
    start = time.time()
    needed = set(author_keys)
    with gzip.open(OL_DUMP, "rt", encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t", 4)
            if len(parts) != 5:
                continue
            type_, key, rev, lastmod, json_str = parts
            if type_ != "/type/author":
                continue
            if key not in needed:
                continue
            try:
                doc = orjson.loads(json_str)
            except Exception:
                try:
                    doc = json.loads(json_str)
                except Exception:
                    continue
            authors[key] = doc
            if len(authors) == len(needed):
                break
    elapsed = time.time() - start
    print(f"Collected {len(authors)}/{len(needed)} authors in {elapsed:.2f}s", file=sys.stderr)
    return authors


def python_collect_editions_and_authors_single_pass(work_keys_set, author_keys, prefilter: bool = False):
    """Single pass: collect both editions and authors in one gzip scan.

    prefilter=True: avoid orjson for 99% of editions by string-extracting works key
                    before parsing. Only parse when wkey in set.
    """
    editions_by_work: dict[str, list[dict]] = {k: [] for k in work_keys_set}
    authors: dict[str, dict] = {}
    needed_authors = set(author_keys) if author_keys else set()
    edition_count = 0
    start = time.time()
    scanned = 0
    parsed_editions = 0
    skipped_prefilter = 0
    with gzip.open(OL_DUMP, "rt", encoding="utf-8") as f:
        for line in f:
            scanned += 1
            parts = line.rstrip("\n").split("\t", 4)
            if len(parts) != 5:
                continue
            type_, key, rev, lastmod, json_str = parts
            if type_ == "/type/edition":
                if prefilter:
                    # Fast path: string extract without JSON parse
                    # Look for '"works"' and then '/works/OL'
                    if '"works"' not in json_str:
                        skipped_prefilter += 1
                        continue
                    # Quick extract wkey via string search: find '/works/OL'
                    idx = json_str.find('"/works/OL')
                    if idx == -1:
                        # fallback to search without quote
                        idx = json_str.find("/works/OL")
                        if idx == -1:
                            skipped_prefilter += 1
                            continue
                        # extract from idx
                        end = json_str.find('"', idx)
                        if end == -1:
                            end = json_str.find("'", idx)
                        if end == -1:
                            skipped_prefilter += 1
                            continue
                        wkey_candidate = json_str[idx:end]
                    else:
                        # idx points to '"/works/OL', skip leading quote
                        idx += 1  # skip opening quote
                        end = json_str.find('"', idx)
                        if end == -1:
                            skipped_prefilter += 1
                            continue
                        wkey_candidate = json_str[idx:end]
                    if wkey_candidate not in work_keys_set:
                        skipped_prefilter += 1
                        continue
                    # Only now parse full JSON for hits
                # Parse (either prefilter hit or no prefilter)
                try:
                    doc = orjson.loads(json_str)
                    parsed_editions += 1
                except Exception:
                    try:
                        doc = json.loads(json_str)
                        parsed_editions += 1
                    except Exception:
                        continue
                works = doc.get("works")
                if not works or not isinstance(works, list):
                    continue
                wkey = works[0].get("key") if isinstance(works[0], dict) else None
                if wkey in work_keys_set:
                    editions_by_work[wkey].append(doc)
                    edition_count += 1
                elif prefilter:
                    # prefilter false positive (rare)
                    pass
            elif type_ == "/type/author" and needed_authors:
                if key in needed_authors and key not in authors:
                    try:
                        doc = orjson.loads(json_str)
                    except Exception:
                        try:
                            doc = json.loads(json_str)
                        except Exception:
                            continue
                    authors[key] = doc
    elapsed = time.time() - start
    print(
        f"Single-pass{' PREFILTER' if prefilter else ''} collected {edition_count} editions and {len(authors)}/{len(needed_authors)} authors in {elapsed:.2f}s (scanned {scanned} lines, parsed {parsed_editions}, skipped_prefilter {skipped_prefilter})",
        file=sys.stderr,
    )
    return editions_by_work, authors


def main():
    t0 = time.time()
    log_progress(f"Sample start OL_DUMP={OL_DUMP} START_AT={START_AT} LIMIT={LIMIT}")

    # Phase 1: sample works
    try:
        if USE_DUCKDB:
            rows = sample_via_duckdb()
        else:
            raise RuntimeError("skip duckdb")
    except Exception as e:
        print(f"DuckDB failed, falling back: {e}", file=sys.stderr)
        rows = sample_via_python()

    # rows is list of (Key, JSON string)
    # Ensure sort and limit (duckdb already did)
    if rows and isinstance(rows[0][1], str) and rows[0][1].startswith("{"):
        pass  # ok
    print(f"Sample got {len(rows)} works", file=sys.stderr)

    # Save sample.parquet
    try:
        import duckdb
        import pyarrow as pa
        import pyarrow.parquet as pq

        con = duckdb.connect()
        # Create parquet via python
        keys = [r[0] for r in rows]
        jsons = [r[1] for r in rows]
        table = pa.table({"Key": keys, "JSON": jsons})
        pq.write_table(table, OUT_SAMPLE_PARQUET)
        print(f"Wrote {OUT_SAMPLE_PARQUET} {len(rows)} rows", file=sys.stderr)
    except Exception as e:
        print(f"Parquet write failed: {e}", file=sys.stderr)
        # fallback jsonl
        with open(OUT_SAMPLE_JSONL, "w") as out:
            out.writelines(orjson.dumps({"key": k, "json": j}).decode() + "\n" for k, j in rows)

    # Also save works.json for transform (list of dicts)
    works_dicts = []
    work_keys_set = set()
    author_keys_all: set[str] = set()
    for k, jstr in rows:
        try:
            doc = orjson.loads(jstr)
        except Exception:
            doc = json.loads(jstr)
        works_dicts.append(doc)
        work_keys_set.add(k)
        for a in doc.get("authors", []):
            # normalize author key: a may be {author: {key: ...}} or {key:...}
            ak = None
            if isinstance(a, dict):
                if "author" in a:
                    auth = a["author"]
                    ak = auth.get("key") if isinstance(auth, dict) else auth
                elif "key" in a:
                    ak = a["key"]
            if ak:
                author_keys_all.add(ak)

    with open(OUT_WORKS, "wb") as f:
        f.write(orjson.dumps(works_dicts))

    print(f"Works dicts {len(works_dicts)}, author keys from works: {len(author_keys_all)}", file=sys.stderr)

    # Phase 2+3: single-pass vs two-pass (toggled via SINGLE_PASS env)
    use_single = os.environ.get("SINGLE_PASS", "1") == "1"
    use_prefilter = os.environ.get("PREFILTER", "1") == "1"
    if use_single:
        print(f"Using SINGLE-PASS for editions+authors... prefilter={use_prefilter}", file=sys.stderr)
        t_ed = time.time()
        editions_by_work, authors = python_collect_editions_and_authors_single_pass(work_keys_set, author_keys_all, prefilter=use_prefilter)
        print(f"Single-pass phase took {time.time() - t_ed:.2f}s", file=sys.stderr)
    else:
        print("Using TWO-PASS (legacy)...", file=sys.stderr)
        editions_by_work = python_collect_editions_authors(work_keys_set)
        authors = collect_authors(author_keys_all)

    with open(OUT_EDITIONS, "wb") as f:
        f.write(orjson.dumps({k: v for k, v in editions_by_work.items()}))
    total_editions = sum(len(v) for v in editions_by_work.values())
    print(f"Total editions collected: {total_editions}", file=sys.stderr)

    with open(OUT_AUTHORS, "wb") as f:
        f.write(orjson.dumps(authors))
    print(f"Authors collected: {len(authors)}", file=sys.stderr)

    elapsed = time.time() - t0
    # Log to progress
    msg = f"Sample done: works={len(works_dicts)} editions={total_editions} authors={len(authors)} elapsed={elapsed:.2f}s OL_DUMP={OL_DUMP}"
    print(msg, file=sys.stderr)
    log_progress(msg)
    # Also write summary counts
    with open(PROGRESS, "a") as f:
        f.write(f"- Works: {len(works_dicts)}\n- Editions: {total_editions}\n- Authors: {len(authors)}\n- Sample parquet: {OUT_SAMPLE_PARQUET}\n")


if __name__ == "__main__":
    main()
