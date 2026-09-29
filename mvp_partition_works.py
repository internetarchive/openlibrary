"""One-time: partition bronze works by numeric OLID bucket (id//100000) matching
lake/silver/editions_bucketed layout, adding an `id` BIGINT column so runtime
queries are pure `WHERE id BETWEEN lo AND hi` (zonemap-prunable, no regex).

Also emits lake/silver/chunks_{SIZE}.json with deterministic contiguous chunk
boundaries {n, lo, hi} so every chunk maps to a contiguous bucket range.

Usage: python3 mvp_partition_works.py [CHUNK_SIZE=20000]
"""

import os
import re
import sys
import time

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq


def _valid_parquet(p):
    try:
        pq.ParquetFile(p).metadata
        return True
    except Exception:
        return False


SRC = "lake/silver/works.parquet" if os.path.exists("lake/silver/works.parquet") and _valid_parquet("lake/silver/works.parquet") else "lake/bronze/works.parquet"
OUT = "lake/silver/works_bucketed"
os.makedirs(OUT, exist_ok=True)

CHUNK = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
RE_OLID = re.compile(r"OL(\d+)W")

pf = pq.ParquetFile(SRC)
print(f"src {SRC} row_groups {pf.num_row_groups} rows {pf.metadata.num_rows}")

t0 = time.time()
all_ids = []  # numpy chunks appended
counts = {}
for rg in range(pf.num_row_groups):
    tbl = pf.read_row_group(rg, columns=["Key", "JSON"])
    keys = tbl.column("Key").to_pylist()
    ids = []
    keep_idx = []
    for i, k in enumerate(keys):
        m = RE_OLID.search(k)
        if m:
            ids.append(int(m.group(1)))
            keep_idx.append(i)
    if not keep_idx:
        continue
    ids_arr = np.asarray(ids, dtype=np.int64)
    all_ids.append(ids_arr)
    sub = tbl.take(keep_idx)
    sub = sub.append_column("id", pa.array(ids, type=pa.int64()))
    # split this row group across buckets
    buckets = ids_arr // 100000
    order = np.argsort(buckets, kind="stable")
    buckets_sorted = buckets[order]
    # boundaries where bucket value changes
    change = np.flatnonzero(np.diff(buckets_sorted)) + 1
    groups = np.split(order, change)
    written_this_rg = 0
    for g in groups:
        # g holds ORIGINAL row positions; all share bucket of any member
        b = int(buckets[g[0]])
        assert int(buckets_sorted[0]) <= b  # sanity
        bdir = os.path.join(OUT, f"bucket={b}")
        os.makedirs(bdir, exist_ok=True)
        out_path = os.path.join(bdir, f"part-{rg:03d}-{b:03d}.parquet")
        pq.write_table(sub.take(g), out_path, compression="zstd", compression_level=3)
        written_this_rg += len(g)
    assert written_this_rg == tbl.num_rows, f"rg {rg}: wrote {written_this_rg} != {tbl.num_rows}"
    if rg % 20 == 0:
        print(f"rg {rg}/{pf.num_row_groups} elapsed {time.time() - t0:.0f}s buckets {len(counts)}", flush=True)

ids_all = np.sort(np.concatenate(all_ids))
print(f"total ids {len(ids_all)} unique {len(np.unique(ids_all))} in {time.time() - t0:.0f}s")

# chunk boundaries over sorted unique ids
uniq = np.unique(ids_all)
chunks = []
for i in range(0, len(uniq), CHUNK):
    part = uniq[i : i + CHUNK]
    chunks.append({"n": len(part), "lo": int(part[0]), "hi": int(part[-1])})
out_json = f"lake/silver/chunks_{CHUNK}.json"
with open(out_json, "w") as f:
    import json

    json.dump(chunks, f)
print(f"wrote {out_json}: {len(chunks)} chunks; first {chunks[0]} last {chunks[-1]}")
print(f"buckets written: {len(counts)}")
