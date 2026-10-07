# Search (Solr)

> **Status:** partial
> **Sources:** `raw/openlibrary-docs-ai/solr/index.md`, `raw/openlibrary-docs-ai/solr/priorities.md`
> **Last ingested:** 2026-06-27

Apache Solr 10 is Open Library's search index. It powers all search pages, the Public Search API, subject pages, and OPDS feeds. The index stores denormalized Work documents (with embedded Edition data) and separate Author and List documents.

---

## How It Works

### Indexing flow

```
OL database (postgres/infobase)
    │
    │  solr-updater daemon (scripts/solr_updater/solr_updater.py)
    │  polls Infobase changelog at /log/{offset} → extract changed OL keys
    ▼
openlibrary/solr/update.py → update_keys()
    │  runs updaters in order: EditionSolrUpdater → WorkSolrUpdater → AuthorSolrUpdater → ListSolrUpdater
    │  per key: fetch document from data_provider
    │           run updater.update_key(doc) → SolrUpdateRequest
    │           accumulate adds/deletes
    ▼
openlibrary/solr/utils.py → solr_update()
    │  httpx POST to Solr /update?commit=true with JSON body
    ▼
Solr (ol-solr0 / ol-solr2 via HAProxy port 8984)
```

**solr-updater state file**: `/solr-updater-data/solr_state` — stores the last consumed changelog offset as `YYYY-MM-DD:N`. On startup, the daemon resumes from this offset. Loss of this file means the updater must restart from scratch or a known offset.

**End-to-end latency**: solr-updater polls with 0–5s latency; Solr's `autoSoftCommit.maxTime` is **60000ms in production**. Combined: **~60–65 seconds** from an OL edit to appearing in search in the happy path.

> Corrected 2026-08-10. The `3000` in `solrconfig.xml` is only a `${solr.autoSoftCommit.maxTime:3000}` fallback and is overridden in *every* environment: 60000 in `compose.production.yaml`, `compose.near-prod.yaml` and `compose.yaml`; 1000 in `compose.override.yaml` (local dev); -1 in the solr_builder. The 3-8s figure was never true anywhere.

### Document types

Four types share the single `openlibrary` Solr core, distinguished by the `type` field:

| Type | Key format | Notes |
|------|-----------|-------|
| `work` | `/works/OL123W` | Main document; embeds edition data as nested docs |
| `work` (orphaned edition) | `/works/OL123M` | Fake key for editions with no parent work |
| `author` | `/authors/OL123A` | Queries Solr itself to aggregate work stats |
| `list` | `/lists/OL123L` | |

Subjects are **not stored as documents** — they are derived at query time from `subject_facet` values.

### WorkSolrBuilder

The most complex piece (`updater/work.py`, 678 lines). `build()` assembles a full work document by:
1. Collecting identifiers (`id_*`) from all editions
2. Building subject fields (`subject`, `subject_facet`, `subject_key`, plus `people/places/times`)
3. Fetching ratings and reading log from `data_provider`
4. Merging trending scores (`trending_score_hourly_*`, `trending_score_daily_*`)

Key computed fields:

| Field | How computed |
|-------|-------------|
| `seed` | Work key + edition keys + author keys + subject keys (used for list membership queries) |
| `title_sort` | Articles moved to end: "The Great Gatsby" → "Great Gatsby, The" |
| `ebook_access` | `max(ebook_access for all editions)` — best access level across editions |
| `first_publish_year` | `min(publish_year for all editions)` |
| `number_of_pages_median` | `ceil(median(pages for all editions))` |
| `osp_count` | Open Syllabus Project lookup from `/solr-updater-data/osp_totals.db` |
| `author_facet` | `["{OL key} {author name}", ...]` — parsed by `read_author_facet()` splitting at first space |

### EditionSolrBuilder

