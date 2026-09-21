#!/usr/bin/env python3
"""
mvp_bronze.py — One-time convert ol_dump TSV gz -> parquet lake partitioned by Type
Inputs: /storage/openlibrary/ol_dump_2026-07-31.txt.gz (7.1G)
Outputs: lake/bronze/{type}.parquet  (e.g. works.parquet, editions.parquet, authors.parquet, other.parquet)
         Also lake/bronze/_meta.json with counts/timings

Streams via gzip + pyarrow ParquetWriter, batch 100k, no DuckDB ORDER BY.
Handles large lines (10M) via split("\t",4).
"""

import gzip
import json
import os
import time
from collections import defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

OL_DUMP = os.environ.get("OL_DUMP", "/storage/openlibrary/ol_dump_2026-07-31.txt.gz")
OUT_DIR = Path("lake/bronze")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Map Type -> writer and buffer
# Types we partition: work, edition, author, redirect, delete, list, other
TYPE_MAP = {
    "/type/work": "works.parquet",
    "/type/edition": "editions.parquet",
    "/type/author": "authors.parquet",
    "/type/redirect": "redirects.parquet",
    "/type/delete": "deletes.parquet",
    "/type/list": "lists.parquet",
}
BATCH = 100_000

schema = pa.schema(
    [
        ("Type", pa.string()),
        ("Key", pa.string()),
        ("Rev", pa.int32()),
        ("LastModified", pa.string()),
        ("JSON", pa.string()),
    ]
)


def main():
    t0 = time.time()
    writers = {}
    buffers = defaultdict(list)
    counts = defaultdict(int)
    total = 0

    # init writers lazily
    def get_writer(fname):
        if fname not in writers:
            path = OUT_DIR / fname
            writers[fname] = pq.ParquetWriter(path, schema, compression="zstd", compression_level=3)
            print(f"Opened writer {path}")
        return writers[fname]

    with gzip.open(OL_DUMP, "rt", encoding="utf-8") as f:
        for line in f:
            total += 1
            if total % 5_000_000 == 0:
                print(f"Scanned {total} lines, elapsed {time.time() - t0:.1f}s")
            parts = line.rstrip("\n").split("\t", 4)
            if len(parts) != 5:
                continue
            typ, key, rev, lastmod, j = parts
            fname = TYPE_MAP.get(typ, "other.parquet")
            # try int rev
            try:
                rev_i = int(rev)
            except:
                rev_i = 0
            buffers[fname].append((typ, key, rev_i, lastmod, j))
            counts[fname] += 1
            if len(buffers[fname]) >= BATCH:
                # flush
                cols = list(zip(*buffers[fname]))
                table = pa.table(
                    {
                        "Type": cols[0],
                        "Key": cols[1],
                        "Rev": cols[2],
                        "LastModified": cols[3],
                        "JSON": cols[4],
                    },
                    schema=schema,
                )
                get_writer(fname).write_table(table)
                buffers[fname].clear()
                if total % 1_000_000 == 0:
                    print(f"  flushed {fname} total {counts[fname]}")

    # flush remaining
    for fname, buf in buffers.items():
        if buf:
            cols = list(zip(*buf))
            table = pa.table(
                {
                    "Type": cols[0],
                    "Key": cols[1],
                    "Rev": cols[2],
                    "LastModified": cols[3],
                    "JSON": cols[4],
                },
                schema=schema,
            )
            get_writer(fname).write_table(table)
            print(f"Final flush {fname} {len(buf)}")

    for w in writers.values():
        w.close()

    elapsed = time.time() - t0
    print(f"Done scanned {total} lines in {elapsed:.1f}s")
    for fname, cnt in counts.items():
        path = OUT_DIR / fname
        size = path.stat().st_size if path.exists() else 0
        print(f"{fname}: {cnt} rows, {size / 1e6:.1f} MB")

    meta = {"total": total, "counts": dict(counts), "elapsed": elapsed, "dump": OL_DUMP}
    with open(OUT_DIR / "_meta.json", "w") as out:
        json.dump(meta, out, indent=2)


if __name__ == "__main__":
    main()
