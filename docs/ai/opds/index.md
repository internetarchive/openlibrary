# OPDS

Open Library serves OPDS 2.0 catalogs so reading apps (Libby, PocketBook, KOReader, reader.archive.org) can browse and search the collection without a browser. A reader app points at `opds.openlibrary.org` and gets back structured JSON feeds: shelves of books, search results, edition detail, and author catalogs.

The OPDS 2.0 spec: https://specs.opds.io/opds-2.0

---

## Production Architecture

```
reader.archive.org          openlibrary.org/opds (reverse proxy)
       │                             │
       └────────────────┬────────────┘
                        │
                        ▼
           opds.openlibrary.org   (= ol-opds.prod.archive.org, Nomad)
           FastAPI — ArchiveLabs/opds.openlibrary.org
             Memcached: stale-while-revalidate (1 min fresh / 30 min stale)
                        │
                        │  GET /search.json  (one request per route handler)
                        ▼
              openlibrary.org  (internetarchive/openlibrary)
                        │
                        │  Solr query (internal)
                        ▼
                      Solr
```

**`openlibrary.org/opds` is a reverse proxy** to `opds.openlibrary.org` — not a separate system. Any request to `openlibrary.org/opds/search?query=tolkien` is handled by the FastAPI service.

The Python library `ArchiveLabs/pyopds2_openlibrary` is the intermediary: it calls `openlibrary.org`'s search and book APIs and assembles OPDS 2.0 catalog JSON. The service (`opds.openlibrary.org`) wraps it with routing, caching, and error handling.

---

## Repos

| Repo | Purpose |
|------|---------|
| `ArchiveLabs/opds.openlibrary.org` | The HTTP service — FastAPI app deployed at opds.openlibrary.org |
| `ArchiveLabs/pyopds2_openlibrary` | Python library — calls OL APIs, emits OPDS 2.0 catalog dicts |
| `internetarchive/openlibrary` | OL backend — provides `/search.json`, `/books/{olid}.json`, etc. |

---

## Key Files

### `ArchiveLabs/opds.openlibrary.org`

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI app, Sentry init, startup language-cache warming |
| `app/routes/opds.py` | All route handlers: `GET /`, `/search`, `/books/{olid}`, `/authors/{olid}` |
| `app/cache.py` | Memcached client with stale-while-revalidate; all TTL constants |
| `app/config/__init__.py` | All env-var config: `OL_BASE_URL`, timeouts, Sentry DSN, Memcached |
| `app/exceptions.py` | `AuthorNotFound`, `EditionNotFound`, `UpstreamError` |
| `tests/test_e2e.py` | e2e smoke suite — run with `make test-e2e` |
| `docs/testing-opds-locally.md` | Local dev + reader.archive.org testing guide (start here) |
| `Makefile` | `make serve`, `make test`, `make test-e2e`, `make tunnel` |

### `ArchiveLabs/pyopds2_openlibrary`

| File | Purpose |
|------|---------|
| `pyopds2_openlibrary/__init__.py` | Entire library (~2200 lines): HTTP client, retry logic, all provider/record classes |
| `tests/test_openlibrary_comprehensive.py` | Primary tests: `_get()` retry, 429 Retry-After, 5xx escalation |
| `tests/test_openlibrary_catalog.py` | Catalog construction: search, pagination, timeout assertions |

Key symbols in `__init__.py`:

| Symbol | What it is |
|--------|-----------|
| `_http_client` | Module-level `Optional[httpx.Client]` singleton — reuses TLS connections |
| `_get_http_client()` | Thread-safe lazy init with double-checked lock + atexit cleanup |
| `_get(url, *, params, timeout)` | All HTTP calls go through here — retry, 429 Retry-After honouring |
| `_RETRY_STATUS_CODES` | `{429, 500, 502, 503, 504}` — retried up to 2 times |
| `OpenLibraryDataRecord` | Pydantic model for one OL search result (work/edition) |
| `OpenLibraryDataProvider` | `search()`, `build_home_feed()`, `fetch_author()` etc. |

---

## How It Works

### Home feed (`GET /`)

1. Route handler calls `provider.build_home_feed(base, mode, language, page)`
2. `build_home_feed` fires one `_get()` call per carousel group against `openlibrary.org/search.json`
3. Results are wrapped in OPDS 2.0 `groups` structure and returned as JSON
4. Response is cached in Memcached (1 min fresh, 30 min stale-while-revalidate)

### Search feed (`GET /search`)

