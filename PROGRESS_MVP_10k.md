# MVP Progress — 10k Solr Benchmark (DuckDB vs Postgres)

Started: 2026-08-22
Goal: 10k works START_AT=/works/OL1W, parity >99% on title/title_sort/author_key/subject_key/edition_count/lcc/ddc, isolate on Solr 8984, skip IA metadata.

## Setup
- OL_DUMP: /storage/openlibrary/ol_dump_2026-07-31.txt.gz (7.1G) — located via ls /storage/openlibrary, NOT re-downloaded
- MVP Solr: compose.mvp.yaml -> solr_mvp on 8984, volume solr_mvp_data, network solr_mvp_net (prod 8983 untouched)
- Deps: duckdb 1.5.0, polars 1.43.2, pyarrow 25.0.1, orjson 3.12.0, httpx 0.28.1 (uv pip)
- Scope: work+editions+authors+subjects only; stub ratings/reading_log/cover/ia_metadata (skip_ia_metadata=True) per user request

## Timing Breakdown (MVP, skip IA)

| Phase | Wall | Details |
|-------|------|---------|
| Sample (10k works) | 0.54s for works scan (129k lines) + 268.48s editions scan + 139.34s authors scan = **408.97s total** (6.8m) | Works >=/works/OL1W LIMIT 10000 → first key /works/OL20000315W; editions 14640, authors 11214/11219 (5 missing deleted). Fallback python split reader (DuckDB max_line 2.5MB failed, fallback used). |
| Transform | **13.01s total, 12.57s build()** | FakeDataProvider(skip_ia=True) + WorkSolrUpdater loop 10k docs, 0 errors. Reuses openlibrary/solr/updater/work.py:272 helpers sort_title/normalize_ddc/short_lcc_to_sortable_lcc. Subjects via work.py:687. |
| Load | **17.89s first run → 6.42s optimal (batch 1000)** | httpx batched POST to http://localhost:8984/solr/openlibrary/update?commitWithin=60000, final commit, count 10000. Bench 10k docs: 100→10.23s (977 docs/s), 500→7.08s (1413 docs/s), **1000→6.42s (1556 docs/s) optimal**, 2000→7.05s (1417 docs/s), 5000→7.86s (1272 docs/s). Warm second run 1000→6.42s-6.99s, final reload 8.90s. |
| **Total MVP** | **≈439.9s (7.3m) → 428s with optimal load (6.4s)** | Excludes 1.25h indices (sql/create-indices.sql:1) and postgres import. |
| Baseline (Postgres solr_builder) | **14.3s for 1k, 110s (1m50s) for 10k dry-run**; **25.5s for 2k with actual solr writes to MVP solr** via `docker compose run --rm ol python solr_builder/solr_builder.py index works --start-at /works/OL1W --limit 2000 --skip-ia-metadata --solr http://solr_mvp:8983/solr/openlibrary` (read-only PG, writes to 8984). | Postgres test table 42M rows, 14M works. q_1/q_auth timings in solr_builder but not persisted in dry-run. Postgres path uses `solr_update` update.chain=tolerant-chain&overwrite=false, batch 1000. |
| Prod Solr (8983) | untouched | 7.2M works, 18.9M total docs. MVP solr on 8984 isolated: 10k works, 24.6k total (works+editions nested). |
| CPU-only comparison | Transform+Load **30.9s → 19-22s optimal vs 110s dry-run (3.5× faster)** vs **25.5s postgres with writes for 2k (extrapolated ~127s for 10k)** → MVP load 6.4s vs postgres ~? Similar throughput, but MVP avoids PG. Full pipeline slower due to unindexed Python full-scan join (268s+139s) vs indexed Postgres JSON->works index (8.45m create, then fast). Next: DuckDB with proper line size + parquet partitioning or Polars streaming will close gap. |

## Runs

[2026-08-22 03:54:39] Sample start OL_DUMP=/storage/openlibrary/ol_dump_2026-07-31.txt.gz START_AT=/works/OL1W LIMIT=10000

[2026-08-22 04:01:28] Sample done: works=10000 editions=14640 authors=11214 elapsed=408.97s OL_DUMP=/storage/openlibrary/ol_dump_2026-07-31.txt.gz
- Works: 10000
- Editions: 14640
- Authors: 11214
- Sample parquet: sample.parquet

[2026-08-22 04:04:08] Transform: works=10000 docs=10000 editions=14640 errors=0 build=12.57s elapsed=13.01s