Editions index as **nested Solr documents** (block-join) within their parent work. Key behaviors:
- Duplicates `author_name`, `author_key`, `author_facet` from the parent work onto each edition
- `isbn`: stores both ISBN-10 and ISBN-13, with `opposite_isbn()` complementary conversions
- Dynamic `id_*` fields from `edition.identifiers` (special chars in key → `_`)
- `ebook_access` enum value + `ebook_provider`, `has_fulltext`, `public_scan_b`

**Orphaned edition handling**: if an edition has no `works` field, `EditionSolrUpdater` emits a fake work key `/works/OL{id}M` in `new_keys`, and `WorkSolrUpdater` indexes that edition as a standalone work document.

### AuthorSolrBuilder

Unique: **queries Solr** during indexing to aggregate statistics from all of the author's works via the JSON Facet API. It computes `top_work`, `work_count`, `top_subjects`, and aggregated reading log + ratings counts. Because it reads Solr, author indexing order matters — works must be indexed before the author that owns them.

### Cascading updates

`update_keys()` key behaviors:
- **Redirect handling**: key resolving to `/type/redirect` → delete original, index redirect target
- **Cascading**: `EditionSolrUpdater.update_key()` returns the parent work's key in `new_keys`, triggering work re-index
- **Fake work keys**: `/works/OL123M` triggers fetching `/books/OL123M` instead

---

## Why It Exists

Search is the primary way users discover books. Without Solr, OL has no fast text search, no faceting, no availability filtering, no subject pages, and no OPDS feeds. Solr denormalizes the Work+Edition+Author graph (spread across Infobase) into flat, queryable documents — Infobase's versioned object store is not designed for full-text search.

---

## How It Is Used

### Search API parameters (`/search.json`)

| Param | Notes |
|-------|-------|
| `q` | Main query. Lucene syntax supported. Field aliases: `title:`, `author:`, `subject:`, `isbn:` |
| `title`, `author`, `subject`, `place`, `person`, `time`, `publisher`, `isbn` | Structured field filters |
| `has_fulltext` | `true` → `ebook_access:[borrowable TO *]` |
| `public_scan` | `true` → `ebook_access:public` |
| `language` | 3-letter ISO codes; multiple values are OR'd |
| `author_key` | OL author key (e.g. `OL1394244A`) |
| `sort` | See sort options below |
| `fields` | Comma-separated Solr fields; defaults to `WorkSearchScheme.default_fetched_fields` |
| `page`, `limit`, `offset` | Pagination |

**Note**: `search.json` disables facets for performance. Facets only return on the HTML `/search` page.

### Availability filters

`ebook_access` is a **sortable enum** (`enumsConfig.xml`): `protected` < `printdisabled` < `borrowable` < `public`.

| UI filter | Solr fq |
|-----------|---------|
| "Readable online" | `ebook_access:[borrowable TO *]` |
| "Borrow online" | `ebook_access:[borrowable TO borrowable]` |
| "Free to read" | `ebook_access:public` |

**`AVAILABILITY_TO_PARAMS` in `worksearch/code.py` MUST stay in sync with `constants.js`** — both encode the same mapping. Drift between them is a frequent bug source.

### Sort options

| Value | Sorts by |
|-------|---------|
| `editions` | `edition_count desc` |
| `new` / `old` | `first_publish_year` desc/asc |
| `title` | `title_sort asc` |
| `rating` | `ratings_sortable` |
| `readinglog` | `readinglog_count desc` |
| `trending` | `def(trending_z_score, 0) desc` |
| `random` | `random_1 asc` |
| `random.hourly` | `random_{YYYYMMDTHH} asc` — hourly-seeded |
| `random.daily` | `random_{YYYYMMDD} asc` — daily-seeded |
| `ebook_access` | Enum value (public first) |
| `osp_count` | Open Syllabus Project citation count |
| `lcc_sort` / `ddc_sort` | Library classification |

### Local dev commands

