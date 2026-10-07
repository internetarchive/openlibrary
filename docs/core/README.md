# Core Operations

> **Status:** partial
> **Sources:** `raw/openlibrary-docs-ai/README.md`
> **Last ingested:** 2026-06-27

The runtime machinery of Open Library: how the app starts, how requests are routed, what framework layer sits under everything, and how the legacy web.py system is being incrementally replaced by FastAPI.

---

## How It Works

Open Library runs on **Infogami**, a wiki-style application framework built on web.py. The app loads via `openlibrary/code.py`, which initialises Infogami and loads plugins from `openlibrary/plugins/`. Each plugin's `code.py` registers its own routes and handlers.

A second ASGI application layer — FastAPI — runs alongside the legacy app. The ASGI app in `openlibrary/asgi_app.py` mounts FastAPI on specific path prefixes and falls back to the legacy WSGI app for everything else.

```
HTTP request
  → nginx/haproxy (see [[infrastructure]])
  → ASGI app (openlibrary/asgi_app.py)
      → FastAPI router  (if path matches a FastAPI route)
      → Infogami/web.py (everything else)
            → plugin code.py route handlers
```

## Why It Exists

Infogami was chosen in the mid-2000s as a flexible wiki/data framework. It provides the versioned object storage model (Works, Editions, Authors), the plugin routing architecture, and the template engine. FastAPI is being introduced incrementally to gain async support and modern API ergonomics without a full rewrite.

## How It Is Used

### Adding a web.py/Infogami route

Routes are classes in a plugin's `code.py` extending `delegate.page`:

```python
class my_feature(delegate.page):
    path = r'/my-feature(/.*)?'   # regex

    def GET(self, subpath=None):
        return render_template('my_feature/index', subpath)
```

`render_template("path/name", args)` maps to `templates/path/name.html`.

### Adding a FastAPI route

New endpoints go in `openlibrary/fastapi/`. Each file contains an `APIRouter` registered in `openlibrary/asgi_app.py`.

```python
from fastapi import APIRouter
router = APIRouter()

@router.get('/api/my-feature')
async def my_feature():
    ...
```

**Rule of thumb:** New public API, async, Pydantic models → FastAPI. Full HTML page using Infogami templates or touching Infogami object types directly → web.py for now.

## Subcomponents and Architecture

### Infogami
The foundational layer. Provides: versioned object storage, plugin loader, web.py routing, Templetor template engine, Infobase client API. Lives in `vendor/infogami/` as a git submodule. Effectively frozen — OL owns all maintenance. See [[infogami]].

OL types (Work, Edition, Author) are registered on Infogami via `openlibrary/core/schema.py` and `openlibrary/core/models.py`. See [[imports]] for the data model.

### Plugin system

| Plugin | Owns |
|---|---|
| `plugins/openlibrary/` | Public-facing pages, core site routes, JS source files (`js/`), ~71 route handler classes |
| `plugins/upstream/` | All data mutations: account management, borrowing, add/edit book, merge authors |
| `plugins/worksearch/` | Search routes, Solr integration, autocomplete — see [[search]] |
| `plugins/importapi/` | Machine-readable book import API — see [[imports]] |
| `plugins/books/` | Legacy book API (JSON/RDF), dynamic/read links — see [[public-apis]] |
| `plugins/admin/` | Admin dashboard, stats, monitoring |
| `plugins/inside/` | IA PDF viewer integration |
| `plugins/recaptcha/` | reCAPTCHA for form spam protection |

### FastAPI layer
`openlibrary/fastapi/` — 20 files, active migration. Covers: account, lists, books, search, importapi, checkins, reading goals, partials, merge_authors, internal APIs. Most traffic still flows through web.py.

### Background jobs
No async job queue. All background work is cron scripts in `scripts/`, wrapped by `scripts/cron_wrapper.py` (Sentry-monitored). No retry logic; a failed cron fails silently unless cron_wrapper catches it. See [[infrastructure]].

### Bots
`internetarchive/openlibrary-bots` — separate repo of cleanup bots built on [[ol-client]].

### Affiliate server (BookWorm)

`scripts/affiliate_server.py` — a **separate web.py application** (not part of the main OL app) that acts as a caching proxy to the Amazon Product API and Google Books API. Default port: 31337. Called "BookWorm" internally.

**What it does:**
1. Receives `GET /isbn/{identifier}` (ISBN-10, ISBN-13, or B* ASIN) from the main OL app
2. Checks Memcache for `amazon_product_{isbn_13}` — returns `{"status": "success", "hit": {...}}` if found
3. On cache miss: enqueues the identifier in a `PriorityQueue`; background `AmazonLookupWorker` thread batches up to 10 items, calls `AmazonCreatorsAPI.get_products()`, stores results in Memcache (1-week TTL)
4. Falls back to Google Books API for ISBN-13-only identifiers that Amazon misses
5. Also stages found books for import via `Batch.add_items(name="amz")`

**Priority levels:**
- `?high_priority=true` — caller waits up to 5 seconds (5 retries × 1s) for the Amazon API to respond; used on edition detail pages where the user is waiting
- `?high_priority=false` (default) — fire-and-forget; returns `{"status": "submitted"}`

**`?stage_import=false`** — fetch metadata but do NOT enqueue for import. Used when displaying buy links without triggering an import workflow.

**How the main app calls it:**
```python
# vendors.py::get_amazon_metadata_from_affiliate_server()
r = requests.get(
    f"http://{affiliate_server_url}/isbn/{id_}?high_priority={priority}&stage_import={stage}",
    timeout=timeout,
)
data = r.json().get("hit")  # returns cleaned Amazon metadata, or None
```
`affiliate_server_url` comes from `config.get("affiliate_server")` in openlibrary.yml.

