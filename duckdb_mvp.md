# MVP: 10k-record Solr Benchmark (DuckDB vs Postgres solr_builder)

**Goal:** Get something up and running soon that matches existing `solr_builder` output as close as possible for `10k` works - prove `dump -> Solr` on `1` box without `postgres:test` and time vs `scripts/solr_builder/solr_builder/solr_builder.py:535`.

**Prerequisites / Constraints (do not change):**
* Latest dump **already on disk** - locate `ol_dump*.txt.gz` (e.g. `find / -name "ol_dump*.txt.gz" 2>/dev/null` or `/storage/openlibrary` per `Jenkinsfile:30`) and use that path; **do not** `wget`/re-download.
* Production/existing `solr` **leave alone** - do not touch `scripts/solr_builder/compose.yaml:27` `solr` on `8983` or its volume. Spin a **separate isolated Solr for MVP** (see Setup).

**Tracking:** Keep a live progress doc `PROGRESS_MVP_10k.md` (alongside this plan) and update it regularly (sample counts, timings, parity diffs, blockers). This plan is the source of truth; `PROGRESS` is the log.

## Scope (MVP, not full reindex)
* `10k` works `START_AT=/works/OL1W` (same slice for both paths)
* Fields: `work` + `editions` + `authors` + `subjects` only; stub `ratings/reading_log/cover/ia_metadata` (`data_provider.py:238` → `{}`) to isolate CPU vs IO. `subjects` via `work.py:687` not `index_subjects.py:48` facet.
* Sink: local `solr:10` `compose.yaml:27` (`autoSoftCommit=-1`), `httpx` batched `POST /update?commitWithin=60000`.

## Tools (3 runtimes)
`uv` + `duckdb 1.5` + `polars[streaming]/pyarrow/orjson` + `httpx` + existing `openlibrary/solr/updater/work.py:272` helpers (`sort_title`, `normalize_ddc`, `short_lcc_to_sortable_lcc`). No `postgres`, no `sql/create-indices.sql:1` (`1.25hr`), no `Jenkinsfile:35`.

## Plan (1-2 day, ~200 LOC)

### 1. Setup (30m) - isolated
```bash
uv venv && uv add duckdb polars pyarrow orjson httpx

# Locate existing dump, do not download
ls -lh /storage/openlibrary/ol_dump*.txt.gz 2>/dev/null; \
find $HOME /data /storage -name "ol_dump*.txt.gz" 2>/dev/null | head
export OL_DUMP=$(ls -t /storage/openlibrary/ol_dump*.txt.gz 2>/dev/null | head -n1)

# Start SEPARATE Solr for MVP only (leave prod solr on 8983 alone)
# Use distinct project name + port + volume
docker compose -f scripts/solr_builder/compose.yaml -p solr_mvp \
  -f compose.mvp.yaml up -d solr_mvp
# compose.mvp.yaml: solr_mvp: image: solr:10.0.0, ports: ["8984:8983"], volumes: ["solr_mvp_data:/var/solr"], networks: [solr_mvp_net]
# Verify: curl http://localhost:8984/solr/openlibrary/admin/ping  (8984, not 8983)

# Init progress log
touch PROGRESS_MVP_10k.md && echo "# MVP Progress $(date)" >> PROGRESS_MVP_10k.md
```

### 2. Sample 10k (30 LOC, `mvp_sample.py`) - use `$OL_DUMP` from Setup
* `duckdb` `read_csv('$OL_DUMP', delim='\t', quote='\b', names=['Type','Key','Rev','LastModified','JSON']) WHERE Type='/type/work' ORDER BY Key LIMIT 10000` → `sample.parquet` + `keys = [Key]`. **Log** `OL_DUMP` path + count to `PROGRESS_MVP_10k.md`.
* Second pass: `SELECT JSON FROM read_csv('$OL_DUMP', ...) WHERE Type='/type/edition' AND JSON->'works'->0->>key IN (SELECT Key FROM 'sample.parquet')` → `editions_by_work`; same for `authors` `JSON->'authors'[*].author.key`. Keep in `dict`.

### 3. Transform (80 LOC, `mvp_transform.py`)
* `FakeDataProvider(DataProvider)` in-mem: `get_document`, `get_editions_of_work`, `preload_*=noop`, `get_cover_dimensions=None`.
* Loop `for work in works: await WorkSolrUpdater(provider).update_key(work)` → `docs` (`abstract.py:34` `build()`).

### 4. Load (30 LOC, `mvp_load.py`) - to MVP Solr only
* `solr_insert_documents(docs, batch=1000, commitWithin=60000, solr_base_url="http://localhost:8984/solr/openlibrary")` → `POST http://localhost:8984/solr/openlibrary/update` (not `8983`). Do not commit to prod.

### 5. Benchmark (1hr) - parity goal
* Baseline (read-only, still against prod `postgres` but `dry-run` to avoid prod `solr` writes): `time docker compose run --rm ol python solr_builder/solr_builder.py index works --start-at /works/OL1W --limit 10000 --dry-run` (or `solr_base_url=http://localhost:8984` if you want baseline also to MVP `solr`).
* MVP: `hyperfine "python mvp.py"` + `/usr/bin/time -v` + `cProfile` on `build()`. Compare wall, RSS, `q_1/q_auth` (`solr_builder.py:569`) vs `duckdb join` ms, **doc parity (goal: as close as possible)** `diff <(jq -S . baseline.json) <(jq -S . mvp.json)` on `title/title_sort/author_key/subject_key/edition_count/lcc/ddc`. Log results to `PROGRESS_MVP_10k.md` every run.

## Success (parity first)
* `10k` docs in **MVP `solr` on `8984`** `q=type:work` count `10000`, `title/title_sort/subject_key/author_key/edition_count/lcc/ddc` match baseline `>99%` (up-and-running soon, output as close as possible).
* Wall `mvp` `<= 50%` of `postgres` path for same `10k` (excludes `1.25hr` indices). Report `ingest|join|transform|POST` breakdown in `PROGRESS_MVP_10k.md`.
* `PROGRESS_MVP_10k.md` updated regularly (every sample/load/bench run) - not just at end.

## Cleanup
* `docker compose -p solr_mvp down -v` removes MVP `solr` + volume; prod `solr` on `8983` untouched.

## Risks
* `TSV \b` quote/escape edge -> fallback to `python gzip csv` reader.
* `JSON ->` extraction nulls -> `try_cast`.

## Next
If `MVP` wins, extend to `ratings/cover/ia` + `1M` `streaming` + `iceberg/parquet lake`.