1. Route handler calls `provider.search(query, limit, offset, availability, language)`
2. One `_get()` call to `openlibrary.org/search.json` with the query params
3. Returns an OPDS 2.0 `publications` list with `metadata.numberOfItems` for pagination
4. Availability facets are present but **do not have `numberOfItems`** (removed in PR #41 — it required 4 extra OL requests per search)

### Cache

`app/cache.py` implements stale-while-revalidate via Memcached:

| Key | Fresh TTL | Stale window |
|-----|-----------|-------------|
| Home feed (default lang) | 1 min | 30 min |
| Home feed (non-default lang) | 1 min | — |
| Book detail | 6 hours | — |
| Author bio | 24 hours | — |
| Author catalog | 1 hour | — |
| Language options / counts | 7 days | — |

---

## Environment Variables

| Var | Default | Purpose |
|-----|---------|---------|
| `OL_BASE_URL` | `https://openlibrary.org` | Where to call OL APIs |
| `OL_USER_AGENT` | `OPDSBot/1.0 (...)` | User-agent sent to OL |
| `OL_REQUEST_TIMEOUT` | `30.0` | Seconds before HTTP timeout |
| `OPDS_BASE_URL` | `https://openlibrary.org/opds` (prod) | Self-referential links in catalog |
| `CACHE_ENABLED` | `true` | Set to `false` for local testing |
| `MEMCACHE_HOST` / `MEMCACHE_PORT` | From `NOMAD_ADDR_memcached` | Memcached location (auto-injected in prod) |
| `SENTRY_DSN` | IA Sentry org | Where 429 and error events land |
| `ENVIRONMENT` | `production` | Set to `test` to skip cache warming |

---

## How to Work on It

### pyopds2_openlibrary (no Docker needed)

```bash
cd ~/Projects/pyopds2_openlibrary

# Full test suite before every push
python3 -m pytest tests/ -x -q
# Expected: 282 passed in ~40s
```

When mocking HTTP calls, mock `pyopds2_openlibrary._get_http_client` — not `httpx.get`. The old bare-httpx pattern no longer intercepts calls since all requests go through the singleton:

```python
mock_client.get.return_value = resp  # correct
mocker.patch("httpx.get")            # wrong — won't intercept
```

### opds.openlibrary.org (no Docker needed)

```bash
cd ~/Projects/opds.openlibrary.org
pip install -r requirements.txt

# Unit tests (fast, no network)
python3 -m pytest tests/ -m "not e2e" -q
# Expected: ~158 passed in ~8s

# Automated e2e (starts local service, tests against real OL, tears down)
make test-e2e
# Expected: health, home, search, pagination, book detail, author detail all pass

# Test a local pyopds2_openlibrary branch
make test-e2e LIB=~/Projects/pyopds2_openlibrary-<slug>

# Manual: start the service
CACHE_ENABLED=false OL_BASE_URL=https://openlibrary.org \
  uvicorn app.main:app --host 127.0.0.1 --port 8090
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8090/health
# Expected: 200

# Expose to reader.archive.org for manual verification
make tunnel
# → Open https://reader.archive.org/?opds=https://<slug>.trycloudflare.com
```

See `docs/testing-opds-locally.md` for the full local testing guide including the reader.archive.org checklist.

---

## Known Issues / Gotchas

- **`CACHE_ENABLED=false` is required for local testing.** When the cache is on, responses are served stale and code changes won't be visible.

- **`docker-compose.yml` hardcodes the worktree name.** The compose file uses `context: ../` + `dockerfile: opds.openlibrary.org/docker/Dockerfile`, which only resolves when the checkout is named exactly `opds.openlibrary.org`. For any worktree with a slug suffix, use `uvicorn` directly — it's faster anyway.

- **Use `python3`, not `python`.** macOS brew installs Python 3 as `python3`. Bare `python` hits the system stub.

- **httpx2 deprecation warning in tests.** `starlette.testclient` warns about httpx vs httpx2. Harmless — tests pass. Add `--disable-warnings` to suppress.

- **Availability facet `numberOfItems` was intentionally removed** (PR #41). If you see `numberOfItems` on availability facet links, something regressed — it required 4 extra OL requests per search and was dropped for performance.

- **`opds-system.md` in `pm/workflows/` has a stale "Performance Fix" section.** It describes PRs pyopds2 #102 and OL #12987 (a `/search/carousels.json` batch endpoint) as the June 2026 performance work. Both were closed without merging. The actual fix was opds #41. Ignore that section.

---

## Related Systems

- **Solr** — all OPDS search calls ultimately hit Solr via `openlibrary.org/search.json`. See [Solr docs](../solr/index.md).
- **OL FastAPI layer** — `openlibrary/fastapi/search.py` defines the `/search.json` endpoint the OPDS service calls.
- **reader.archive.org** — the primary production consumer of the OPDS feed; production traffic is live and immediately visible.