```bash
# Check Solr is up
curl "http://localhost:8983/solr/openlibrary/select?q=*:*&rows=0"

# Full reindex from DB (10–30 min)
docker compose run --rm home make reindex-solr

# If schema mismatch after changing managed-schema.xml.
#
# NAME THE VOLUME FROM YOUR OWN PROJECT. The Solr data volume is per compose
# project, so a worktree has its own; a bare `openlibrary_solr-data` is the MAIN
# checkout's, and removing it from inside a worktree destroys an index that is
# not yours and that another agent may be mid-run against.
#
# `docker/ol-local-solr-start.sh` prints the bare name in its own recovery
# instructions, and so do several docs. Do not copy them verbatim from a
# worktree. Confirmed 2026-10-03: 11 occurrences of the bare name across 8
# files in `openlibrary` plus this page.
#
# Ask compose for the project name; do NOT derive it from the directory.
# Measured 2026-10-03, `basename "$PWD"` disagrees with what compose computes
# in 4 of 5 cases -- compose lowercases and strips dots, spaces and a leading
# underscore (`OpenLibrary-13796-Allowlist` -> `openlibrary-13796-allowlist`,
# `ol.worktree.foo` -> `olworktreefoo`). It happens to agree for the all-
# lowercase hyphenated names our worktrees use, which is why the wrong form
# looks fine until someone names a directory differently. The failure is at
# least safe -- the wrong name matches no volume and `rm` errors rather than
# deleting something else -- but it will not do what you asked.
PROJECT=$(docker compose config --format json | jq -r .name)
docker compose stop solr
docker volume rm "${PROJECT}_solr-data"
docker compose up -d solr
docker compose run --rm home make reindex-solr

# Before removing ANY volume you did not create in this session, check nothing
# else mounts it. Enumerate rather than assume -- a sample cannot prove "none":
docker ps -a --format '{{.Names}}' | while read c; do
  docker inspect "$c" --format '{{range .Mounts}}{{.Name}}{{"\n"}}{{end}}' 2>/dev/null \
    | grep -qx "<volume>" && echo "$c"
done

# Index a single work
docker compose run --rm home python -m openlibrary.solr.update --config conf/openlibrary.yml /works/OL45883W

# Preview what a key would index (without sending to Solr)
docker compose run --rm home python -m openlibrary.solr.update --config conf/openlibrary.yml --update pprint /works/OL45883W

# Inspect a work document
curl "http://localhost:8983/solr/openlibrary/select?q=key:/works/OL45883W&rows=1&wt=json" | python3 -m json.tool

# Full-text search directly against Solr
curl "http://localhost:8983/solr/openlibrary/select?q=frankenstein&rows=3&wt=json" | python3 -m json.tool
```

---

## Subcomponents and Architecture

### solr-updater daemon

`scripts/solr_updater/solr_updater.py` — long-running daemon. Reads changelog offset from state file, polls Infobase `/log/{offset}`, calls `update_keys()`, persists new offset. The `docker/ol-solr-updater-start.sh` entrypoint starts both this daemon and `trending_updater.py` in parallel.

**OSP data**: `osp_totals.db` (Open Syllabus Project citation counts) is downloaded from IA on startup and stored at `/solr-updater-data/osp_totals.db`. Used by `WorkSolrBuilder` to populate `osp_count`.

### SearchScheme pattern

Each document type has a `SearchScheme` subclass in `openlibrary/plugins/worksearch/schemes/`:

| Property | What it governs |
|----------|----------------|
| `default_fetched_fields` | Solr `fl` param default |
| `facet_fields` | Which fields return facet counts |
| `facet_rewrites` | Maps UI filter values → Solr `fq` clauses |
| `field_name_map` | Aliases: `author` → `author_name`, `trending` → `trending_z_score`, etc. |
| `sorts` | Valid sort options |
| `transform_user_query()` | Rewrites the luqum parse tree (ISBN normalization, field aliasing) |
| `q_to_solr_params()` | Adds boosting, highlighting, edition subquery |