**Other endpoints:**
- `GET /status` — JSON: thread alive?, queue size, queue contents
- `GET /clear` — clears the queue; returns pre-clear queue size

**Amazon API config:** requires `amazon_creators_api` (`key`, `secret`, `id` from olsystem); `load_config` raises without it. Throttling: 0.9s between calls. The legacy PA-API (`amazon_api`) fallback was **removed** in [#13315](https://github.com/internetarchive/openlibrary/pull/13315) (2026-08-12) — PA-API was deprecated April 2026. Note that prior to that, legacy was checked *first*, so a box with both credential sets silently ran PA-API and never constructed `AmazonCreatorsAPI`; that misconfiguration was a contributing factor in the ~12h outage post-mortem [#13277](https://github.com/internetarchive/openlibrary/issues/13277).

**979-prefix ISBN-13s need a keyword search, not a lookup.** `get_items` is an exact-id lookup accepting only an ISBN-10 or a real ASIN. A 979 ISBN-13 has **no ISBN-10 equivalent**, and Amazon assigns such books an arbitrary `B*` ASIN unrelated to the ISBN — so no conversion can reach them. Historically `Submit.GET` computed `key = isbn_10 or b_asin` → `None` and exited to Google Books or `{"error": "rejected_isbn"}` before any Amazon call, making the Amazon branch dead code for the whole 979 range. `AmazonCreatorsAPI.get_product_by_isbn_13()` resolves them via `search_items` instead ([#13316](https://github.com/internetarchive/openlibrary/issues/13316)). Two things to know if you touch this path:

- **Search is not an exact-match lookup.** Results must be verified against the item's own `external_ids.eans` before being cached or staged, or you import the wrong book under the right ISBN.
- **`search_items` is one ISBN per call**, with no batching (vs. 10/call for `get_items`), so it is markedly more expensive per result. It runs only in the background worker — never inline in `Submit.GET`, which would put a fresh Amazon round trip back on the request path that caused [#13277](https://github.com/internetarchive/openlibrary/issues/13277).

Related: `vendors.py::amazon_affiliate_url()` handles the same 979 limitation on the *link* side by falling back to an Amazon search URL ([#6572](https://github.com/internetarchive/openlibrary/issues/6572)). Both gate on `isbn_13_to_isbn_10()` returning `None` rather than a raw `startswith("979")` check, keeping ISBN structural knowledge inside the isbn utils.

**What it doesn't do:** It does NOT generate the Amazon affiliate link URLs shown on edition pages — those are built by `vendors.py::amazon_affiliate_url()` (a pure function using the affiliate tag). BookWorm fetches metadata; `amazon_affiliate_url` constructs the buy link.

## Key Files

| File | Purpose |
|---|---|
| `openlibrary/code.py` | App entry point; loads Infogami, initialises plugins |
| `openlibrary/asgi_app.py` | ASGI app; mounts FastAPI alongside legacy WSGI |
| `openlibrary/fastapi/` | FastAPI routers (new endpoints) |
| `openlibrary/plugins/*/code.py` | Plugin route handlers (web.py/Infogami) |
| `openlibrary/core/schema.py` | Registers OL types on Infogami |
| `openlibrary/core/models.py` | ORM-like methods for Work, Edition, Author |
| `vendor/infogami/` | Infogami git submodule |
| `scripts/cron_wrapper.py` | Wraps cron jobs with Sentry monitoring |

## Configuration

- Python 3.14; Ruff linting; line length 162
- Dev setup: `make git` → `docker compose up` → http://localhost:8080
- FastAPI dev server: port 18080
- Branch naming: `{issue-number}/{type}/{slug}`

## Testing

```bash
make test-py-uv          # Python tests outside Docker (preferred)
docker compose run --rm home make test-py
pytest openlibrary/core/tests/test_models.py::test_fn -xvs
npm run test:js
make test                # All tests
```

## Performance

Infogami object reads go through `openlibrary/core/cache.py` (Memcache). FastAPI endpoints are async; web.py handlers are synchronous. Most page-load cost is in [[search]] (Solr) and [[lending]] (IA availability checks).

## Related Processes

- Solr updater background service — see [[search]]
- Batch import crons — see [[imports]] and [[infrastructure]]
- Deployment via olsystem — see [[infrastructure]]

## What's Broken / Fragile / Unimplemented

- FastAPI migration is partial with no clear completion timeline; some routes exist in both frameworks
- Infogami is frozen upstream — OL owns all submodule maintenance
- No retry logic or dead-letter queue for background cron jobs

## Common Confusion

- **Templetor ≠ Jinja2.** Templates use web.py's Templetor syntax (`$def with (args)`, `$variable`, `$:variable` unescaped). Wrong assumptions cause subtle rendering bugs.
- **`plugins/openlibrary/` ≠ the whole app.** It's one plugin. `plugins/upstream/` owns mutations; `plugins/worksearch/` owns search.
- **FastAPI and web.py run on different ports in dev.** localhost:8080 = web.py/Infogami; localhost:18080 = FastAPI. The ASGI app routes between them in production.

## Dependencies

**Depends on:** Infogami (`vendor/infogami/`), PostgreSQL, Memcache — see [[infrastructure]]
**Depended on by:** all other domains — they all sit on top of this routing and type system.

## Provisioning / Services

Docker Compose for development. Production via [[infrastructure]] (olsystem, supervisor, nginx/haproxy).

---

*Sources: `raw/openlibrary-docs-ai/README.md` · See [[README]] · [[METHODOLOGY]]*
