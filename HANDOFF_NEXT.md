# Handoff — Build the full Gold → verify → fast-load into a fresh Solr

> ⚠️ **SUPERSEDED PATHS:** the `lake/` tree below was built from a bad dump (January-2024 snapshot mislabeled `ol_dump_2026-07-31.txt.gz`) and has been deleted. The completed full pipeline lives at `/mnt/HC_Volume_106672133/openlibrary/lake_full/` (41.5M works / 56.6M editions / 15.4M authors). See `docs/ai/solr/index.md` ("Dump mixup incident"). Numbers below reflect the bad-dump run and are kept for history only.

**Status before you:** DuckDB → Rust Gold is working and benchmarked.

*   `mvp_partition_works.py:1` + bucketing gave `lake/silver/works_b/bucket=N/data.parquet` (`346` buckets, `718M` incl. `id` BIGINT) + `lake/silver/editions_bucketed/bucket=N/data.parquet` (`459` buckets, `4.1G`) — one-time ~`81s+149s`.
*   `lake/silver/chunks_{10000,20000}.json:1` (`1441`/`721` numeric-id windows `{lo,hi,n}`) — `2.1s` warm.
*   `rust_solr/src/query.rs:12` bucket-pruned `WHERE id BETWEEN lo AND hi`; `rust_solr/src/transform/mod.rs:1` (`WorkSolrBuilder` port, static `RE_*` Lazy, `par_chunks` no-clone); `rust_solr/src/parquet.rs:1` row-group 10k + `par_iter` JSON.
    *   `10k` legacy `10.39s` (`9.81s prep + 0.39s build`) → **chunked `2.30s`** (`1.37s prep + 0.63s build`, `31623 docs/s`).
    *   `100k` (`5×20k` `Key>`-paginate old path `58.7s`) → **`~11.5s`** (`5×2.4s avg`) via chunks.
    *   Full `14.4M` (`721×20k`) **~28 min wall** (`build ~0.6s/chunk avg`) vs baseline `78.20s/10k→31h` — `~65×` reported in `rust_solr/README.md:72`.
*   Logical diff (`py` `Fake(skip_ia)` `WorkSolrUpdater`) shows `py only []` and `~113` `lcc_sort` non-tie `+3` `ebook_*` within `skip_ia` tolerance.
*   Prior Python path `HANDOFF_RUST.md:6` / `MVP_STATUS.md:1` `mvp_gold_DC.py:15` `19.17s` idle `→7.67h` still reproducible.

**Your 3 jobs (keep scope small, use absolute paths, pin `START_AT=/works/OL1W` where shown):**

### 1) Run Rust to generate the full Gold parquet

```bash
# Build (cold ~90s, incremental ~7s)
cargo build --release --manifest-path rust_solr/Cargo.toml

# Sanity — 10k legacy path (no --chunks) vs 20k chunk 10 (sparse) vs chunk 0 (dense bucket 0)
cargo run --release -p rust_solr -- --limit 10000 --out /tmp/rust_10k_legacy.parquet \
  --bronze-works /root/openlibrary/lake/bronze/works.parquet \
  --silver-editions /root/openlibrary/lake/silver/editions.parquet \
  --bronze-authors /root/openlibrary/lake/bronze/authors.parquet
cargo run --release -p rust_solr -- --chunks /root/openlibrary/lake/silver/chunks_20000.json --chunk-index 10 \
  --out /tmp/rust_chunk10.parquet --silver-editions /root/openlibrary/lake/silver/editions.parquet \
  --bronze-authors /root/openlibrary/lake/bronze/authors.parquet

# Full 14.4M → lake/gold/rust_full/ (one parquet per chunk, then concat)
# Use a fresh output dir; do NOT reuse an existing Solr — step 3 will stand up a new one.
mkdir -p lake/gold/rust_full
for i in $(seq 0 720); do
  cargo run --release -p rust_solr -- \
    --chunks /root/openlibrary/lake/silver/chunks_20000.json --chunk-index $i \
    --out lake/gold/rust_full/part-$(printf %04d $i).parquet \
    --silver-editions /root/openlibrary/lake/silver/editions.parquet \
    --bronze-authors /root/openlibrary/lake/bronze/authors.parquet
done
# If a chunk fails (OOM), rerun just that chunk — all chunks are deterministic and idempotent.

# Merge into single nice file (Parquet)
python3 -c "
import pyarrow.parquet as pq, pyarrow as pa, glob
files=sorted(glob.glob('lake/gold/rust_full/part-*.parquet'))
tbls=[pq.read_table(f) for f in files]; c=pa.concat_tables(tbls)
pq.write_table(c, 'lake/gold/rust_full.parquet', compression='zstd')
print(c.num_rows, c.schema.names)
"
# Expect ~14_406_749 rows. File is gitignored (lake/*.parquet) — large, do not commit.
```

