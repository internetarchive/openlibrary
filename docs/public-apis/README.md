# Public APIs & Partials

> **Status:** partial
> **Sources:** `raw/openlibrary-docs-ai/opds/index.md`
> **Last ingested:** 2026-06-27

Open Library's machine-readable surface: OPDS 2.0 catalogs, Books/Authors/Search JSON APIs, import endpoint, and HTML partials. This page currently covers OPDS in depth. Books API (JSON/RDF), partials, and advanced FastAPI endpoints need a follow-up ingest.

---

## OPDS 2.0 (opds.openlibrary.org)

OPDS 2.0 catalogs let reading apps (Libby, PocketBook, KOReader, reader.archive.org) browse and search OL without a browser.

### Architecture

```
reader.archive.org    openlibrary.org/opds (reverse proxy)
       │                        │
       └──────────┬─────────────┘
                  ▼
     opds.openlibrary.org   (= ol-opds.prod.archive.org, Nomad)
     FastAPI — ArchiveLabs/opds.openlibrary.org
       Memcached: stale-while-revalidate (1 min fresh / 30 min stale)
                  │
                  │  GET /search.json  (one request per route handler)
                  ▼
        openlibrary.org (internetarchive/openlibrary)
                  │
                  ▼
                Solr
```

`openlibrary.org/opds` is a **reverse proxy** — not a separate system. All `/opds/` traffic is handled by the FastAPI service at `opds.openlibrary.org`.

### Repos

| Repo | Role |
|------|------|
| `ArchiveLabs/pyopds2` | Base OPDS 2.0 data model (`Catalog`, `DataProvider`, `DataProviderRecord`, `Link`, `Metadata`, `Publication`) |
| `ArchiveLabs/pyopds2_openlibrary` | OL-specific implementation — extends pyopds2; calls OL search/book APIs; retry logic |
| `ArchiveLabs/opds.openlibrary.org` | HTTP service — FastAPI, Memcached, Sentry; deployed on Nomad |
| `internetarchive/openlibrary` | Backend — provides `/search.json`, `/books/{olid}.json`, etc. |

### How a search request flows

1. Reading app → `GET opds.openlibrary.org/search?query=tolkien`
2. Route handler in `app/routes/opds.py` calls `provider.search(query, ...)`
3. `pyopds2_openlibrary.__init__._get()` → `openlibrary.org/search.json`
4. OL backend hits Solr (see [[search]])
5. Results wrapped in OPDS 2.0 `publications` JSON → Memcached → returned

### Cache TTLs

| Resource | Fresh TTL | Stale window |
|----------|-----------|-------------|
| Home feed (default lang) | 1 min | 30 min (stale-while-revalidate) |
| Home feed (other lang) | 1 min | — |
| Book detail | 6 hours | — |
| Author bio | 24 hours | — |
| Author catalog | 1 hour | — |
| Language options | 7 days | — |

### Key files

| File | Purpose |
|------|---------|
| `opds.openlibrary.org/app/main.py` | FastAPI app, Sentry init, startup language-cache warming |
| `opds.openlibrary.org/app/routes/opds.py` | Route handlers: `GET /`, `/search`, `/books/{olid}`, `/authors/{olid}` |
| `opds.openlibrary.org/app/cache.py` | Memcached client with stale-while-revalidate; TTL constants |
| `opds.openlibrary.org/app/config/__init__.py` | All env-var config: `OL_BASE_URL`, timeouts, Sentry DSN, Memcached |
| `pyopds2_openlibrary/__init__.py` | Entire library (~2200 lines): HTTP client singleton, retry logic, all provider/record classes |

Key symbols in `pyopds2_openlibrary/__init__.py`:

| Symbol | What it is |
|--------|-----------|
| `_http_client` | Module-level httpx.Client singleton — reuses TLS connections |
| `_get_http_client()` | Thread-safe lazy init; atexit cleanup |
| `_get(url, *, params, timeout)` | All HTTP calls — retry on `{429, 500, 502, 503, 504}`, 2 retries max; 429 Retry-After honoured |
| `OpenLibraryDataRecord` | Pydantic model for one OL search result |
| `OpenLibraryDataProvider` | `search()`, `build_home_feed()`, `fetch_author()` |

### Environment variables

