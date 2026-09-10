#!/usr/bin/env python3
"""mvp_gold_A.py — Single denormalized query test A"""

import time

import duckdb
import orjson

BRONZE_WORKS = "lake/bronze/works.parquet"
SILVER_EDITIONS = "lake/silver/editions.parquet"
BRONZE_AUTHORS = "lake/bronze/authors.parquet"
LIMIT = 10000
START_AT = "/works/OL1W"


def baseline_3_queries():
    con = duckdb.connect()
    t0 = time.time()
    rows = con.execute(f"SELECT Key, JSON FROM '{BRONZE_WORKS}' WHERE Key >= '{START_AT}' ORDER BY Key LIMIT {LIMIT}").fetchall()
    t1 = time.time()
    edition_rows = con.execute(
        f"SELECT e.JSON FROM '{SILVER_EDITIONS}' e JOIN (SELECT Key FROM '{BRONZE_WORKS}' WHERE Key >= '{START_AT}' ORDER BY Key LIMIT {LIMIT}) s ON e.work_key = s.Key"
    ).fetchall()
    t2 = time.time()
    # authors need keys from works
    works = [orjson.loads(r[1]) for r in rows]
    author_keys = set()
    for w in works:
        for a in w.get("authors", []):
            ak = a.get("author", {}).get("key") if isinstance(a.get("author"), dict) else a.get("author")
            if not ak and "key" in a:
                ak = a["key"]
            if ak:
                author_keys.add(ak)
    con2 = duckdb.connect()
    con2.execute("CREATE TEMP TABLE ak (Key VARCHAR)")
    con2.executemany("INSERT INTO ak VALUES (?)", [(k,) for k in author_keys])
    author_rows = con2.execute(f"SELECT a.JSON FROM '{BRONZE_AUTHORS}' a JOIN ak ON a.Key = ak.Key").fetchall()
    t3 = time.time()
    print(
        f"Baseline 3 queries: works {t1 - t0:.2f}s editions {t2 - t1:.2f}s authors {t3 - t2:.2f}s total {t3 - t0:.2f}s rows {len(rows)}/{len(edition_rows)}/{len(author_rows)}"
    )
    return t3 - t0


def single_query():
    con = duckdb.connect()
    t0 = time.time()
    # Single query: works + editions aggregated
    q = f"""
    WITH sample AS (
      SELECT Key, JSON as work_json FROM '{BRONZE_WORKS}' WHERE Key >= '{START_AT}' ORDER BY Key LIMIT {LIMIT}
    )
    SELECT
      s.Key,
      s.work_json,
      list(e.JSON) as editions_json
    FROM sample s
    LEFT JOIN '{SILVER_EDITIONS}' e ON e.work_key = s.Key
    GROUP BY s.Key, s.work_json
    ORDER BY s.Key
    """
    rows = con.execute(q).fetchall()
    t1 = time.time()
    print(f"Single query (works+editions) {len(rows)} in {t1 - t0:.2f}s")
    # Need also authors, but we can do second query for authors aggregated similarly or include in same?
    # Try full 1 query with authors via lateral join
    q2 = f"""
    WITH sample AS (
      SELECT Key, JSON as work_json, json_extract_string(JSON, '$.authors[0].author.key') as ak1, json_extract_string(JSON, '$.authors[1].author.key') as ak2
      FROM '{BRONZE_WORKS}' WHERE Key >= '{START_AT}' ORDER BY Key LIMIT {LIMIT}
    )
    SELECT s.Key, s.work_json, list(e.JSON) as editions_json
    FROM sample s
    LEFT JOIN '{SILVER_EDITIONS}' e ON e.work_key = s.Key
    GROUP BY s.Key, s.work_json
    """
    t2 = time.time()
    rows2 = con.execute(q2).fetchall()
    print(f"Single query v2 {len(rows2)} in {time.time() - t2:.2f}s")
    return t1 - t0


if __name__ == "__main__":
    b = baseline_3_queries()
    s = single_query()
    print(f"A speedup vs baseline 3-query total {b:.2f}s -> single {s:.2f}s = {b / s:.2f}x")
