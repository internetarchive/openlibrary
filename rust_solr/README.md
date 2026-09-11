# rust_solr — DuckDB (A) → Rust Transform → Gold Parquet (minimal)

Keeps DuckDB for queries (silver `work_key` 21× win `mvp_silver_py.py:1`), Rust does `WorkSolrBuilder` build + Parquet write. Minimal schema `key, doc_json, title, edition_count` per user decision, logical diff.

## Quick run (test with small samples first)

```bash
cargo build --release  # ~5s incremental, 1.5m cold (libduckdb-sys bundled)
./target/release/rust_solr --limit 10 --out /tmp/rust_10.parquet \
  --bronze-works /mnt/HC_Volume_106672133/openlibrary/lake_full/bronze/works.parquet \
  --silver-editions /mnt/HC_Volume_106672133/openlibrary/lake_full/silver/editions.parquet \
  --bronze-authors /mnt/HC_Volume_106672133/openlibrary/lake_full/bronze/authors.parquet

# 100/1000/10000
./target/release/rust_solr --limit 100 --out lake_full/gold/rust_100.parquet --bronze-works lake_full/bronze/works.parquet --silver-editions lake_full/silver/editions.parquet --bronze-authors lake_full/bronze/authors.parquet
./target/release/rust_solr --limit 1000 --out lake_full/gold/rust_1000.parquet --bronze-works lake_full/bronze/works.parquet --silver-editions lake_full/silver/editions.parquet --bronze-authors lake_full/bronze/authors.parquet
./target/release/rust_solr --limit 10000 --out lake_full/gold/rust_10k.parquet --bronze-works lake_full/bronze/works.parquet --silver-editions lake_full/silver/editions.parquet --bronze-authors lake_full/bronze/authors.parquet
```

Works must be run from repo root OR pass absolute paths (binary runs with `Connection::open_in_memory`, so paths are passed to DuckDB SQL).

## Structure

```
src/
  main.rs         # clap CLI, rayon chunk filter (mvp_gold_DC.py:104-115)
  query.rs        # DuckDB: sample_keys temp table + JOIN silver work_key + authors via appender
  transform/mod.rs # WorkSolrBuilder port (minimal core fields)
  helpers/
    sort_title.rs # edition.py:105
    ddc.rs        # utils/ddc.py:49 + choose_sorting_ddc
    lcc.rs        # utils/lcc.py:115
    isbn.rs       # opposite_isbn
    mod.rs        # uniq, subject_name_to_key, datetimestr_to_int
  parquet.rs      # arrow 54 ArrowWriter zstd(3) minimal schema
```

## Bench (10k, START_AT=/works/OL1W)

| Variant | total | prep | build | docs/s |
|---------|-------|------|-------|--------|
| Python `mvp_gold_DC.py:15` idle | 19.17s | 10.58s | 8.52s | 1173 |
| Python loaded | 43.98s | 24.41s | 19.44s | 514 |
| **Rust A (this)** | **12.62s** | **10.21s** | **2.19s** | **4559** |

`12.62s` vs `19.17s` → 1.5× total, 3.9× build. Full 14.4M est `build 0.88h total 5.05h` vs Python `3.41h/7.67h`.

Smaller samples (stable prep ~2.5-10s, build scales linearly):
- 10: prep 4.45s build 0.01s 1029 docs/s
- 100: prep 7.61s build 0.03s 3848 docs/s
- 1000: prep 9.30s build 0.25s 3968 docs/s

## Logical diff (minimal core fields)

Checked `key, type, title, title_sort, edition_count, edition_key, author_key/name/facet, publisher, publish_year, first_publish_year, language, isbn, lcc, lcc_sort, ddc, ddc_sort, seed, subject*, place*, person*, time*, last_modified_i, cover_i`:

- **10:** 0/10 mismatches (pass)
- **100:** 5/100 mismatches (all `lcc_sort` tie-breaking where same short_len but different year, e.g. `NA-1353.00000000.B67 A4 2013` vs `2014` — both valid max among set)
- **1000:** 59/1000 mismatches (same tie cause, ~5.9% lcc_sort/ddc_sort)

Set iteration order for `choose_sorting_lcc/ddc` is nondeterministic in both Python (`set`) and Rust (`HashSet`) when multiple candidates tie on `short_len`. Logical diff should allow either tie-winner.

Full `doc_json` still omits `editions` nested, `by_statement`, `number_of_pages_median`, `cover_edition_key`, `ia`, `ebook_*`, `chapter`, `format` — deferred for next iteration (needs EditionSolrBuilder full port). Core fields now parity-checked.