`WorkSearchScheme` handles `work.` and `edition.` field prefixes, allowing direct targeting of nested edition fields.

### Work Query: Field Boosts (qf / pf)

`q_to_solr_params()` uses the edismax parser (not `defType=edismax` — local params, to allow parent/child nested queries). The boost configuration as of 2026-06-27:

**`qf` (query fields)** — fields searched for un-prefixed terms:
```
alternative_title^40   author_name^40   series_name^5
chapter                series_position  author_alternative_name
subject                place            person  time
series_key             author_key       ia      oclc
lccn                   isbn             key     edition_key
publisher              contributor
# (text field implied — the base "bag of words" with no explicit boost)
```

**`pf` (phrase fields)** — extra score when query terms appear in close proximity:
```
alternative_title^50   author_name^50   series_name^5
```

**`pf2`** (2-word bigram proximity):
```
alternative_title^20   author_name^20   series_name^5   chapter^5
```

**`boost` (multiplicative function query)** — applied to all results:
```
sum(
  mul(20, log(sum(3, edition_count))),          # edition count signal (log-scaled, ×20)
  min(50, def(already_read_count, 0)),          # reading log "already read" (capped at 50)
  mul(35, log(div(sum(4, def(readinglog_count,0)), 4)))  # total reading log (log-scaled, ×35)
)
```

So relevance score = text match score × popularity boost. A book with no editions, zero reading log entries scores boost ≈ `mul(20, log(3)) + 0 + mul(35, log(1))` = `mul(20, 0.477) + 0 + 0` ≈ 9.5.

### Edition Subquery: Field Boosts

When an edition subquery is active (e.g., `edition.isbn:...`), the edition `bq` (boost query) promotes which edition appears first:
```
language:{user_lang}^40    # preferred language heavily boosted
ebook_access:public^10     # freely readable
ebook_access:borrowable^8  # borrowable
ebook_access:printdisabled^2
cover_i:*^2                # has a cover
```

User language is detected from `lang` param (converted from ISO → MARC 3-letter code); defaults to `eng`.

**Key insight:** Field boosts are hardcoded in `schemes/works.py::q_to_solr_params()`. There is no runtime configuration, feature flag, or admin UI to change them — changes require a code deploy.

### Edition block-join

Editions are nested Solr documents within their parent work. To access them:
- `fl=editions:[subquery]` — returns per-work edition data in a single query (used by `/search` page)
- `q=edition.isbn:1234567890` — `WorkSearchScheme` rewrites to a block-join subquery filter
- Direct Solr: `{!child of=type:work}isbn:1234567890`

**You cannot search editions directly.** `EditionSearchScheme.universe = frozenset(["type:work"])` — it still filters to works. No `/editions/search.json` endpoint exists.

### Trending fields

Written by `trending_updater.py` (parallel daemon):
- `trending_score_hourly_0` through `_23` — pageviews per hour (rolling 24h)
- `trending_score_daily_0` through `_6` — daily scores (rolling 7 days)
- `trending_z_score` — Z-score for trend detection
- `weekly_demand` — demand weight per edition, computed by Trending code for [[core-vitals]] CVS
- `weighted_usefulness` — demand × usefulness, used in CVS numerator
- `trending_score_weekly_sum` — summed to produce `total_demand` for CVS denominator

All are `indexed=false, stored=false` — not searchable or retrievable, used only in `sort` and `function` queries.

### `solr_next` flag

`get_solr_next()` in `utils.py` — boolean flag for schema migrations. New indexing code writes new fields only when `solr_next=True`, allowing a reindex to complete before the flag is flipped in production. Use when adding fields that require a full reindex before going live.

---

## Key Files

