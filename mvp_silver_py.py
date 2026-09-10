#!/usr/bin/env python3
"""
mvp_silver_py.py — Build silver editions.work_key via pyarrow streaming (more robust than DuckDB COPY)
Reads lake/bronze/editions.parquet batches, extracts work_key via orjson, writes lake/silver/editions.parquet
"""

import json
import time
from pathlib import Path

import orjson
import pyarrow as pa
import pyarrow.parquet as pq

BRONZE = Path("lake/bronze/editions.parquet")
SILVER = Path("lake/silver/editions.parquet")
SILVER.parent.mkdir(parents=True, exist_ok=True)


def extract_work_key(json_str):
    # Fast prefilter then orjson
    if '"works"' not in json_str:
        return None
    # Quick string find for /works/OL
    idx = json_str.find('"/works/OL')
    if idx == -1:
        idx = json_str.find("/works/OL")
        if idx == -1:
            return None
        # fallback parse
    try:
        doc = orjson.loads(json_str)
    except:
        try:
            doc = json.loads(json_str)
        except:
            return None
    works = doc.get("works")
    if not works or not isinstance(works, list):
        return None
    w = works[0]
    if isinstance(w, dict):
        return w.get("key")
    return None


def main():
    print(f"Reading {BRONZE}")
    pf = pq.ParquetFile(BRONZE)
    total_rows = pf.metadata.num_rows
    print(f"Total rows {total_rows}, row_groups {pf.num_row_groups}")
    t0 = time.time()
    writer = None
    schema = None
    written = 0
    for rg in range(pf.num_row_groups):
        batch = pf.read_row_group(rg, columns=["Type", "Key", "Rev", "LastModified", "JSON"])
        # batch is Table
        # Extract work_key
        json_col = batch.column("JSON").to_pylist()
        work_keys = [extract_work_key(j) for j in json_col]
        # Add column
        table = batch.append_column("work_key", pa.array(work_keys, type=pa.string()))
        if writer is None:
            schema = table.schema
            writer = pq.ParquetWriter(SILVER, schema, compression="zstd", compression_level=3)
            print(f"Writer schema {schema}")
        writer.write_table(table)
        written += len(table)
        if rg % 20 == 0:
            print(f"RG {rg}/{pf.num_row_groups} written {written} elapsed {time.time() - t0:.1f}s")
    if writer:
        writer.close()
    elapsed = time.time() - t0
    print(f"Done written {written} in {elapsed:.1f}s size {SILVER.stat().st_size / 1e9:.2f}GB")
    # Verify
    import duckdb

    con = duckdb.connect()
    cnt = con.execute(f"SELECT count(*) FROM '{SILVER}'").fetchone()[0]
    print(f"Verify count {cnt}")


if __name__ == "__main__":
    main()