| Var | Default | Purpose |
|-----|---------|---------|
| `OL_BASE_URL` | `https://openlibrary.org` | Where to call OL APIs |
| `OL_REQUEST_TIMEOUT` | `30.0` | Seconds before timeout |
| `OPDS_BASE_URL` | `https://openlibrary.org/opds` | Self-referential links in catalog |
| `CACHE_ENABLED` | `true` | Set to `false` for local testing |
| `MEMCACHE_HOST` / `MEMCACHE_PORT` | From `NOMAD_ADDR_memcached` | Auto-injected in prod |
| `ENVIRONMENT` | `production` | Set to `test` to skip cache warming |

### Local development

```bash
# pyopds2_openlibrary — no Docker needed
cd ~/Projects/pyopds2_openlibrary
python3 -m pytest tests/ -x -q   # 282 passed in ~40s

# opds.openlibrary.org — no Docker needed
cd ~/Projects/opds.openlibrary.org
pip install -r requirements.txt
python3 -m pytest tests/ -m "not e2e" -q   # ~158 passed in ~8s

# Start service manually
CACHE_ENABLED=false OL_BASE_URL=https://openlibrary.org \
  uvicorn app.main:app --host 127.0.0.1 --port 8090

# Automated e2e (starts local service, tests against real OL)
make test-e2e

# Test against reader.archive.org
make tunnel   # → https://reader.archive.org/?opds=https://<slug>.trycloudflare.com
```

---

## Books API (`/api/books`)

The Books API lets callers look up editions by any identifier (ISBN, LCCN, OCLC, OLID). It was web.py and is now **FastAPI** at `openlibrary/fastapi/books.py` — the web.py handler at `plugins/openlibrary/deprecated_handler.py` proxies to FastAPI in dev and raises an error in prod.

### Endpoints

| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/api/books.json?bibkeys=...` | Main Books API |
| `GET` | `/api/books?bibkeys=...` | Same; `include_in_schema=False` (undocumented alias) |

**bibkeys** — comma-separated identifiers. Accepted types:
- ISBN (plain number, or `ISBN:`, `isbn_` prefix, 10 or 13 digits)
- LCCN (`LCCN:sa 64009056`)
- OCLC (`OCLC:123456`)
- OCAID (`ocaid:...`)
- OLID (`OL24630277M`, or `OLID:...`)

Parsing logic: `dynlinks.split_key()` — normalizes all these into Infobase field queries.

### Response modes (`jscmd` param)

| `jscmd` | Returns | Notes |
|---------|---------|-------|
| `viewapi` (default) | Minimal: `{bib_key, info_url, preview, preview_url, thumbnail_url}` | Used by embed widgets |
| `data` | Full bibliographic: authors, identifiers, publishers, subjects, excerpts, cover URLs, ebooks | Joins Edition + Work objects; assembled by `DataProcessor` |
| `details` | Raw Infobase edition object + `details` key | For integrators that need the full record |

**`jscmd=data` response structure** (curated by `DataProcessor.process_doc()`):
```json
{
  "url": "https://openlibrary.org/books/OL43M/Harry_Potter",
  "key": "/books/OL43M",
  "title": "...",
  "authors": [{"url": "...", "name": "..."}],
  "number_of_pages": 309,
  "identifiers": {"isbn_10": [...], "isbn_13": [...], "lccn": [...], "oclc": [...], "openlibrary": ["OL43M"]},
  "classifications": {"lc_classifications": [...], "dewey_decimal_class": [...]},
  "publishers": [{"name": "..."}],
  "publish_date": "1998",
  "subjects": [{"name": "...", "url": "https://openlibrary.org/subjects/..."}],
  "excerpts": [...],
  "ebooks": [{"preview_url": "...", "availability": "borrow|full|restricted|noview", "borrow_url": "...", "formats": {...}}],
  "cover": {"small": "...", "medium": "...", "large": "..."}
}
```
Empty fields are trimmed (the `trim()` function removes falsy values).

### Missing ISBN auto-import

If a bibkey is an ISBN not found in OL:
- `high_priority=true` → `Edition.from_isbn()` called immediately; if found, imported and returned
- `high_priority=false` (default) → missed ISBNs queued to the affiliate server (BookWorm); returns nothing for that ISBN this call

Availability (`preview` field) comes from Solr — `ebook_access` field mapped to `full/borrow/restricted/noview`. See [[lending]] and [[search]].

### Key code path

```
GET /api/books.json?bibkeys=ISBN:0590353427&jscmd=data
  → fastapi/books.py::get_books()
      → dynlinks.dynlinks(bib_keys, options)
          → query_docs(bib_keys)          # Infobase lookup
          → add_availability(edition_dicts) # Solr ebook_access
          → DataProcessor().process(result) # jscmd=data join
          → format_result(edition_dicts, options)