| File | Purpose |
|---|---|
| `conf/solr/conf/managed-schema.xml` | Field definitions, field types, copy-fields — the schema |
| `conf/solr/conf/solrconfig.xml` | Query handlers, cache config, update processors, commit settings |
| `conf/solr/conf/enumsConfig.xml` | `ebookAccess` enum definition |
| `conf/solr/conf/synonyms.txt` | Query-time synonyms (not index-time) |
| `conf/solr/haproxy.cfg` | Production load balancer config; source of truth for host topology |
| `openlibrary/solr/update.py` | `update_keys()` — dispatches to typed updaters |
| `openlibrary/solr/utils.py` | `SolrUpdateRequest`, `solr_update()`, `get_solr_next()` |
| `openlibrary/solr/data_provider.py` | Fetches OL DB data during indexing (docs, editions, ratings, reading log, IA metadata) |
| `openlibrary/solr/updater/work.py` | `WorkSolrBuilder` + `WorkSolrUpdater` (678 lines) |
| `openlibrary/solr/updater/edition.py` | `EditionSolrBuilder` + `EditionSolrUpdater`; orphaned edition handling |
| `openlibrary/solr/updater/author.py` | `AuthorSolrBuilder` + `AuthorSolrUpdater`; queries Solr during indexing |
| `openlibrary/solr/updater/list.py` | `ListSolrUpdater` |
| `openlibrary/plugins/worksearch/code.py` | Search query prep, facet handling, web.py route handlers (1251 lines) |
| `openlibrary/plugins/worksearch/subjects.py` | `/subjects/{key}` page + `SubjectPseudoKey` logic |
| `openlibrary/plugins/worksearch/schemes/works.py` | `WorkSearchScheme` — all fields, sorts, facets, query rewriting |
| `openlibrary/plugins/worksearch/schemes/authors.py` | `AuthorSearchScheme` |
| `openlibrary/plugins/worksearch/schemes/editions.py` | `EditionSearchScheme` |
| `openlibrary/fastapi/search.py` | FastAPI endpoint definitions: `/search.json`, `/search/carousels.json`, etc. |
| `scripts/solr_updater/solr_updater.py` | solr-updater daemon — tails Infobase changelog |
| `scripts/solr_updater/trending_updater.py` | Writes trending scores into Solr |
| `scripts/solr_builder/` | Full reindex pipeline (Jenkins + Docker) |
| `docker/ol-solr-updater-start.sh` | Entrypoint for `solr-updater` container; starts both daemons |

---

## Configuration

**Production cluster:**
- `ol-solr0.us.archive.org:8983` (weight 60), `ol-solr2.us.archive.org:8983` (weight 60) — active
- `ol-solr1.us.archive.org:8983` — staging, disabled in HAProxy
- HAProxy at port **8984**, `leastconn` balancing
- Core name: `openlibrary`; index size ~80 GB

**Env vars:**

| Var | Purpose |
|-----|---------|
| `OL_SOLR_BASE_URL` | Overrides config-file Solr URL (local dev) |
| `solr.autoSoftCommit.maxTime` | ms until changes visible in search (solrconfig fallback 3000, but **overridden to 60000 in prod**) |
| `solr.autoCommit.maxTime` | ms until durable flush (default 15000) |
| `ol.replication.role.leader` / `.follower` | ReplicationHandler mode for reindex |

**`solrconfig.xml` commit chain:**

| Setting | Default | Effect |
|---------|---------|--------|
| `autoSoftCommit.maxTime` | 60000ms (prod) | Changes become searchable every ~60s |
| `autoCommit.maxTime` | 15000ms | Durable disk flush every ~15s |
| `autoCommit.openSearcher` | `false` | Hard commit does NOT open a new searcher — durability and visibility are decoupled |

**`solrconfig.xml` caches:**

| Cache | Size | Notes |
|-------|------|-------|
| `filterCache` | 512 | `fq` clauses |
| `queryResultCache` | 512 | Ordered doc ID lists by query+sort |
| `documentCache` | 512 | Stored field sets; no autowarm |
| `perSegFilter` | 10 | Block-join cache for nested edition docs — intentionally small, possible bottleneck on edition-heavy queries |