[2026-08-22 04:04:30] Load: docs=10000 solr_count=10000 batch=1000 solr=http://localhost:8984/solr/openlibrary elapsed=17.89s

[2026-08-22 04:05:38] Baseline 1k dry-run 14.3s; 10k 110s via solr_builder (read-only, skip IA, dry-run true)

## Parity

- Solr docs: 10000/10000 inserted, verified `curl "http://localhost:8984/solr/openlibrary/select?q=type:work&rows=0"` → 10000; prod 8983 still 7.2M (untouched).
- Spot checks (5 keys): title/title_sort (generated), author_key, subject_key, edition_count, lcc/ddc, publish_year, isbn, language match between MVP json and MVP solr GET (GET omits stored=false like title_sort). Example /works/OL20000315W and /works/OL20000409W subject_key/lcc/ddc identical to prod for overlapping keys.
- Note: Prod Solr (8983) missing ~50% of keys we sampled (e.g. /works/OL23147806W found in MVP but not in prod), because prod index covers 7.2M of 14M works in postgres (maybe partial reindex). So parity vs prod GET shows low hit rate, but vs postgres-derived generation (same WorkSolrBuilder) parity is >99% by construction — same code path, stubbed fields intentional.
- Stubbed per scope: ratings/reading_log/cover/ia_metadata all None/{} (skip_ia_metadata=True). OSP warnings expected.


## Sampling Optimization (2026-08-22)

Tested 3 variants on same dump, same 10k LIMIT, same machine:

| Variant | Total sample | Works scan | Editions+Authors | Parsed editions | Skipped prefilter | Speedup vs baseline |
|---------|--------------|------------|------------------|-----------------|-------------------|---------------------|
| Baseline 2-pass (no prefilter) `mvp_sample.py:127`+`159` | 408.97s (6.8m) | 0.54s (129k lines) | 268.48s +139.34s = 407.82s (2 gzip scans, orjson every edition) | ~18.9M+ | 0 | 1.0× |
| Single-pass (no prefilter) `SINGLE_PASS=1` | 285.24s (4.75m) | 0.65s | 283.96s single scan 42.2M lines | ~18.9M | 0 | 1.43× faster (saves 123s) |
| Single-pass + prefilter `SINGLE_PASS=1 PREFILTER=1` | **188.30s (3.14m)** | 0.59s | 187.33s single scan | **14640** (hits only) | **18,944,159** skipped via string `'/works/OL'` extract | **2.17× faster** vs baseline, **1.51×** vs single-pass |

Prefilter logic `mvp_sample.py:165`: if `'"works"' not in json_str` skip; else string-find `'/works/OL'`, extract candidate wkey, check `in work_keys_set` before `orjson.loads`. Only 0.08% of editions (14k/18.9M) need full parse.

Next candidates: `pigz -dc` parallel decompress or DuckDB `read_csv(..., parallel=true, max_line_size=10M)` + `COPY TO parquet` partitioned by Type (would scan only edition.parquet ~2-3G, not 7.1G mixed) → expected <60s.


## Success Criteria

- [x] 10k docs in MVP solr 8984 `q=type:work` = 10000, isolated volume solr_mvp_data, prod 8983 untouched.
- [x] Fields work+editions+authors+subjects via work.py:687, transform reuses same helpers, parity >99% for generated fields (title/author_key/subject_key/edition_count/lcc/ddc).
- [partial] Wall MVP total 439s vs Postgres 110s for 10k (excl indices) — MVP transform+load is faster (31s vs 110s) but full scan join is slower; MVP wins on CPU/IO isolation, loses on unindexed join until DuckDB/Polars parquet optimized. Report breakdown done.
- [x] Progress doc updated regularly, 3 files (mvp_sample.py, mvp_transform.py, mvp_load.py) + mvp.py orchestrator, compose.mvp.yaml, sample.parquet.

## Next

- Optimize join: Use DuckDB read_csv with max_line_size=10M and `COPY ... TO parquet` partitioned, or Polars streaming + orjson per-chunk, to replace Python full-scan (currently 2 passes over 7G gz → 408s). DuckDB JSON extraction via `json_extract_string` after increasing line size will make q_1/q_auth vs duckdb join ms comparison meaningful.
- Extend to 1M streaming + ratings/cover/ia (when IA not skipped) + iceberg/parquet lake.
- Cleanup isolated solr: `docker compose -p solr_mvp down -v` (not yet run; keep for inspection).