```

---

## Raw Infobase JSON (`/books/{olid}.json`, `/works/{olid}.json`, `/authors/{olid}.json`)

These are **not the same as `/api/books`**. The `.json` extension is handled by Infogami's generic `view` mode (`encoding = "json"` in `infogami/plugins/api/code.py`) — it calls `Infobase.get(key)` and returns the raw stored object.

- `/books/OL123M.json` → the raw Edition Infobase object (all stored fields, no joins, no curation)
- `/works/OL456W.json` → the raw Work Infobase object
- `/authors/OL789A.json` → the raw Author Infobase object

These are **read-only views of the Infobase store**, not computed APIs. The schema is whatever Infobase has stored. No availability, no subject URLs, no cover URL normalization — just the raw document.

`?v=N` param: request a specific revision (version number).

---

## Volumes API (`/api/volumes/...`) — HathiTrust-style

Modeled after the HathiTrust Bibliographic API. Provides loan status and all physical/digital editions of a work. Implemented in `plugins/books/readlinks.py` + `fastapi/books.py`.

| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/api/volumes/brief/isbn/{isbn}.json` | Single identifier lookup |
| `GET` | `/api/volumes/full/isbn/{isbn}.json` | Full detail |
| `GET` | `/api/volumes/brief/json/{isbn:...}&#124;{oclc:...}.json` | Multi-identifier batch |

**Response structure:**
```json
{
  "isbn:059035342X": {
    "records": {
      "/books/OL43M": {
        "isbns": [...], "lccns": [...], "oclcs": [...], "olids": [...],
        "publishDates": [...],
        "recordURL": "https://openlibrary.org/books/OL43M/...",
        "data": { ... },   // jscmd=data output
        "details": { ... } // raw infobase details
      }
    },
    "items": [
      {
        "match": "exact|similar",
        "status": "full access|lendable|restricted|checked out",
        "fromRecord": "/books/OL43M",
        "ol-edition-id": "OL43M",
        "ol-work-id": "OL456W",
        "publishDate": "1998",
        "itemURL": "http://www.archive.org/stream/..."
      }
    ]
  }
}
```
Items come from Solr's `ia` field (up to 500 IA items per work). Loan status checked from `web.ctx.site.store("ebooks/{iaid}")`.

---

## IA Link/Unlink API (`/api/link`, `/api/unlink`)