`enableLazyFieldLoading=true` — loads only stored fields in `fl`, major perf gain when not requesting large text fields.

**Update processors:** `tolerant-chain` (`maxErrors=-1`) — a single bad document never fails the whole batch. `update.autoCreateFields=true` — schemaless ON; unknown fields get auto-typed. See Known Issues for the deployment risk this creates.

**Searcher warming**: on every new searcher open, Solr runs three warming queries (harry potter with all facets; author works page; availability-filtered search). `useColdSearcher=false` blocks all requests during warming.

---

## Testing

```bash
# Run Solr-related tests
docker compose run --rm home python -m pytest openlibrary/solr/ -xvs
docker compose run --rm home python -m pytest openlibrary/plugins/worksearch/ -xvs

# Integration test (requires running Solr)
docker compose run --rm home python -m pytest openlibrary/tests/integration/test_search.py -xvs
```

⚠️ Integration tests for Solr are sparse — see issue [#11651](https://github.com/internetarchive/openlibrary/issues/11651). Unit tests run without Solr; integration tests require the full stack.

---

## Performance

- **End-to-end indexing latency**: ~60–65 seconds in prod (solr-updater poll + 60s soft commit)
- **Index size**: ~80 GB production
- **Known bottleneck**: `perSegFilter` cache is intentionally small (size=10); edition-heavy queries (block-join) may hit cache misses on large result sets
- **IA availability join**: every search result currently requires a separate call to `archive.org/services/availability` — expensive N+1 join on a hot path. PR #12689 (near-realtime loan availability in Solr) would eliminate this
- **`title_suggest` copy-field**: 3.4 GB; noted as TODO: unused internally
- `author.py` updater queries Solr live during indexing — if Solr is slow, author indexing backs up

---

## Related Processes

- **solr-updater** — long-running daemon; see [[infrastructure]] for deployment and supervision
- **trending_updater** — parallel daemon writing trending scores; also managed by [[infrastructure]]
- **Full reindex** — Jenkins job using `scripts/solr_builder/`; production uses ReplicationHandler leader/follower (followers poll leader every 60s post-commit)
- **Imports** — newly created/updated editions from [[imports]] must propagate through the solr-updater to appear in search
- **Lending** — `ebook_access` enum values come from [[lending]] availability data embedded at index time
- **Tags** — `subject_facet`, `person_facet`, `place_facet`, `time_facet` populated from Work subjects; [[tags]] covers the subject/tag relationship

---

## What's Broken / Fragile / Unimplemented

### Confirmed bugs

~~**Python 2 syntax in `work.py`** (line 256)~~ — **retracted 2026-08-10, this was never a bug and the location was wrong.** The `except TypeError, ValueError:` line is in `openlibrary/plugins/openlibrary/api.py`, not `work.py`, and it compiles cleanly: [PEP 758](https://peps.python.org/pep-0758/) (Python 3.14) permits unparenthesized multiple exception types, and the repo runs 3.14. Verified with `python3 -m py_compile`. The same pattern in `scripts/monitoring/monitor.py` is likewise fine. If a `conftest.py` workaround exists for this, it is now dead weight.

**`SearchResponse.from_solr_result()`'s `num_found=None` error sentinel wasn't checked everywhere** ([#13192](https://github.com/internetarchive/openlibrary/issues/13192), fixed by [#13193](https://github.com/internetarchive/openlibrary/pull/13193)) — see "`num_found=None` is a Solr-error sentinel" under Common Confusion below for the pattern. `subjects.py`'s subject-page controller now guards on `work_count is None`; other callers of `run_solr_query_async`/`SearchResponse` that render Solr-derived counts/values without checking `.error` (or `num_found is None`) could hit the same class of crash — not yet audited: `openlibrary/core/bookshelves.py`, `openlibrary/plugins/openlibrary/partials.py`, `openlibrary/plugins/openlibrary/lists.py`, `openlibrary/fastapi/search.py`.

### Known limitations

- **No editions search endpoint** — `EditionSearchScheme` is described as "kind of mostly a stub"; no `/editions/search.json` exists. Editions are only accessible via block-join from work queries.

- **schemaless mode ON** (`update.autoCreateFields=true`) — if app code deploys before a schema update, Solr auto-types new fields. A string field auto-created as `text_general` breaks exact-match filter queries. Any PR adding new Solr fields needs a `Needs: Special Deploy` label and schema-first deployment.

- **English stemming on non-English text** — `text_en_splitting` applies Porter stemming to author/title text, causing false positives and misses for non-English records. [#7551](https://github.com/internetarchive/openlibrary/issues/7551)
- **Stopword filtering is disabled entirely** — both `stop` filters in `text_en_splitting` are commented out; re-enabling them naively reproduces a position-mismatch bug on consecutive stopwords. See [[search-text-analysis]] for the full chain, the reproduction, and a candidate fix. [#5393](https://github.com/internetarchive/openlibrary/issues/5393)

- **`title_suggest` copy-field** — 3.4 GB; noted as unused internally. [TODO] Remove.

- **Legacy IA fields pending removal**: `lending_edition_s`, `lending_identifier_s`, `printdisabled_s` are deprecated but still in the schema. [#11586](https://github.com/internetarchive/openlibrary/issues/11586)

- **No integration tests for Solr** — [#11651](https://github.com/internetarchive/openlibrary/issues/11651) P2

### Active PRs with deployment ordering requirements

| PR | Status | What | Deploy requirement |
|----|--------|------|--------------------|
| [#12987](https://github.com/internetarchive/openlibrary/pull/12987) | ⚠️ **Contradiction** | `/search/carousels.json` — `solr/priorities.md` says open/CI passing; `opds/index.md` says closed without merging. Verify current status on GitHub. | None |
| [#12689](https://github.com/internetarchive/openlibrary/pull/12689) | P2, mergeable | Near-realtime loan availability (`ebook_availability`, `ebook_becomes_available`, `loan_uid`) | Schema first; `Needs: Special Deploy` **missing** — gap |
| [#12916](https://github.com/internetarchive/openlibrary/pull/12916) | Open | Cover dimensions (`cover_width`, `cover_height`) in Solr | `Needs: Special Deploy` ✅ |

**PR #12987 is highest priority** — actively causing 429s in production on OPDS/BookServer carousel loads.

---

## Common Confusion

- **`ebook_access` vs `ebook_availability`**: `ebook_access` (enum: protected/printdisabled/borrowable/public) is the static "highest tier for this work" — updated on work reindex. `ebook_availability` (string: available/unavailable, from PR #12689) is the realtime "is this copy checked out right now?" Both are needed; neither replaces the other.

- **`search.json` has no facets** — facets are disabled in `search.json` for performance. They only appear on the HTML `/search` page. If you need facet counts, use the HTML endpoint or add `facet=true` in a direct Solr query.

- **`num_found=None` is a Solr-error sentinel, and it can carry a `None` `.error` too**: `SearchResponse.from_solr_result()` in `worksearch/code.py` sets `num_found=None` + `error=<msg>` whenever the *response* Solr returns contains an `"error"` key — but a total connection failure or timeout never reaches that branch with a message at all. `execute_solr_query_async()` catches `httpx.HTTPError` (this includes `httpx.TimeoutException` and `httpx.ConnectError`) and returns `None` for the raw response *before* any `"error"` key can exist, so `from_solr_result(None, ...)` sets `error=None` alongside `num_found=None`. Downstream code that only checks `.error` truthiness (rather than `num_found is None` / `work_count is None`) will silently miss the "Solr is unreachable or timed out" case — which is exactly the intermittent "first load after a while" trigger reported in [#13192](https://github.com/internetarchive/openlibrary/issues/13192). Always key off the `None`-ness of the count/value itself, not the presence of an error message.

- **`AVAILABILITY_TO_PARAMS` and `constants.js` must stay in sync** — both encode the mapping from UI filter names to Solr `fq` clauses. Editing one without the other causes availability filters to silently mismatch between front-end and back-end.

- **solr-updater offset file loss** — if `/solr-updater-data/solr_state` is lost or corrupted, the updater must restart from scratch or a manually-specified known offset. This has happened during container restarts where the volume was not persisted.

- **Schema changes require a full reindex** — adding a new field to `managed-schema.xml` doesn't backfill existing documents. The new field only appears on newly indexed documents until a full reindex runs.

- **A query that works on `/search` may return nothing from `search.json`** — the HTML search page applies additional query rewriting in `_prepare_solr_query_params()` in `worksearch/code.py`. When debugging a missing result, check that function first.

- **Subjects are not Solr documents** — they are derived at query time from `subject_facet` field values. The `/subjects/{key}` page is built from a facet query, not a document lookup.

---

## Debugging: Book Not Appearing in Search

1. **Is Solr running?**
   ```bash
   curl "http://localhost:8983/solr/openlibrary/select?q=*:*&rows=0"
   ```
   If `numFound=0`, the index is empty → run `make reindex-solr`.

2. **Is the document in Solr at all?**
   ```bash
   curl "http://localhost:8983/solr/openlibrary/select?q=key:/works/OL45883W&rows=1&wt=json"
   ```

3. **What does the updater think it would index?**
   ```bash
   docker compose run --rm home python -m openlibrary.solr.update --config conf/openlibrary.yml --update pprint /works/OL45883W
   ```

4. **Is there a schema mismatch?**
   If solr-updater logs "unknown field" errors → schema changed but Solr core still has old schema → reset volume and reindex.

5. **Is the solr-updater daemon running?**
   Check `docker compose logs solr-updater`. If it crashed or missed events, trigger a manual update for the specific key (step 3 above without `--update pprint`).

6. **Is the query rewriting hiding it?**
   Check `_prepare_solr_query_params()` in `worksearch/code.py` for HTML search vs `search.json`.

---

## Dependencies

**Depends on:**
- [[core-operations]] — Infobase changelog (the event stream solr-updater reads); plugin routing for worksearch
- [[lending]] — `ebook_access` enum values reflect availability data from the lending system
- [[imports]] — new editions created by imports must be indexed by solr-updater to appear in search
- [[tags]] — Work subjects → Solr `subject_facet`, `person_facet`, etc.
- [[infrastructure]] — solr-updater and trending_updater are supervised processes; production Solr cluster is IA-managed

**Depended on by:**
- All search pages (HTML and JSON API)
- OPDS feeds (see [[public-apis]])
- Subject pages (`/subjects/{key}`)
- Autocomplete
- [[core-vitals]] — CVS, CLS, Demand, and Usefulness scores are all stored as Solr fields and queried via Solr; `usefulness` and `usefulness_pct` recomputed on Edition update

---

## Provisioning / Services

**Production:** Three-node cluster (`ol-solr0`, `ol-solr1`, `ol-solr2`) managed via HAProxy at port 8984. Config in `conf/solr/haproxy.cfg`. Health check: `GET /solr/openlibrary/admin/ping`.

**Replication:** `ReplicationHandler` leader/follower — leader does the reindex; followers poll every 60s after commits. HAProxy removes a node from rotation if it fails the health check.

**Full production reindex process**: see [olsystem wiki: Solr Re-Indexing](https://github.com/internetarchive/olsystem/wiki/Solr-Re%E2%80%90Indexing) (requires IA staff access).

**Local dev:** Single Solr container at `http://localhost:8983`. Full stack: `docker compose up -d`.

---

*Sources: `raw/openlibrary-docs-ai/solr/index.md`, `raw/openlibrary-docs-ai/solr/priorities.md` · See [[README]] · [[METHODOLOGY]]*
