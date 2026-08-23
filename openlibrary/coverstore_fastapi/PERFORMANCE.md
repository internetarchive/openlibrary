# Covers FastAPI Service — Performance Report

Before/after comparison of the FastAPI reimplementation of coverstore
(`openlibrary/coverstore_fastapi/`) against the legacy web.py/gunicorn
service (`openlibrary/coverstore/`).

## Methodology

- Both services ran side-by-side against the same PostgreSQL instance and the
  same cover files, one worker each, inside Docker Desktop on macOS
  (Apple Silicon). Absolute numbers are low/noisy in this environment;
  relative comparisons are what matter.
- Load generator: [hey](https://github.com/rakyll/hey), 6–10s runs unless noted.
- The legacy container's dev-only `--max-requests 250` (worker respawn every
  250 requests) was removed during benchmarking for fairness.
- Three eras of the new service are shown: **sync** (psycopg2 +
  threadpool endpoints), **async** (psycopg3 `AsyncConnectionPool` +
  httpx + `async def` endpoints), and **current** (async + direct-DB
  Open Library lookups via `ol_db_parameters`).

## Throughput (requests/sec, c=10)

| Endpoint | Legacy (web.py/gunicorn) | Sync FastAPI | Async FastAPI | Current (async + direct DB) |
|---|---:|---:|---:|---:|
| `GET /` (no I/O) | 1,204–1,337 | 2,286 | 3,118 | **2,809** |
| `/b/query` | 239–257 | 425 | 1,300 | **1,706** |
| `/b/id/N.jpg` | 184–272 | 430 | 734 | **1,003** |
| `/b/id/N.json` | 3.8* | 432 | 1,418 | **1,204** |
| missing cover → gif | 139–268 | 448 | 884 | **810** |
| 404 route miss | 793 | 3,204 | 2,524 | n/a |
| `POST /b/upload2` (real image write) | 101–140 | 132 | 175 | **230** |

\* Legacy `.json` was pathologically slow because `cover_details.GET` makes a
pointless external HTTP call to openlibrary.org before checking that the key
is `id` (the result is discarded). The port skips that dead call.

## The lookup path: the biggest win

ISBN/OLID/OCLC-keyed cover URLs previously made **synchronous external HTTP
calls to openlibrary.org** on every request (~265 ms each, hard ceiling of a
few req/s per worker). With `ol_db_parameters` configured, lookups now hit the
infogami Postgres schema directly (`thing`/`property`/`data`/`edition_str`):

| | Before (HTTP fallback) | After (direct DB) |
|---|---:|---:|
| Single lookup latency | ~265 ms | ~30 ms |
| Throughput `/b/olid/X-M.jpg` @ c=10 | ~4 rps (est.) | **655 rps** |
| Throughput @ c=50 | — | **794 rps** (p50 = 65 ms) |
| Throughput @ c=100 | — | 725 rps |

This also removes the circular runtime dependency between
covers.openlibrary.org and openlibrary.org when the config is enabled.

Note: enabling direct-DB mode exposed (and now requires) the `isbn_`
alias fix in both implementations — see commit history; regression cases are
in `scripts/test-coverstore-parity.sh`.

## Latency distribution (`/b/query`, c=50)

| Percentile | Legacy | Async FastAPI |
|---|---:|---:|
| p50 | 302 ms | 38 ms |
| p90 | 427 ms | 72 ms |
| p99 | 533 ms | 221 ms |

Legacy flatlines around ~250 rps at any concurrency (single sync worker);
the async service keeps climbing to c=50 before easing slightly as the DB
pool (16 connections) and threadpool saturate.

## Memory

Docker cgroup memory usage (deduplicates shared pages):

| State | Legacy covers (gunicorn, master+worker) | FastAPI covers (single uvicorn) |
|---|---:|---:|
| Idle | 98.9 MiB | 58.1 MiB |
| Under load (c=10–20 mixed reads) | 94.0 MiB | 60.5 MiB |

Per-process RSS (over-counts shared libraries):

| Process | RSS |
|---|---:|
| Legacy gunicorn master | 35 MB |
| Legacy gunicorn worker | 99 MB |
| uvicorn (app process) | 77 MB |

The FastAPI service uses roughly **40% less memory** than the legacy setup
and holds steady under load (no growth across sustained benchmark runs).
Production-style multi-worker deployments scale this linearly per worker on
both stacks.

## Why the gap looks like this

The workload is I/O-bound: every request pays a synchronous PostgreSQL
roundtrip plus filesystem access, so framework overhead is only worth
~0.4 ms/request (visible on pure-Python routes: `/` is 2.3x faster,
route-miss 404s 2.6–3.2x faster). The large wins came from:

1. Removing dead external calls (`.json` details),
2. True async I/O letting one event loop keep hundreds of DB roundtrips in
   flight over a small connection pool (vs a threadpool blocked on the GIL),
3. Direct-DB lookups eliminating external HTTP from the hot path.

Writes stay closest to parity (~1.5–2x): PIL LANCZOS thumbnailing (identical
pinned Pillow version both sides), file writes, and the INSERT dominate.

## Reproducing

```bash
# Parity + behavior suite (requires dev compose up):
scripts/test-coverstore-parity.sh        # OLD/NEW env vars override endpoints

# Example throughput measurement:
hey -z 10s -c 10 http://localhost:7075/b/query   # legacy
hey -z 10s -c 10 http://localhost:18075/b/query  # fastapi service
```

Known behavioral differences are documented in the harness header and the
package docstring; the only intentional divergence is `/b/upload` accepting
binary uploads where legacy's gunicorn multipart parser 500s.
