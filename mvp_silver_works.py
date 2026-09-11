#!/usr/bin/env python3
"""Build silver works with author_keys array"""

import time
from pathlib import Path

import duckdb

BRONZE = "lake/bronze/works.parquet"
SILVER = "lake/silver/works.parquet"
Path(SILVER).unlink(missing_ok=True)
con = duckdb.connect()
con.execute("PRAGMA memory_limit='6GB'")
print("Building silver works with author_keys")
t0 = time.time()
con.execute(f"""
COPY (
  SELECT
    *,
    json_extract(JSON, '$.authors[*].author.key') as author_keys_json,
    -- also try string array via json_extract_string?
    CAST(json_extract(JSON, '$.authors[*].author.key') AS VARCHAR[]) as author_keys
  FROM '{BRONZE}'
) TO '{SILVER}' (FORMAT PARQUET, COMPRESSION ZSTD)
""")
print(f"Done in {time.time() - t0:.1f}s size {Path(SILVER).stat().st_size / 1e9:.2f}GB")
# Test query speed
for label, q in [
    ("bronze authors via temp table", f"SELECT count(*) FROM '{BRONZE}' WHERE Key >= '/works/OL1W' ORDER BY Key LIMIT 10000"),
]:
    pass
# Bench authors join with silver
t1 = time.time()
# Old: need to extract author_keys per work then join authors
# New: use silver author_keys array to directly filter authors: SELECT a.JSON FROM 'lake/bronze/authors.parquet' a WHERE a.Key IN (SELECT UNNEST(author_keys) FROM 'lake/silver/works.parquet' WHERE Key >= '/works/OL1W' ORDER BY Key LIMIT 10000)
cnt = con.execute(f"""
SELECT count(*) FROM 'lake/bronze/authors.parquet' a
WHERE a.Key IN (SELECT unnest(author_keys) FROM '{SILVER}' WHERE Key >= '/works/OL1W' ORDER BY Key LIMIT 10000)
""").fetchone()[0]
print(f"Silver author_keys join count {cnt} in {time.time() - t1:.2f}s")
# Compare baseline 6.72s
t1 = time.time()
# baseline via python extraction + temp table (simulate)
import orjson

rows = con.execute(f"SELECT JSON FROM '{BRONZE}' WHERE Key >= '/works/OL1W' ORDER BY Key LIMIT 10000").fetchall()
author_keys = set()
for r in rows:
    j = orjson.loads(r[0])
    for a in j.get("authors", []):
        ak = a.get("author", {}).get("key") if isinstance(a.get("author"), dict) else a.get("author")
        if not ak and "key" in a:
            ak = a["key"]
        if ak:
            author_keys.add(ak)
print(f"Python extract {len(author_keys)} in {time.time() - t1:.2f}s")