Keep the chunked manifest contract (`lake/silver/chunks_*.json`) as-is; the true single-Arrow-stream pass (`Fix 6`) was intentionally not built (`rust_solr/README.md:72`) — bucketed lake gives the same pruning cheaply.

### 2) Inspect to make sure it is totally right

*   **Counts & distinct keys:**
    ```bash
    python3 -c "import duckdb; c=duckdb.connect(); print(c.execute(\"SELECT count(*), count(DISTINCT key) FROM 'lake/gold/rust_full.parquet'\").fetchone())"
    # expect (14406749, 14406749)
    ```
*   **Logical diff vs Python ground truth** on a *shared id range* (sparse `chunk 10` is a good proxy — `lo=618525 hi=677611`):
    ```bash
    PYTHONPATH=/root/openlibrary .venv/bin/python -c "
import duckdb, orjson; from openlibrary.utils.lcc import sortable_lcc_to_short_lcc
con=duckdb.connect(); rows=con.execute(\"SELECT doc_json FROM '/tmp/py_20k_parquet-for-chunk-10.parquet'\").fetchall()
# Build py_20k for chunk 10 by reusing the same id BETWEEN range as the chunk manifest
# (see script in rust_solr/README.md / prior session logs for the full py updater flow)
# Then compare normalized lists (sets as sorted), allow lcc/ddc same-short_len ties.
"
    ```
    Accept: tie `lcc_sort`/`ddc_sort` same `short_len` + `ebook_*` within `skip_ia`, same as session `py only []`, `ties ~815` for `20k`. Spot-check `cover_i/cover_edition_key` nondeterminism (`work.py:588` picks first edition with `cover_i`) — any valid `cover_i` from the work's editions is fine.

### 3) Fast-load into a **new** Solr (not existing prod/dev)

Follow `fast_solr_inserts.md:1` but apply to the `rust_full.parquet`, and keep the Solr isolated:

*   Create a separate Solr on different port/volume (do **not** reuse the dev `8983` / `solr-data` in `compose.yaml:42`). Example `docker run --name solr_rust_full -p 8985:8983 -v solr_rust_full:/var/solr solr:10.0.0 solr-precreate openlibrary /opt/solr/server/solr/configsets/olconfig` (or a dedicated `compose.rust_full.yaml` with `8985:8983` + `solr_rust_full` volume).
*   **Tune *that* Solr before load** (`fast_solr_inserts.md:22` `2`): `solrconfig.xml` `ramBufferSizeMB=512`, `autoSoftCommit maxTime=-1`, `autoCommit maxTime=60000 openSearcher=false`. Our `compose.yaml:42` does this via `SOLR_OPTS` `-Dsolr.*` — mirror that for the new instance and restart it.
*   **Convert Parquet → NDJSON per chunk** (don't use a 14M monolithic array — `fast_solr_inserts.md:5` `NDJSON`):
    ```bash
    python3 -c "
import duckdb
# stream doc_json column to lz4-compressed ndjson chunks of 100k lines (memory-safe)
"
    # or in Rust: add a --format ndjson flag and write doc_json lines directly.
    ```
*   **Load in parallel** (`fast_solr_inserts.md:50` `Approach A` `parallel -j 8` `curl --data-binary @chunk_  http://localhost:8985/solr/openlibrary/update/json/docs?commit=false` with `BATCH_SIZE 10000`, or Approach C Python pool). Use the per-chunk ndjson files you just split.
*   **Post-load** (`fast_solr_inserts.md:135` `4`): `curl "http://localhost:8985/solr/openlibrary/update?commit=true"` then verify `curl "http://localhost:8985/solr/openlibrary/select?q=type:work&rows=0"` → `14406749` (plus follow-up spot `fl=key,title,edition_count` for a known key e.g. `/works/OL1W` if present). Keep dev prod `8983` `7.2M` untouched.
*   Choose Rust or Python loader — whichever is already wired. Rust with `reqwest` streaming would be fastest but reimplementing Approach C in Python (`.venv/bin/python`) reusing `mvp_bench_load.py:59` `httpx batch 10000` is fine at `~6.42s/10k` scaled → `~2.5h` for 14.4M serial; parallel `--load-workers 8` brings it near `~20min`. The file is large (`--with-rows Append=true`) so a parallel Approach C is the pragmatic first pass.
