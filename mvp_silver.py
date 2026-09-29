#!/usr/bin/env python3
"""
mvp_silver.py — Build silver layer from bronze parquet lake
Bronze: lake/bronze/{works,editions,authors}.parquet (raw dump)
Silver: lake/silver/{works,editions,authors}.parquet (+ derived columns)

Currently: editions.work_key = json_extract_string(JSON, '$.works[0].key')
          (enables WHERE work_key IN (...) string hash-join vs 30s JSON parse)

Run: .venv/bin/python mvp_silver.py
Rerun: same command (overwrites), or SINGLE_TABLE=editions .venv/bin/python mvp_silver.py
Time: ~10-12m for editions 18.9M rows (4.3G -> ~0.5G + column)
"""

import os
import time
from pathlib import Path

import duckdb

BRONZE = Path("lake/bronze")
SILVER = Path("lake/silver")
SILVER.mkdir(parents=True, exist_ok=True)


def build_editions():
    out = SILVER / "editions.parquet"
    # Remove incomplete file if exists
    if out.exists():
        print(f"Removing existing {out}")
        out.unlink()
    con = duckdb.connect()
    # Use larger temp memory
    con.execute("PRAGMA memory_limit='6GB'")
    print(f"Building silver editions -> {out} from {BRONZE / 'editions.parquet'}")
    t0 = time.time()
    # Use COPY with JSON extract; compression ZSTD for size/speed
    con.execute(f"""
        COPY (
          SELECT
            *,
            json_extract_string(JSON, '$.works[0].key') AS work_key
          FROM '{BRONZE / "editions.parquet"}'
        ) TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    elapsed = time.time() - t0
    size = out.stat().st_size / 1e9
    print(f"Done silver editions {elapsed:.1f}s size {size:.2f} GB")
    # Verify
    cnt = con.execute(f"SELECT count(*) FROM '{out}'").fetchone()[0]
    nulls = con.execute(f"SELECT count(*) FROM '{out}' WHERE work_key IS NULL").fetchone()[0]
    print(f"Rows {cnt}, work_key nulls {nulls} ({100 * nulls / cnt:.1f}% orphans)")
    return out


def build_works():
    # Silver works: add author_keys array for faster author join if needed
    # Keep simple: just copy bronze works as silver for now (no extra cols needed for 10k)
    # Could add: json_extract(JSON, '$.authors[*].author.key') as author_keys
    out = SILVER / "works.parquet"
    if out.exists():
        print(f"Silver works exists {out}, skipping (delete to rebuild)")
        return out
    import shutil

    src = BRONZE / "works.parquet"
    print(f"Copying works bronze -> silver (no transform) {src} -> {out}")
    shutil.copy(src, out)
    print("Done works silver")
    return out


def main():
    single = os.environ.get("SINGLE_TABLE")
    t0 = time.time()
    if single == "editions" or not single:
        build_editions()
    if single == "works" or not single:
        build_works()
    print(f"Silver build total {time.time() - t0:.1f}s")
    # Quick bench vs bronze
    con = duckdb.connect()
    for label, q in [
        (
            "bronze json_extract",
            "SELECT count(*) FROM 'lake/bronze/editions.parquet' WHERE json_extract_string(JSON, '$.works[0].key') IN (SELECT Key FROM 'lake/bronze/works.parquet' WHERE Key >= '/works/OL1W' ORDER BY Key LIMIT 10000)",
        ),
        (
            "silver work_key",
            "SELECT count(*) FROM 'lake/silver/editions.parquet' WHERE work_key IN (SELECT Key FROM 'lake/bronze/works.parquet' WHERE Key >= '/works/OL1W' ORDER BY Key LIMIT 10000)",
        ),
        (
            "silver join",
            "SELECT count(*) FROM 'lake/silver/editions.parquet' e JOIN (SELECT Key FROM 'lake/bronze/works.parquet' WHERE Key >= '/works/OL1W' ORDER BY Key LIMIT 10000) s ON e.work_key = s.Key",
        ),
    ]:
        try:
            t1 = time.time()
            cnt = con.execute(q).fetchone()[0]
            print(f"{label}: {cnt} in {time.time() - t1:.2f}s")
        except Exception as e:
            print(f"{label} failed: {e}")


if __name__ == "__main__":
    main()
