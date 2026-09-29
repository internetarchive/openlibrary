# MVP Status — 2026-08-22

> ⚠️ **OBSOLETE NUMBERS:** this run used a bad dump (a 7.1 GB January-2024 snapshot mislabeled `ol_dump_2026-07-31.txt.gz`). Works/editions were later rebuilt from the real 18 GB dump into `/mnt/HC_Volume_106672133/openlibrary/lake_full/` — see `docs/ai/solr/index.md` ("Dump mixup incident"). The repo `lake/` tree referenced below has been deleted.

**Goal:** 10k works `START_AT=/works/OL1W` → Solr `8984` isolated (prod `8983` untouched), skip IA `data_provider.py:238`.

## Where we are

- **Bronze** `lake/bronze/*.parquet` `6.2G` `42M` rows (`works 1.5G 14.4M`, `editions 4.3G 18.9M`, `authors 405M`) — `mvp_bronze.py:1` `563s` one-time `ol_dump_2026-07-31.txt.gz` `7.1G`
- **Silver** `lake/silver/editions.parquet` `4.4G` `+ work_key` `mvp_silver_py.py:1` `343s` — makes `WHERE work_key IN (10k)` `1.84s` vs `39.37s` `json_extract` (`21×`)
- **Gold sample** `lake/gold/sample_10k.parquet` `5.9M` `10k` docs `mvp_gold.py:40` `78.20s` → **D+C `mvp_gold_DC.py:15` `43.98s` total (`24.41s` prep + `19.44s` build `514 docs/s`)** `lake/gold/sample_10k.parquet`

**Kept:** `D` (Silver `work_key`) + `C` (Pool 18 filtered per chunk) + `B1-4` (reuse `sample_keys`, `work_key` column, `ANY(?)`, single `orjson.loads`, cache-only `Fake.get_document`) — `B1-4+C` saved `7.44s` (`51.42→43.98s` `14.5%`) on `10k`.

**Dropped:** `A` per-worker DuckDB `mvp_gold_DCA2.py:1` `234.93s` `5.3×` slower (18× `4.6G` scans contend) — filtered pickle per chunk already solves IPC for `10k`.

## Timings `10k` and full `14.4M` est.

| Variant | `10k` total | `10k` build | Full `14.4M` total / build |
|---------|-------------|-------------|---------------------------|
| Python prefilter `mvp_sample.py:165` `SINGLE_PASS+PREFILTER` | `188.30s` | — | `75.2h` sample |
| Gold baseline `mvp_gold.py:40` 3 queries single-thread | `78.20s` | `26.51s` | `31.22h / 10.61h` |
| **Gold D+C (current)** `mvp_gold_DC.py:15` | **`43.98s`** | **`19.44s`** | **`17.60h / 7.78h`** |
| Gold D+C+A | `234.93s` | `229.52s` | `94h` |

**PPG:** `transform 13-19s/10k` `~500 docs/s`, `load` `6.42s/10k` `1556 docs/s` optimal `batch 1000` `mvp_bench_load.py:59` `100→10.23s, 1000→6.42s, 5000→7.86s`

## Load

`mvp_load.py:24` `httpx POST /update?commitWithin=60000` `batch 1000` → `8984` `q=type:work 10000` `24.6k` total (nested editions) vs prod `8983` `7.2M` untouched. Final reload `8.90s`.

## Scripts for rerun

- `mvp_bronze.py` (once) → `mvp_silver.py` / `mvp_silver_py.py` → `mvp_gold_DC.py` (active) → `mvp_load.py`
- `compose.mvp.yaml:4` `solr_mvp` `8984` `PROGRESS_MVP_10k.md:1`

## Next

Full Gold `14.4M` via `D+C` `~17.6h` wall (`8.7s` sample + `7.78h` build) — monthly dump, one `~8h` is fine. No Iceberg incremental needed. Keep `D+C`, drop `A`.

Cleanup: `docker compose -p solr_mvp down -v` when done.
