# Handoff — Rust Transform for Gold

**Date:** 2026-08-22  

> ⚠️ **OBSOLETE NUMBERS:** this run used a bad dump (January-2024 snapshot mislabeled `ol_dump_2026-07-31.txt.gz`). The real full pipeline lives at `/mnt/HC_Volume_106672133/openlibrary/lake_full/` — see `docs/ai/solr/index.md` ("Dump mixup incident"). Repo `lake/` paths below have been deleted.

**Goal:** 10k `START_AT=/works/OL1W` → `8984` isolated (prod `8983` untouched), skip IA, prove `dump → Solr` without PG.

## Where we are (fast path kept: D+C)

- **Bronze** `lake/bronze/*.parquet` `6.2G` `42M` rows (`works 1.5G 14.4M`, `editions 4.3G 18.9M`, `authors 405M`) — `mvp_bronze.py:1` `563s` one-time `ol_dump_2026-07-31.txt.gz` `7.1G`
- **Silver** `lake/silver/editions.parquet` `4.4G` `+ work_key = json_extract_string(JSON,'$.works[0].key')` — `mvp_silver_py.py:1` `343s` (`39.37s → 1.84s` `21×`)
- **Gold active** `mvp_gold_DC.py:15` **D (Silver) + C (Pool 18 filtered)** + `B1-4` (reuse `sample_keys`, `work_key` column, `ANY(?)`, single `orjson.loads`, `Fake.get_document` cache-only)  
  `10k` **under load** (`30× sh 18%` `load 24.45`): `prep 24.41s` (`6.21s` works + `~1.84s` editions + `6s` authors) + `build 19.44s` `514 docs/s` + `write 0.59s` = **`43.98s`** vs baseline `mvp_gold.py:40` `78.20s` (`26.51s` build) `→ 1.52× total, 1.30× build` — `PROGRESS_MVP_10k.md:48`, `MVP_STATUS.md:1`  
  `10k` **idle** (`jenkins stopped` `load 2.5`): **`prep 10.58s` + `build 8.52s` `1173 docs/s` = `19.17s` total** `→ 2.29×` faster than loaded `43.98s`, `4.08×` vs `78.20s` baseline — `load` was big factor
- **Load** `mvp_load.py:24` `httpx batch 10000 commitWithin=60000` → `8984` `10000` works `6.42s` loaded / `8.52s` idle optimal (`100→10.23s, 500→7.08s, 1000→6.42s, 2000→7.05s, 5000→7.86s`) `mvp_bench_load.py:59` — prod `8983` `7.2M` untouched
- **Dropped** `A` per-worker DuckDB `mvp_gold_DCA2.py:1` `234.93s` `5.3×` slower (18× `4.6G` scans contend) — filtered pickle per chunk already solves IPC

**Full `14.4M` est with D+C:** `51.42s×1440=20.58h` → `43.98s×1440=17.60h` loaded → **`19.17s×1440=7.67h` idle** (`3.41h` build) vs `31.22h` baseline. Sample `~60s` constant, not `×1440`. **CPU load halved `wall` — `24.41→10.58` prep `2.3×`, `19.44→8.52` build `2.28×`.**

**Silver/Gold samples:** `lake/gold/sample_10k.parquet` `5.9M` `10k` — `mvp_gold.py:40` `26.51s` vs `mvp_gold_DC.py:15` `19.44s`

## Table — Results so far (idle = Jenkins stopped `load 2.5`)

