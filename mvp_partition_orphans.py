#!/usr/bin/env python3
"""
mvp_partition_orphans.py — One-time: bucket orphan editions (work_key IS NULL in silver) by numeric
OLID//100000 so rust_solr chunk mode can read them zonemap-pruned, mirroring editions_bucketed.

Orphan editions (no linked work) are indexed by production as standalone fake works (/works/OLxxxM);
without this set they silently drop out of rust full rebuilds.

Output: <silver-dir>/orphans_bucketed/bucket=N/data.parquet (columns work_key, JSON, id, bucket)

Usage:
  .venv/bin/python mvp_partition_orphans.py \
    --silver /mnt/HC_Volume_106672133/openlibrary/lake_full/silver
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import duckdb


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--silver", default="/mnt/HC_Volume_106672133/openlibrary/lake_full/silver")
    ap.add_argument("--batch-size", type=int, default=100_000_000)
    args = ap.parse_args()

    silver = Path(args.silver)
    src = silver / "editions.parquet"
    out = silver / "orphans_bucketed"
    t0 = time.time()

    con = duckdb.connect()
    total, orphans = con.execute(f"SELECT count(*), count_if(work_key IS NULL) FROM '{src}'").fetchone()
    print(f"silver editions: {total:,} rows, {orphans:,} orphans")

    con.execute("SET memory_limit='4GB'")
    con.execute("SET preserve_insertion_order=false")
    con.execute(
        f"""
        COPY (
            SELECT
                work_key,
                JSON,
                CAST(regexp_extract(Key, '^/books/OL(\\d+)M$', 1) AS BIGINT) AS id,
                CAST(CAST(regexp_extract(Key, '^/books/OL(\\d+)M$', 1) AS BIGINT) / 100000 AS BIGINT) AS bucket
            FROM '{src}'
            WHERE work_key IS NULL AND regexp_matches(Key, '^/books/OL\\d+M$')
        ) TO '{out}' (FORMAT PARQUET, PARTITION_BY (bucket), OVERWRITE_OR_IGNORE, COMPRESSION ZSTD)
        """
    )
    n_buckets = len(list(out.glob("bucket=*")))
    print(f"Wrote {n_buckets} buckets to {out} in {time.time() - t0:.0f}s")

    # any orphans we skipped (non-numeric keys, e.g. /books/ia:xxx)?
    skipped = con.execute(
        f"""
        SELECT count(*) FROM '{src}'
        WHERE work_key IS NULL AND NOT regexp_matches(Key, '^/books/OL\\d+M$')
        """
    ).fetchone()[0]
    print(f"Skipped {skipped:,} non-numeric-key orphans (e.g. /books/ia:*)")


if __name__ == "__main__":
    main()