## Full parity (2026-08-25) — 0 field diffs vs WorkSolrUpdater, incl. orphan fake-works

The builder is now a complete port. Verified with `mvp_diff_check.py` against Python ground truth
(`mvp_py_ground.py` runs the real `WorkSolrUpdater` over the same lake rows): **98,142 works across
five runs → `FULL PARITY ✓`, zero field diffs**, comparing order-insensitively on multivalued fields,
allowing equal-length `lcc_sort`/`ddc_sort` max-ties and ±1h `last_modified_i` on docs that get
index-time `now()` (`datetimestr_to_int(None)` semantics). Runs: 10k + 5k legacy windows, 20k chunk
(chunk 1000), 33k chunk **with 13,142 orphan editions** indexed as fake `/works/OLxxxM` works
(chunk 654). Since the first port added: nested edition docs (`id_*`, `ia_box_id`, chapter,
scorecard fields), work-level `lending_edition_s`/`lending_identifier_s`/`printdisabled_s`, real IA
availability (below), LCC short-form leading-zero fix, DDC word-boundary fix (Python skips a match
when the adjacent chars are word chars — not a transition check), and orphan coverage.

## Orphan editions -> fake works

~1.95M lake editions have no linked work; production indexes each as a standalone work under
`/works/OLxxxM` (`work.py:67-83`). Chunk mode does the same since the bucketed silver drops NULL
`work_key` rows:

```bash
# one-time: build silver/orphans_bucketed/ (numeric-id buckets of orphan editions)
.venv/bin/python mvp_partition_orphans.py
# then run chunks as usual -- rust picks up orphans in [lo,hi] automatically ("Indexed N orphan
# editions as fake works" in stderr)
```

7 non-numeric-key orphans (`/books/ia:*`) are skipped by the bucketing (logged).

## Real availability via --ia-metadata

