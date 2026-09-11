# Rust Solr Pipeline — Jenkins operator guide

The Rust lake pipeline (`Jenkinsfile.rust`) runs **side by side** with the legacy
postgres pipeline (`Jenkinsfile`). They share nothing: separate jobs, separate data
stores, separate Solr instances (Rust uses the isolated `solr_rust_full` on **:8985**;
legacy uses its own postgres+solr stack).

```
                       ┌──────────────────────────────────────┐
 monthly dump ────────►│ solr-builder        (Jenkinsfile)    │ postgres + solr  :9xxx
                       │                                      │
                       │ solr-builder-rust   (Jenkinsfile.rust)│ lake/ + solr     :8985
                       └──────────────────────────────────────┘
```

## First-time setup

```bash
cd scripts/solr_builder

# Controller coexists with a dev stack already on 8080:
export JENKINS_HTTP_PORT=8081          # optional, default 8080
export ADMIN_PASSWORD=choose-one       # seeds the admin user; never baked into the image

# Point both jobs at your fork/branch carrying the pipeline files:
export SEED_REPO=https://github.com/RayBB/openlibrary.git
export SEED_BRANCH=jenkins-rust-pipeline

docker compose --profile jenkins build jenkins
docker compose --profile jenkins up -d jenkins
# boot ~15s; seed logs: "created job 'solr-builder'" + "created job 'solr-builder-rust'"
docker compose -p solr_rust_full -f ../compose.rust_full.yaml logs jenkins | grep SEEDER || \
  docker logs openlibrary-solr_builder-jenkins-1 2>&1 | grep SEEDER
```

Open `http://localhost:${JENKINS_HTTP_PORT:-8080}` → log in as `admin` /
`$ADMIN_PASSWORD` → both jobs exist with parameters pre-seeded.

## Smoke run (~1–2 h incl. first cargo compile)

Proves every stage's wiring without a multi-hour build:

```
solr-builder-rust → Build with Parameters →
    SMOKE ✓  RESUME ✓  FETCH_IA_METADATA ✗ (skip for smoke)  LOAD_SATELLITES ✓
→ Build
```

Green means: agent image built, isolated Solr healthy, dump resolved, bronze/silver/
partitions/orphans produced, ≥3 chunks transformed + loaded, satellites ran sampled,
verify gate passed (`titleless == 0`, works > 0).

## Full rebuild (the real thing)

```
WIPE_SOLR ✓  RESUME ✗  FETCH_IA_METADATA ✓  LOAD_SATELLITES ✓  OPTIMIZE (your call)
```

~7–9 h wall on the reference box (4c/16GB + fast volume). See the phase table in
`docs/ai/solr/index.md`. Interrupted builds: re-run with `RESUME ✓` — completed
chunks/passes are skipped by output-existence checks.

## Stage map

| # | Stage | Skippable via |
|---|---|---|
| 1 | Build `openlibrary/solr-rust-agent` image | always runs (cheap when cached) |
| 2 | Isolated Solr up (+ health wait) | `WIPE_SOLR` empties data first |
| 3 | Dump fetch (chases `latest` → dated file, >1GB assert) | `RESUME` |
| 4 | Bronze / silver / bucketing / orphans | `RESUME` per-output |
| 5 | IA lite metadata (6.37M ocaids) | `FETCH_IA_METADATA`, `RESUME` |
| 6 | Gold chunks — Rust transform × N, parallel, parquet+ndjson twins | `RESUME` per chunk |
| 7 | Parallel NDJSON load → commit → works-count assert | — |
| 8 | Authors / lists / ratings / osp (all ghost-guarded vs gold parts) | `LOAD_SATELLITES` |
| 9 | Author aggregates (slim→DuckDB rollups→atomic updates) | `LOAD_SATELLITES`; skipped in SMOKE |
| 10 | **Verify gate** — hard assertions, fails the build loudly | — |
| 11 | Optimize maxSegments=1 | `OPTIMIZE` |

## Cargo cache

`libduckdb-sys` compiles DuckDB C++ (~35 min cold). The agent mounts the named
volume `solr-rust-cargo` at `/opt/cargo-cache` (`CARGO_TARGET_DIR`), so this happens
once per machine. If builds get weird: `docker volume rm solr-rust-cargo` and eat the
cold build.

## Legacy pipeline retirement checklist

Run both pipelines against the same dump once, then compare:

```bash
# counts by type
curl 'localhost:8985/solr/openlibrary/select?q=*:*&rows=0&facet=true&facet.field=type'
# spot fields on a hot work (ratings, availability, series)
curl 'localhost:8985/solr/openlibrary/select?q=key:%5C%2Fworks%5C%2FOL21524512W&fl=key,title,ebook_access,ratings_average,ia'
```

When satisfied: remove the legacy job from the seed list + delete `Jenkinsfile`,
`Dockerfile.olpython`, and the postgres stages of `compose.yaml`.