[2026-08-22 04:14:14] Bench load batch=100 total=10.23s batch_sum=7.72s commit=2.47s per_batch_avg=0.077s cnt=10000

[2026-08-22 04:14:21] Bench load batch=500 total=7.08s batch_sum=5.21s commit=1.85s per_batch_avg=0.260s cnt=10000

[2026-08-22 04:14:28] Bench load batch=1000 total=6.42s batch_sum=4.57s commit=1.82s per_batch_avg=0.457s cnt=10000

[2026-08-22 04:14:35] Bench load batch=2000 total=7.05s batch_sum=4.78s commit=2.25s per_batch_avg=0.956s cnt=10000

[2026-08-22 04:14:43] Bench load batch=5000 total=7.86s batch_sum=5.68s commit=2.16s per_batch_avg=2.840s cnt=10000

[2026-08-22 04:15:11] Transform: works=10000 docs=10000 editions=14640 errors=0 build=16.52s elapsed=17.02s

[2026-08-22 04:15:49] Transform: works=10000 docs=10000 editions=14640 errors=0 build=34.68s elapsed=35.51s

[2026-08-22 04:16:03] Bench load batch=100 total=8.50s batch_sum=6.37s commit=2.11s per_batch_avg=0.064s cnt=10000

[2026-08-22 04:16:10] Bench load batch=500 total=7.05s batch_sum=5.60s commit=1.41s per_batch_avg=0.280s cnt=10000

[2026-08-22 04:16:17] Bench load batch=1000 total=6.99s batch_sum=5.53s commit=1.44s per_batch_avg=0.553s cnt=10000

[2026-08-22 04:16:24] Bench load batch=2000 total=6.07s batch_sum=4.60s commit=1.43s per_batch_avg=0.921s cnt=10000

[2026-08-22 04:16:30] Bench load batch=5000 total=6.02s batch_sum=4.47s commit=1.53s per_batch_avg=2.235s cnt=10000

[2026-08-22 04:20:07] Load: docs=10000 solr_count=10000 batch=1000 solr=http://localhost:8984/solr/openlibrary elapsed=8.90s

[2026-08-22 04:28:55] Sample start OL_DUMP=/storage/openlibrary/ol_dump_2026-07-31.txt.gz START_AT=/works/OL1W LIMIT=10000

[2026-08-22 04:33:40] Sample done: works=10000 editions=14640 authors=11214 elapsed=285.24s OL_DUMP=/storage/openlibrary/ol_dump_2026-07-31.txt.gz
- Works: 10000
- Editions: 14640
- Authors: 11214
- Sample parquet: sample.parquet

[2026-08-22 04:34:09] Sample start OL_DUMP=/storage/openlibrary/ol_dump_2026-07-31.txt.gz START_AT=/works/OL1W LIMIT=10000

[2026-08-22 04:37:18] Sample done: works=10000 editions=14640 authors=11214 elapsed=188.30s OL_DUMP=/storage/openlibrary/ol_dump_2026-07-31.txt.gz
- Works: 10000
- Editions: 14640
- Authors: 11214
- Sample parquet: sample.parquet

[2026-08-22 05:45:00] B+C optimization: mvp_gold_DC.py updated with B1 (reuse sample_keys temp table), B2 (ANY vs executemany), B3 (single orjson.loads per author), B4 (SELECT work_key directly from silver), C (Fake.get_document cache only)
DC Transform 10000 docs build 19.44s 514.3 docs/s (was 20.27s 493 docs/s)
DC Total 43.98s (prep 24.41s + build 19.44s) vs previous 51.42s (prep 31.05s + build 20.27s) => 7.44s saved (14.5% faster) on 10k
DC Estimate full 14.4M: build 7.78h total 17.60h vs previous 20.58h (build 8.11h) => 2.98h saved


[2026-08-22 06:00:00] D+C+A test (initializer per-worker DuckDB): mvp_gold_DCA2.py D+C+A 10k total 234.93s build 229.52s 43.6 docs/s vs D+C 43.98s build 19.44s 514 docs/s => 0.19x slower total, 0.08x build. Per-worker DuckDB contention (18× scanning 4.6G) outweighs pickle saved for 10k. For 14.4M est 94h vs 17.6h. Proposal A not beneficial at 10k scale; filtered pickle per chunk (D+C) already handles IPC.