By default every ocaid degrades to `ebook_access: unclassified` (matches prod's skip-IA mode).
Pass `--ia-metadata <ia_lite.parquet>` (built by `mvp_ia_fetch.py`) to compute REAL
`ebook_access`/`has_fulltext`/`public_scan_b`/`ia_collection` per `InternetArchiveProvider.get_access`
(inlibrary→borrowable, printdisabled→printdisabled, access-restricted/no-collections→unclassified,
else public), plus nested-edition scores that depend on access. Missing ocaids degrade to
unclassified exactly like prod when metadata can't be fetched.

```bash
# fetch lite metadata for all lake ocaids (~6.4M; resumable parts/, then merge)
.venv/bin/python mvp_ia_fetch.py                       # full run
.venv/bin/python mvp_ia_fetch.py --limit 1000          # smoke test
.venv/bin/python mvp_ia_fetch.py --merge-only          # rebuild ia_lite.parquet from parts/

cargo run --release -p rust_solr -- --chunks lake_full/silver/chunks_20000.json --chunk-index 0 \
  --out part-0000.parquet \
  --ia-metadata /mnt/HC_Volume_106672133/openlibrary/lake_full/ia/ia_lite.parquet
```

Note: prod's bulk endpoint (`advancedsearch.php?doc_ids=...`) returns unrelated results when called
from outside prod even with `service=metadata__unlimited`; `mvp_ia_fetch.py` uses the scrape API
(`services/search/v1/scrape`, exact matches, no throttling) instead, with retry + per-item
`/metadata/<ocaid>` fallbacks.

## Parity harness

```bash
# python ground truth (real WorkSolrUpdater + FakeDataProvider fed the same ia_lite.parquet)
PYTHONPATH=/root/openlibrary .venv/bin/python mvp_py_ground.py --limit 10000 \
  --out /tmp/py.json --ia-metadata /tmp/opencode/ia_test/ia_lite.parquet
# diff (exit 1 on any unallowed mismatch)
PYTHONPATH=/root/openlibrary .venv/bin/python mvp_diff_check.py \
  --py /tmp/py.json --rust /tmp/rust_10k.parquet
```

Unit tests (`cargo test`) cover `get_access` cases from `book_providers.py`, acquisition-access
mapping, direct-provider precedence, and scorecard aggregation.

## Next steps

1. ~~Port remaining `EditionSolrBuilder` fields~~ — done (full parity, incl. orphan fake-works).
2. ~~Real availability~~ — done (`--ia-metadata`).
3. ~~Author aggregates~~ — done (`mvp_author_aggregates.py`): lake-side DuckDB rollups matching
   `AuthorSolrUpdater`'s Solr facet semantics exactly; validated 300/300 top authors vs the real
   updater querying a loaded index (`--validate N`, zero mismatches). Posts atomic `{"set":}` updates
   to all 15.4M authors in ~30 min at conc 8.
5. ~~Ghost work docs~~ — done: `mvp_ratings_to_solr.py` SEMI-JOINs gold before aggregating
   (atomic updates can no longer create stubs); `--cleanup-ghosts` deletes historical ones by
   exact key set via XML delete (JSON delete objects mis-parse as atomic ops on nested docs).
   Live index cleaned: titleless works 34,062 -> 0.
6. ~~Non-IA provider identifiers~~ — done: full PROVIDER_ORDER chain (direct -> librivox ->
   project_gutenberg -> project_runeberg -> standard_ebooks -> openstax -> cita_press ->
   wikisource -> ia; BWB is config-gated and skipped) with faithful multi-provider
   `ebook_provider` lists.
7. ~~Series names~~ — done: fetched-doc name resolution from bronze other.parquet
   `/type/series` docs, falling back to the key path like prod when absent.
8. ~~osp_count~~ — done: `mvp_osp_to_solr.py` (ghost-guarded) posts counts from the official
   `2023_openlibrary_osp_counts/osp_totals.db`; 1,292,547 works after guard. Run after ratings.
9. Solr loading deferred (`mvp_load.py:24` `commitWithin=60000`).

## Author aggregates

```bash
# one-time: slim sidecars from gold parts (pyarrow+orjson streaming, ~14 min)
python mvp_author_aggregates.py --no-post            # extract + aggregate + dump author_aggs.parquet
# validate against the REAL AuthorSolrUpdater hitting --solr (default :8985) before posting
python mvp_author_aggregates.py --duckdb-only --validate 300
# push atomic updates for every author (zeros included, like Solr facet sums)
python mvp_author_aggregates.py --load-aggs          # requires AGG_DUMP env or default path
```

Semantics ported: `work_count` = distinct works per author (author arrays deduped); `top_work` =
max `edition_count` (ties broken by key asc — Solr's internal tie order is opaque, validate accepts
equal-max ties); `top_subjects` = each of the four facet fields' top-10 buckets (count desc, term
ASC ties like Lucene), merged by `(count, val)` DESC into a global top-10 **without cross-field
dedup** (a value can appear via both subject_facet and place_facet, as in prod); ratings/reading-log
fields are SUMs over the author's works run through `Ratings.work_ratings_summary_from_counts`,
always emitted (zeros included). Memory-safe: gold JSON never touches DuckDB — extraction streams
via pyarrow/orjson into slim parquets first, then all aggregation is partitioned small-row SQL.

---

## Note — Single Arrow Scan was not built

`Fix 6` as specced — one `parquet::arrow::ParquetRecordBatchReader` streaming `bronze`+`silver` once and joining in Rust — was **not implemented**. Instead `prep` was cut by bucketing both sides by numeric `OLID//100000` (`mvp_partition_works.py:1` + duckdb bucketed-silver compaction):

*   `lake_full/silver/works_b/bucket=N/data.parquet` (`346` buckets, `718M`) + `lake_full/silver/editions_bucketed/bucket=N/data.parquet` (`459` buckets, `4.1G`) each compacted to one file/bucket (`id` BIGINT column).
*   Chunk manifests `lake_full/silver/chunks_{10000,20000}.json` (numeric-OLID windows, `1441`/`721` chunks, `2.1s` warm build) let every call read only its `lo/100000..hi/100000` dirs (`query.rs:12` `bucket_paths()` + `WHERE id BETWEEN lo AND hi`) — the same pruning a true single scan would give, without rewriting the whole pipeline to Arrow.

Result: `prep 10.11s→1.4s` for typical sparse chunks (`10k` legacy `10.39s` → `2.30s`), `100k` (`5×20k` `Key>` paginate) `≈12s` (`5×2.4s avg`), full `14.4M` (`721×20k`) **`~24-29 min` wall** (`build ~0.6s`/`20k avg`) vs `mvp_gold_DC.py:15` `19.17s/10k` `→7.67h` idle (`43.98s` loaded `→17.6h`). A true single streaming pass (`Fix 6`) would shave only another `~1s prep/chunk` (DuckDB file-open overhead remains) — we left it for next handoff. Keep the bucketed `lake` as the contract; a pure Arrow scan can swap `query.rs:12` later without changing manifests or outputs.