| Variant | `10k` total | `10k` build | `14.4M` est total / build | Samples | Load `10k` |
|---------|-------------|-------------|---------------------------|---------|------------|
| Python prefilter `mvp_sample.py:165` `SINGLE_PASS+PREFILTER` | `188.30s` | — | `75.2h` sample | `18.9M→14k` parse skip `18.9M` | — |
| Bronze 3 queries single-thread `mvp_sample_bronze.py:1` | `48.84s` (`5.63+36.24+6.09`) | — | — | `39.37s` `json_extract` | — |
| Gold baseline `mvp_gold.py:40` loaded | `78.20s` | `26.51s` `377 docs/s` | `31.22h / 10.61h` | `29.29s` | `6.42s` |
| **Gold D+C loaded** `mvp_gold_DC.py:15` | `43.98s` | `19.44s` `514 docs/s` | `17.60h / 7.78h` | `24.41s` | `6.42s` |
| **Gold D+C idle** `mvp_gold_DC.py:15` **current fast** | **`19.17s`** | **`8.52s` `1173 docs/s`** | **`7.67h / 3.41h`** | **`10.58s`** | `6.42s` |
| Gold D+C+A `mvp_gold_DCA2.py:1` | `234.93s` | `229.52s` | `94h` | `54.66s` | — |

## Plan — Convert transform to Rust (keep DuckDB queries)

**Keep** DuckDB for `sample` `0.74s` + `editions 1.84s` + `authors 6s` (`lake/silver` `work_key`) — already `21×` fast.

**Convert** `WorkSolrBuilder.build()` `work.py:272` hot helpers only via `pyo3`:
- `sort_title` `edition.py:105` `ARTICLE_PATTERN` `~15 lines`
- `normalize_ddc` `ddc.py:49` `DDC_RE` + `choose_sorting_ddc` `ddc.py:168` `~120 lines`
- `short_lcc_to_sortable_lcc` `lcc.py:115` + `choose_sorting_lcc` `~130 lines`
- `lib.rs` glue `~40` → **~315 Rust + `Cargo.toml`**

**Why Rust:** `build()` `~40%` `ddc/lcc` `re.finditer` `re.IGNORECASE|VERBOSE` `+` `groupdict()` per `edition` (`1.7` avg × `14.4M` ≈ `24M` regex) — Python `re` interpreted + `GIL` serializes `18` cores `1.3×` vs `18×`. Rust `regex` `DFA` `SIMD` + `no GIL` → `~4×` (`10.61h→2.5h` build per prior `build-cython.sh:1`).

**Steps for next agent (Rust already installed `rustc 1.98.0` `cargo 1.98.0` `rustup 1.29.0` `~/.cargo/bin/rustc`):**

1. **Verify Rust** `rustc --version && cargo --version` — already `1.98.0` via `rustup` `~/.cargo/bin/rustc -> rustup`
2. `cargo new --lib rust_solr_helpers && cd rust_solr_helpers`
3. Add `pyo3 = { version = "0.22", features = ["extension-module"] }`, `regex = "1.10"` to `Cargo.toml`, `maturin` for `pip`
4. Port `normalize_ddc`, `short_lcc_to_sortable_lcc`, `sort_title` as `#[pyfunction]` — keep Python `WorkSolrBuilder` but `from rust_solr_helpers import normalize_ddc, short_lcc_to_sortable_lcc, sort_title`
5. `maturin develop --release` (or `cargo build --release` + `uv pip install -e .`)
6. Re-bench `10k` `mvp_gold_DC.py:15` `8.52s` idle (`19.44s` loaded) → expect `~3-4s` `3000 docs/s` `~1.5h` full build `1.2h` with `19.17s` total. Update `HANDOFF_RUST.md` table row `Gold D+C+Rust`.

**Scripts for rerun:** `mvp_bronze.py` (once `563s`) → `mvp_silver_py.py` (`343s`) → `mvp_gold_DC.py` (`19.17s` idle / `43.98s` loaded) → `mvp_load.py` (`6.42s` to `8984`). `compose.mvp.yaml:4` `solr_mvp` `8984`, `PROGRESS_MVP_10k.md:1` log. Jenkins `30× sh` `load 24` halved wall — stop via `docker stop solr_builder-jenkins-1` before bench.

**Verify:** `curl "http://localhost:8984/solr/openlibrary/select?q=type:work&rows=0"` → `10000`, prod `8983` `7.2M` unchanged.