Lets archive.org associate or disassociate an OCAID (Internet Archive item ID) with an OL edition. Used when: MARC is disassociated from an IA item, ISBN/metadata corrections mean an item was linked to the wrong edition, or digitization writes the ocaid back to OL (OL otherwise fails to import items it can't find via `openlibrary_edition:*`).

**Auth**: HMAC-SHA256 digest over a pipe-delimited `msg` (`ocaid|timestamp` for unlink, `ocaid|olid|timestamp` for link), verified via `HMACToken.verify(digest, msg, "ia_sync_secret", unix_time=True)` (`openlibrary/core/auth.py`). `verify()` only `rsplit`s on the *last* delimiter to find the timestamp — so a caller-side msg format change (e.g. adding a middle field) is technically compatible with verification, but still requires coordinating the archive.org-side caller, which lives outside this repo.

**Where the code actually lives — this is confusing, read carefully:**

| Path | Live implementation | Status |
|------|---------------------|--------|
| `/api/unlink` | `unlink_ia_ol` class in `openlibrary/plugins/openlibrary/api.py` (web.py, `path = "/api/unlink"`) | **The only implementation.** Runs in the `web` compose service (port 8080), started via `scripts/openlibrary-server` (pure web.py/infogami WSGI — see `load_infogami`/`OLWSGIServer` in that script). |
| `/api/link` | Two implementations exist: (1) `link_ia_ol` class in `plugins/openlibrary/api.py` (web.py, same file as above) — **dead code in a fully-routed deployment**, shadowed by (2) `link_ia_ol` function in `openlibrary/fastapi/link.py`, registered via `app.include_router(link_router)` in `openlibrary/asgi_app.py`. The FastAPI app runs as a *separate* compose service, `fast_web` (port 18080, `docker/ol-web-fastapi-start.sh` → `uvicorn ... openlibrary.asgi_app:app`) — not the same process as `web`. Whichever a reverse proxy routes `/api/link` to in prod is the one that actually runs; hitting the `web` container directly on 8080 (as local dev commonly does) still executes the older web.py version. |

There is also an **unwired stub** `async def unlink_ia_ol(): pass` in `openlibrary/fastapi/internal/api.py` (no `@router` decorator, not included by any router) — looks like an abandoned start on migrating `/api/unlink` to FastAPI to match `link.py`. Don't confuse it with the live handler.

**Save comment**: `unlink_ia_ol.make_dark(edition, ocaid, comment="")` passes the caller-supplied `comment` straight to `site.save(..., action="edit-edition-ocaid")`, falling back to a default (`"Unlink OCAID: Item no longer available"`) if omitted. `comment` is a plain unsigned `web.input()` field, not part of the signed `msg` — it's free text with no OL-side vocabulary or whitelist. (An earlier draft of internetarchive/openlibrary#13171 tried an `op` code — `"dark"`/`"mismatch"` — mapped internally to fixed comment strings via a `UNLINK_COMMENTS` table, mirroring `bestbook_award.POST`'s `op` pattern in the same file. @hornc flagged that as a separation-of-concerns violation: OL shouldn't need an archive.org-specific vocabulary when the caller can just supply the comment text directly, same as any normal edit. The PR was revised to the free-text `comment` field accordingly — the `op`/`UNLINK_COMMENTS` design never shipped.) See internetarchive/openlibrary#13171.

---

## Other Public APIs

| API | Entry point | Status | See |
|-----|-------------|--------|-----|
| Search API | `/search.json`, `/search/authors.json` | FastAPI | [[search]] |
| Import API | `/api/import`, `/import/batch/new` | web.py | [[imports]] |
| Covers API | `covers.openlibrary.org` | standalone | [[covers]] |
| Lists API | `/lists/{olid}.json` | Infogami .json encoding | [[features]] |
| OPDS | `opds.openlibrary.org/opds/...` | FastAPI (Nomad) | See above |
| Partials | Various `/partials/` paths | FastAPI | HTML fragments |

---

## What's Broken / Fragile

### ⚠️ Contradiction: PR #12987 status

`raw/openlibrary-docs-ai/solr/priorities.md` (dated June 2026): PR #12987 (`/search/carousels.json`) is "open, CI passing, ready for code review."

`raw/openlibrary-docs-ai/opds/index.md`: "Both [pyopds2 #102 and OL #12987] were closed without merging. The actual fix was opds #41."

These directly conflict. **Verify current status on GitHub before relying on either.** The OPDS source says the workaround was already shipped via `opds #41`; the Solr priorities source says it was still open and needed. If #12987 was closed, update [[search]] PR table accordingly.

### docker-compose.yml worktree naming

`opds.openlibrary.org/docker-compose.yml` hardcodes the checkout directory name. Any worktree with a slug suffix breaks the build. Use `uvicorn` directly — it's faster anyway.

### Mocking pattern

Mock `pyopds2_openlibrary._get_http_client`, not `httpx.get`. The old bare-httpx pattern doesn't intercept calls since all requests go through the singleton client.

---

## Common Confusion

- **`openlibrary.org/opds` is a reverse proxy** — it's not a separate codebase. All OPDS logic lives in `opds.openlibrary.org` (the Nomad service). Editing OL's web.py plugin won't change OPDS behavior.

- **`CACHE_ENABLED=false` required locally** — with the cache on, code changes won't be visible. Always set this for local development.

- **Availability facet has no `numberOfItems`** — intentionally removed (opds PR #41). It required 4 extra OL requests per search. If `numberOfItems` appears on availability facet links in a new PR, it's a regression.

---

## Dependencies

**Depends on:**
- [[search]] — all OPDS search calls hit Solr via `openlibrary.org/search.json`
- [[core-operations]] — OL backend provides the Books/Authors/Works JSON APIs the OPDS service calls
- [[imports]] — `/api/import` endpoint lives in the importapi plugin
- [[infrastructure]] — `opds.openlibrary.org` runs on Nomad; see also [[infrastructure]] for deployment

**Depended on by:**
- reader.archive.org — primary production OPDS consumer
- Reading apps (Libby, PocketBook, KOReader)

---

## Provisioning / Services

- `opds.openlibrary.org` deployed via Nomad at `ol-opds.prod.archive.org`
- Memcached for stale-while-revalidate caching
- Sentry for error tracking (429s and upstream errors)

---

*Sources: `raw/openlibrary-docs-ai/opds/index.md` · code synthesis: `fastapi/books.py`, `plugins/books/dynlinks.py`, `plugins/books/readlinks.py`, `infogami/plugins/api/code.py` · See [[README]] · [[METHODOLOGY]]*
