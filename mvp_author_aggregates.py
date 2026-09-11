#!/usr/bin/env python3
"""
mvp_author_aggregates.py — Compute author rollups (top_work, work_count, top_subjects, ratings +
reading-log sums) lake-side with DuckDB and push them onto author docs via atomic {"set":} updates.

Mirrors AuthorSolrUpdater (openlibrary/solr/updater/author.py):
  q=author_key:<id>, fq=type:work, sort=edition_count desc, fl=title,subtitle
  facet sums: ratings_count_1..5, readinglog/want/currently/already/stopped
  facet terms per field (limit 10, count desc then term ASC): subject/time/person/place facets
AuthorSolrBuilder: top_work = docs[0].title (+": "+subtitle); top_subjects = global (count,val) DESC
top-10 over the four fields' bucket lists; ratings via Ratings.work_ratings_summary_from_counts;
numeric facet sums always present (zeros included), matching Solr facet semantics.

Memory strategy: gold is processed in small batches of part files (the box can't hold the full
author-x-facet cross product); per-batch partial aggregates land in an on-disk duckdb DB, then a
light final pass merges them. Run AFTER gold load + ratings/reading_log passes.

Usage:
  .venv/bin/python mvp_author_aggregates.py --validate 300     # vs real AuthorSolrUpdater @ --solr
  .venv/bin/python mvp_author_aggregates.py                    # full run (15.4M authors)
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import math
import os
import time

import duckdb
import httpx
import orjson
import pyarrow as pa
import pyarrow.parquet as pq

SUBJECT_FACETS = ["subject_facet", "time_facet", "person_facet", "place_facet"]


def compute_sortable_rating(counts: list[int]) -> float:
    """Exact port of Ratings.compute_sortable_rating (openlibrary/core/ratings.py:117)."""
    n = counts
    total = sum(n, 0)
    k_n = len(n)
    z = 1.65
    mean = sum(((k + 1) * (n_k + 1) / (total + k_n) for k, n_k in enumerate(n)), 0)
    second_moment = sum((((k + 1) ** 2) * (n_k + 1) / (total + k_n) for k, n_k in enumerate(n)), 0)
    return mean - z * math.sqrt((second_moment - mean**2) / (total + k_n + 1))


def ratings_summary_from_counts(counts: list[int]) -> dict:
    """Port of Ratings.work_ratings_summary_from_counts."""
    total = sum(counts, 0)
    average = (sum((k * c for k, c in enumerate(counts, 1)), 0) / total) if total != 0 else 0
    return {
        "ratings_average": average,
        "ratings_sortable": compute_sortable_rating(counts),
        "ratings_count": total,
        "ratings_count_1": counts[0],
        "ratings_count_2": counts[1],
        "ratings_count_3": counts[2],
        "ratings_count_4": counts[3],
        "ratings_count_5": counts[4],
    }


def tune(con: duckdb.DuckDBPyConnection):
    con.execute("SET temp_directory='/mnt/HC_Volume_106672133/openlibrary/tmp_duckdb'")
    con.execute("SET memory_limit='6GB'")
    con.execute("SET preserve_insertion_order=false")
    con.execute("SET threads=4")


SLIM_SCHEMA_WA = pa.schema(
    [
        ("wkey", pa.string()),
        ("akey", pa.string()),
        ("ec", pa.int64()),
        ("title", pa.string()),
        ("subtitle", pa.string()),
        ("is_fake", pa.bool_()),
    ]
)
SLIM_SCHEMA_F = pa.schema([("wkey", pa.string()), ("fld", pa.string()), ("val", pa.string())])


def rows_to_table(rows, schema):
    cols = list(zip(*rows))
    return pa.Table.from_arrays([pa.array(c, type=f.type) for c, f in zip(cols, schema)], schema=schema)


def stream_slim(gold_files: list[str], out_dir: str):
    """One streaming pass over gold parts -> slim sidecar parquets (no giant-JSON ops in DuckDB).

    Facet values are de-duplicated per (work, field): Solr terms-facet counts are document
    frequencies, not array-occurrence counts.
    """
    import os

    wa_dir, f_dir = os.path.join(out_dir, "wa"), os.path.join(out_dir, "facets")
    os.makedirs(wa_dir, exist_ok=True)
    os.makedirs(f_dir, exist_ok=True)

    t0 = time.time()
    n_parts = len(gold_files)
    wa_writer = pq.ParquetWriter(os.path.join(wa_dir, "slim.parquet"), SLIM_SCHEMA_WA, compression="zstd")
    f_writer = pq.ParquetWriter(os.path.join(f_dir, "slim.parquet"), SLIM_SCHEMA_F, compression="zstd")
    fields = [("subject_facet", SUBJECT_FACETS[0]), ("time_facet", SUBJECT_FACETS[1]), ("person_facet", SUBJECT_FACETS[2]), ("place_facet", SUBJECT_FACETS[3])]
    try:
        for i, part in enumerate(gold_files):
            pf = pq.ParquetFile(part)
            wa_buf, f_buf = [], []
            for batch in pf.iter_batches(batch_size=2000, columns=["key", "doc_json"]):
                keys = batch.column(0).to_pylist()
                docs = batch.column(1).to_pylist()
                for k, dj in zip(keys, docs):
                    if not dj:
                        continue
                    d = orjson.loads(dj)
                    aks = d.get("author_key") or []
                    ec = d.get("edition_count") or 0
                    title = d.get("title")
                    sub = d.get("subtitle")
                    fake = k.endswith("M")
                    for ak in aks:
                        wa_buf.append((k, ak, ec, title, sub, fake))
                    for src_field, fld in fields:
                        vals = d.get(src_field)
                        if not vals:
                            continue
                        for v in dict.fromkeys(vals):
                            if v:
                                f_buf.append((k, fld, v))
                if len(wa_buf) >= 200_000:
                    wa_writer.write_table(rows_to_table(wa_buf, SLIM_SCHEMA_WA))
                    wa_buf = []
                if len(f_buf) >= 400_000:
                    f_writer.write_table(rows_to_table(f_buf, SLIM_SCHEMA_F))
                    f_buf = []
            if wa_buf:
                wa_writer.write_table(rows_to_table(wa_buf, SLIM_SCHEMA_WA))
            if f_buf:
                f_writer.write_table(rows_to_table(f_buf, SLIM_SCHEMA_F))
            if (i + 1) % 100 == 0:
                rate = (i + 1) / max(time.time() - t0, 0.001)
                print(f"  [slim] {i + 1:,}/{n_parts:,} parts ({rate:.1f} parts/s)", flush=True)
    finally:
        wa_writer.close()
        f_writer.close()
    print(f"[slim] done in {(time.time() - t0) / 60:.1f}m", flush=True)


def build_from_slim(con: duckdb.DuckDBPyConnection, slim_dir: str, ratings: str, reading_log: str, authors_parquet: str):
    t0 = time.time()
    wa_glob = f"'{slim_dir}/wa/*.parquet'"
    f_glob = f"'{slim_dir}/facets/*.parquet'"
    NP = 12

    # top_work winner + work_count per author (partition by author hash)
    con.execute("CREATE OR REPLACE TEMP TABLE f_top(akey VARCHAR, wkey VARCHAR, title VARCHAR, subtitle VARCHAR)")
    con.execute("CREATE OR REPLACE TEMP TABLE f_wc(akey VARCHAR, work_count BIGINT)")
    for p in range(NP):
        con.execute(
            f"""
            INSERT INTO f_top
            SELECT akey, wkey, title, subtitle FROM (
                SELECT akey, wkey, any_value(title) AS title, any_value(subtitle) AS subtitle,
                       row_number() OVER (PARTITION BY akey ORDER BY max(ec) DESC, wkey ASC) AS rn
                FROM read_parquet([{wa_glob}])
                WHERE hash(akey) % {NP} = {p}
                GROUP BY akey, wkey
            ) WHERE rn = 1
            """
        )
        con.execute(
            f"""
            INSERT INTO f_wc
            SELECT akey, count(DISTINCT wkey) FROM read_parquet([{wa_glob}]) WHERE hash(akey) % {NP} = {p} GROUP BY akey
            """
        )
    print(f"    [f_top/f_wc x{NP} passes]", flush=True)

    # subject facets: partitioned cross+count, then per-author top-10 pipeline (also partitioned)
    con.execute("CREATE OR REPLACE TEMP TABLE f_subj_raw(akey VARCHAR, fld VARCHAR, val VARCHAR, c BIGINT)")
    for p in range(NP):
        con.execute(
            f"""
            INSERT INTO f_subj_raw
            SELECT u.akey, s.fld, s.val, count(*) AS c
            FROM read_parquet([{f_glob}]) s
            JOIN (SELECT DISTINCT wkey, akey FROM read_parquet([{wa_glob}]) WHERE hash(wkey) % {NP} = {p}) u USING (wkey)
            WHERE s.val IS NOT NULL AND hash(s.wkey) % {NP} = {p}
            GROUP BY 1, 2, 3
            """
        )
        print(f"    [f_subj pass {p + 1}/{NP}]", flush=True)
    con.execute("CREATE OR REPLACE TEMP TABLE f_subj(akey VARCHAR, top_subjects VARCHAR[])")
    for p in range(NP):
        # Faithful port of AuthorSolrBuilder.top_subjects: candidates are each field's top-10
        # buckets with their OWN counts (no cross-field dedup -> values can repeat, e.g.
        # 'United States' via subject_facet AND place_facet); global sort (count,val) DESC; top 10.
        con.execute(
            f"""
            INSERT INTO f_subj
            WITH vc AS (
                SELECT akey, fld, val, sum(c) AS c FROM f_subj_raw WHERE hash(akey) % {NP} = {p} GROUP BY 1, 2, 3
            ),
            per_field AS (
                SELECT akey, fld, val, c FROM (
                    SELECT akey, fld, val, c, row_number() OVER (PARTITION BY akey, fld ORDER BY c DESC, val ASC) AS rn
                    FROM vc
                ) WHERE rn <= 10
            ),
            ranked AS (
                SELECT akey, val, row_number() OVER (PARTITION BY akey ORDER BY c DESC, val DESC) AS rn
                FROM per_field
            )
            SELECT akey, list(val ORDER BY rn) FROM ranked WHERE rn <= 10 GROUP BY akey
            """
        )
        print(f"    [f_subj rank {p + 1}/{NP}]", flush=True)

    # ratings / reading-log sums (partitioned by work hash on the pair build side)
    con.execute("CREATE OR REPLACE TEMP TABLE f_rat(akey VARCHAR, rc1 BIGINT, rc2 BIGINT, rc3 BIGINT, rc4 BIGINT, rc5 BIGINT)")
    con.execute("CREATE OR REPLACE TEMP TABLE f_rl(akey VARCHAR, want BIGINT, curr BIGINT, already BIGINT, stopped BIGINT)")
    for p in range(NP):
        con.execute(
            f"""
            INSERT INTO f_rat
            WITH wrk AS (
                SELECT WorkKey,
                       count(*) FILTER (WHERE Rating = 1) AS rc1, count(*) FILTER (WHERE Rating = 2) AS rc2,
                       count(*) FILTER (WHERE Rating = 3) AS rc3, count(*) FILTER (WHERE Rating = 4) AS rc4,
                       count(*) FILTER (WHERE Rating = 5) AS rc5
                FROM '{ratings}' GROUP BY WorkKey
            )
            SELECT u.akey, sum(rc1), sum(rc2), sum(rc3), sum(rc4), sum(rc5)
            FROM wrk r JOIN (SELECT DISTINCT wkey, akey FROM read_parquet([{wa_glob}]) WHERE hash(wkey) % {NP} = {p}) u ON r.WorkKey = u.wkey
            GROUP BY 1
            """
        )
        con.execute(
            f"""
            INSERT INTO f_rl
            WITH wrk AS (
                SELECT WorkKey,
                       count(*) FILTER (WHERE Shelf = 'Want to Read') AS want,
                       count(*) FILTER (WHERE Shelf = 'Currently Reading') AS curr,
                       count(*) FILTER (WHERE Shelf = 'Already Read') AS already,
                       count(*) FILTER (WHERE Shelf = 'Stopped Reading') AS stopped
                FROM '{reading_log}' GROUP BY WorkKey
            )
            SELECT u.akey, sum(want), sum(curr), sum(already), sum(stopped)
            FROM wrk r JOIN (SELECT DISTINCT wkey, akey FROM read_parquet([{wa_glob}]) WHERE hash(wkey) % {NP} = {p}) u ON r.WorkKey = u.wkey
            GROUP BY 1
            """
        )
        print(f"    [f_rat/f_rl pass {p + 1}/{NP}]", flush=True)

    # collapse per-work-partition partials to one row per author before joining
    con.execute(
        "CREATE OR REPLACE TEMP TABLE f_rat_f AS SELECT akey, sum(rc1) AS rc1, sum(rc2) AS rc2,"
        " sum(rc3) AS rc3, sum(rc4) AS rc4, sum(rc5) AS rc5 FROM f_rat GROUP BY akey"
    )
    con.execute(
        "CREATE OR REPLACE TEMP TABLE f_rl_f AS SELECT akey, sum(want) AS want, sum(curr) AS curr,"
        " sum(already) AS already, sum(stopped) AS stopped FROM f_rl GROUP BY akey"
    )
    # final zero-filled table over every bronze author
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE agg_final AS
        SELECT regexp_replace(a.Key, '^/authors/', '') AS akey,
               COALESCE(wc.work_count, 0) AS work_count,
               tw.title AS top_work_title,
               tw.subtitle AS top_work_subtitle,
               COALESCE(s.top_subjects, []) AS top_subjects,
               COALESCE(r.rc1, 0) AS rc1, COALESCE(r.rc2, 0) AS rc2, COALESCE(r.rc3, 0) AS rc3,
               COALESCE(r.rc4, 0) AS rc4, COALESCE(r.rc5, 0) AS rc5,
               COALESCE(rl.want, 0) AS want, COALESCE(rl.curr, 0) AS curr,
               COALESCE(rl.already, 0) AS already, COALESCE(rl.stopped, 0) AS stopped,
               COALESCE(rl.want, 0) + COALESCE(rl.curr, 0) + COALESCE(rl.already, 0) + COALESCE(rl.stopped, 0) AS readinglog_count
        FROM '{authors_parquet}' a
        LEFT JOIN f_wc wc ON wc.akey = regexp_replace(a.Key, '^/authors/', '')
        LEFT JOIN f_top tw ON tw.akey = regexp_replace(a.Key, '^/authors/', '')
        LEFT JOIN f_subj s ON s.akey = regexp_replace(a.Key, '^/authors/', '')
        LEFT JOIN f_rat_f r ON r.akey = regexp_replace(a.Key, '^/authors/', '')
        LEFT JOIN f_rl_f rl ON rl.akey = regexp_replace(a.Key, '^/authors/', '')
        """
    )
    n = con.execute("SELECT count(*) FROM agg_final").fetchone()[0]
    BUILD_TOTAL[0] = n
    print(f"[final] agg_final built: {n:,} authors {time.time() - t0:.1f}s", flush=True)
    if dump := os.environ.get("AGG_DUMP"):
        con.execute(f"COPY agg_final TO '{dump}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        print(f"[final] dumped to {dump}", flush=True)


# Table kept for validation-time lookups (wa equivalent over all gold): rebuilt lazily per query.
def make_doc(row: dict) -> dict:
    summary = ratings_summary_from_counts([row["rc1"], row["rc2"], row["rc3"], row["rc4"], row["rc5"]])
    doc = {
        "key": f"/authors/{row['akey']}",
        "type": {"set": "author"},
        "work_count": {"set": int(row["work_count"])},
        "ratings_average": {"set": summary["ratings_average"]},
        "ratings_sortable": {"set": summary["ratings_sortable"]},
        "ratings_count": {"set": int(summary["ratings_count"])},
        "ratings_count_1": {"set": int(row["rc1"])},
        "ratings_count_2": {"set": int(row["rc2"])},
        "ratings_count_3": {"set": int(row["rc3"])},
        "ratings_count_4": {"set": int(row["rc4"])},
        "ratings_count_5": {"set": int(row["rc5"])},
        "readinglog_count": {"set": int(row["readinglog_count"])},
        "want_to_read_count": {"set": int(row["want"])},
        "currently_reading_count": {"set": int(row["curr"])},
        "already_read_count": {"set": int(row["already"])},
        "stopped_reading_count": {"set": int(row["stopped"])},
    }
    if row["top_work_title"] is not None:
        top_work = row["top_work_title"]
        if row["top_work_subtitle"]:
            top_work = f"{top_work}: {row['top_work_subtitle']}"
        doc["top_work"] = {"set": top_work}
    if row["top_subjects"]:
        doc["top_subjects"] = {"set": list(row["top_subjects"])}
    return doc


async def post_all(con: duckdb.DuckDBPyConnection, solr: str, batch: int, concurrency: int, total: int):
    url = f"{solr}/update"
    t0 = time.time()
    counter = [0]
    cur = con.execute("SELECT * FROM agg_final")
    cols = [d[0] for d in cur.description]

    async def _post(client, payload: bytes, n_docs: int):
        for attempt in range(3):
            try:
                res = await client.post(url, params={"commitWithin": "60000"}, content=payload, headers={"Content-Type": "application/json"})
                if res.status_code >= 400:
                    print(f"SOLR {res.status_code}: {res.text[:600]}", flush=True)
                    print(f"payload head: {payload[:300]}", flush=True)
                res.raise_for_status()
                return
            except Exception:
                if attempt == 2:
                    raise
                await asyncio.sleep(2**attempt)

    # Windowed fan-out: only `concurrency` payloads in flight (and built) at a time, so python
    # memory stays flat over the 15M-row stream.
    done = False
    # NOTE: never con.execute anything else on `con` while `cur` streams -- a new statement
    # invalidates the streaming cursor (this bit us twice).
    async with httpx.AsyncClient(timeout=120.0) as client:
        while not done:
            window = []
            for _ in range(concurrency):
                rows = cur.fetchmany(batch)
                if not rows:
                    done = True
                    break
                docs = [make_doc(dict(zip(cols, r))) for r in rows]
                window.append((json.dumps(docs).encode(), len(rows)))
            if not window:
                break
            await asyncio.gather(*(_post(client, p, n) for p, n in window))
            counter[0] += sum(n for _, n in window)
            rate = counter[0] / max(time.time() - t0, 0.001)
            eta = ""
            if counter[0] < total:
                eta = f" ETA {(total - counter[0]) / max(rate, 0.01) / 60:.0f}m"
            print(f"  {counter[0]:,}/{total:,} authors ({rate:.0f}/s{eta})", flush=True)
    print(f"[post done] {counter[0]:,} author updates in {(time.time() - t0) / 60:.1f}m", flush=True)


SLIM_DIR = None
BUILD_TOTAL = [0]


async def validate(con: duckdb.DuckDBPyConnection, solr: str, n: int, authors_parquet: str):
    """Compare against the REAL AuthorSolrUpdater querying the loaded Solr.

    The oracle index predates orphan fake-works, so authors owning any /works/OL..M doc are skipped.
    """
    import os

    os.environ["OL_SOLR_BASE_URL"] = solr
    from openlibrary.solr.updater.author import AuthorSolrUpdater

    # authors owning fake works can't be validated against the pre-oracle index
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE fake_authors AS
        SELECT DISTINCT unnest(from_json(json_extract(doc_json,'$.author_key[*]'),'["VARCHAR"]')) AS ak
        FROM read_parquet(['/mnt/HC_Volume_106672133/openlibrary/lake_full/gold/rust_full.parquet'])
        WHERE key LIKE '%M'
        """
    )
    sample = con.execute(
        """
        SELECT wc.akey FROM f_wc wc
        LEFT JOIN fake_authors f ON f.ak = wc.akey
        WHERE f.ak IS NULL
        ORDER BY wc.work_count DESC LIMIT ?
        """,
        [n],
    ).fetchall()
    keys = [f"/authors/{a}" for (a,) in sample]
    author_rows = con.execute(f"SELECT Key, JSON FROM '{authors_parquet}' WHERE Key = ANY(?)", [keys]).fetchall()

    from openlibrary.solr.data_provider import DataProvider

    class NoopDP(DataProvider):
        async def get_document(self, k):
            raise AssertionError("not used")

    updater = AuthorSolrUpdater(NoopDP())
    mismatches = tie_accepted = checked = 0
    for akey_raw, j in author_rows:
        author = json.loads(j)
        upd, _ = await updater.update_key(author)
        py_doc = upd.adds[0]
        akey = akey_raw.replace("/authors/", "")
        row = con.execute("SELECT * FROM agg_final WHERE akey = ?", [akey]).fetchone()
        cols = [d[0] for d in con.description]
        ours = make_doc(dict(zip(cols, row)))
        checked += 1
        problems = []

        def eq(a, b, eps=1e-4):  # float32 storage in Solr loses ~1e-5 relative
            if isinstance(a, float) or isinstance(b, float):
                return abs(float(a) - float(b)) <= eps
            return a == b

        for f in (
            "work_count",
            "ratings_average",
            "ratings_sortable",
            "ratings_count",
            "ratings_count_1",
            "ratings_count_2",
            "ratings_count_3",
            "ratings_count_4",
            "ratings_count_5",
            "readinglog_count",
            "want_to_read_count",
            "currently_reading_count",
            "already_read_count",
            "stopped_reading_count",
        ):
            pv, rv = py_doc.get(f), ours[f]["set"]
            pv = pv if pv is not None else 0
            if not eq(pv, rv):
                problems.append((f, pv, rv))

        pt, rt = py_doc.get("top_work"), ours.get("top_work", {}).get("set")
        if pt != rt:
            wa_glob = f"{SLIM_DIR}/wa/*.parquet"
            n_tied = con.execute(
                f"""
                WITH wec AS (SELECT wkey, max(ec) AS ec FROM read_parquet(['{wa_glob}']) WHERE akey = ? GROUP BY wkey)
                SELECT count(*) FROM wec WHERE ec = (SELECT max(ec) FROM wec)
                """,
                [akey],
            ).fetchone()[0]
            if n_tied > 1:
                tie_accepted += 1
            else:
                problems.append(("top_work", pt, rt))

        ps = py_doc.get("top_subjects") or []
        rs = ours.get("top_subjects", {}).get("set") or []
        if sorted(ps) != sorted(rs):  # multiset: prod can repeat a value across fields
            problems.append(("top_subjects", sorted(ps)[:8], sorted(rs)[:8]))
            if mismatches == 0:
                fs = con.execute("SELECT top_subjects FROM f_subj WHERE akey = ?", [akey]).fetchone()
                print(f"DEBUG {akey}: f_subj={fs[0] if fs else None}")
                print(f"         py      ={py_doc.get('top_subjects')}")

        if problems:
            mismatches += 1
            if mismatches <= 8:
                print(f"MISMATCH {author['name']} ({akey}): {problems}")

    print(f"[validate] checked={checked} mismatched={mismatches} top_work_ties_accepted={tie_accepted}")
    return mismatches


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold-parts-glob", default="/mnt/HC_Volume_106672133/openlibrary/lake_full/gold/parts/*.parquet")
    ap.add_argument("--gold-single", nargs="+", default=None, help="merged gold parquet(s) used only for --validate fake-author scan")
    ap.add_argument("--authors", default="/mnt/HC_Volume_106672133/openlibrary/lake_full/bronze/authors.parquet")
    ap.add_argument("--ratings", default="/root/solr_duckdb/parquet/ratings.parquet")
    ap.add_argument("--reading-log", default="/root/solr_duckdb/parquet/reading_log.parquet")
    ap.add_argument("--slim-dir", default="/mnt/HC_Volume_106672133/openlibrary/lake_full/slim_authors")
    ap.add_argument("--solr", default="http://localhost:8985/solr/openlibrary")
    ap.add_argument("--batch-files", type=int, default=8)
    ap.add_argument("--batch", type=int, default=5000)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--validate", type=int, default=0)
    ap.add_argument("--no-post", action="store_true")
    ap.add_argument("--rebuild", action="store_true", help="Drop existing partial tables first")
    ap.add_argument("--skip-build", action="store_true", help="Reuse existing slim; go straight to validate/post")
    ap.add_argument("--duckdb-only", action="store_true", help="Skip extraction; run duckdb stage then validate/post")
    ap.add_argument("--load-aggs", action="store_true", help="Read agg_final from AGG_DUMP parquet instead of rebuilding")
    args = ap.parse_args()

    global SLIM_DIR
    SLIM_DIR = args.slim_dir
    gold_files = sorted(glob.glob(args.gold_parts_glob))
    if not gold_files:
        raise SystemExit(f"no gold parts found at {args.gold_parts_glob}")

    con = duckdb.connect()
    tune(con)

    wa_marker = os.path.join(args.slim_dir, "wa", "slim.parquet")
    if args.load_aggs:
        dump = os.environ.get("AGG_DUMP")
        assert dump and os.path.exists(dump), "--load-aggs needs AGG_DUMP parquet"
        con = duckdb.connect()
        tune(con)
        con.execute(f"CREATE VIEW agg_final AS SELECT * FROM read_parquet(['{dump}'])")
        n = con.execute("SELECT count(*) FROM agg_final").fetchone()[0]
        print(f"[load] agg_final from {dump}: {n:,} authors", flush=True)
        if args.validate:
            raise SystemExit(1 if asyncio.run(validate(con, args.solr, args.validate, args.authors)) else 0)
        asyncio.run(post_all(con, args.solr, args.batch, args.concurrency, n))
        return
    if args.skip_build or args.duckdb_only:
        assert os.path.exists(wa_marker), f"--skip-build/--duckdb-only need existing {wa_marker}"
    else:
        if os.path.exists(wa_marker) and not args.rebuild:
            raise SystemExit(f"{wa_marker} exists; pass --rebuild or --skip-build")
        import shutil

        if os.path.exists(args.slim_dir):
            shutil.rmtree(args.slim_dir)
        stream_slim(gold_files, args.slim_dir)
    build_from_slim(con, args.slim_dir, args.ratings, args.reading_log, args.authors)

    if args.validate:
        raise SystemExit(1 if asyncio.run(validate(con, args.solr, args.validate, args.authors)) else 0)
    if not args.no_post:
        asyncio.run(post_all(con, args.solr, args.batch, args.concurrency, BUILD_TOTAL[0]))


if __name__ == "__main__":
    main()
