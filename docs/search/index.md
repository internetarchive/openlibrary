# Solr

Apache Solr 10 is Open Library's search index. It powers all search pages, the Public Search API, subject pages, and OPDS feeds. The index stores denormalized Work documents (with embedded edition data) and separate Author, Subject, and List documents.

## Production Architecture

Three Solr nodes, load-balanced via HAProxy:

| Host | Role | Weight |
|------|------|--------|
| `ol-solr0.us.archive.org:8983` | Primary production | 60 |
| `ol-solr2.us.archive.org:8983` | Secondary production | 60 |
| `ol-solr1.us.archive.org:8983` | Staging (disabled in haproxy.cfg) | — |

- HAProxy listens at port **8984**, balances with `leastconn`
- Health check: `GET /solr/openlibrary/admin/ping`
- Index size: ~80 GB
- Core name: `openlibrary`
- Config: `conf/solr/haproxy.cfg`

Local dev runs a single Solr container at `http://localhost:8983`. The `OL_SOLR_BASE_URL` env var overrides the config-file value.

## Key Files

| File | What it does |
|------|-------------|
| `conf/solr/conf/managed-schema.xml` | Field definitions, field types, copy-fields. The schema. |
| `conf/solr/conf/solrconfig.xml` | Query handlers, cache config, update processors. |
| `conf/solr/conf/enumsConfig.xml` | `ebookAccess` enum definition. |
| `conf/solr/conf/synonyms.txt` | Query-time synonyms applied at search (not index) time. |
| `conf/solr/haproxy.cfg` | Production load balancer config — source of truth for host topology. |
| `openlibrary/solr/update.py` | Main entry point: `update_keys()` dispatches to typed updaters. |
| `openlibrary/solr/utils.py` | `SolrUpdateRequest`, `solr_update()`, `get_solr_base_url()`, `solr_next` flag. |
| `openlibrary/solr/data_provider.py` | Fetches OL DB data during indexing: docs, editions, ratings, reading log, IA metadata, trending. |
| `openlibrary/solr/updater/abstract.py` | `AbstractSolrUpdater` and `AbstractSolrBuilder` base classes. |
| `openlibrary/solr/updater/work.py` | `WorkSolrBuilder` + `WorkSolrUpdater` — the most complex updater (678 lines). |
| `openlibrary/solr/updater/edition.py` | `EditionSolrBuilder` + `EditionSolrUpdater` — orphaned edition handling, nested doc construction. |
| `openlibrary/solr/updater/author.py` | `AuthorSolrBuilder` + `AuthorSolrUpdater` — uniquely queries Solr to aggregate work stats. |
| `openlibrary/solr/updater/list.py` | `ListSolrUpdater`. |
| `openlibrary/plugins/worksearch/code.py` | Search query preparation, facet handling, web.py route handlers (1251 lines). |
| `openlibrary/plugins/worksearch/subjects.py` | `/subjects/{key}` page data and `SubjectPseudoKey` logic. |
| `openlibrary/plugins/worksearch/schemes/works.py` | `WorkSearchScheme` — all fields, sorts, facets, query rewriting. |
| `openlibrary/plugins/worksearch/schemes/authors.py` | `AuthorSearchScheme`. |
| `openlibrary/plugins/worksearch/schemes/editions.py` | `EditionSearchScheme` — for the edition block-join subquery. |
| `openlibrary/fastapi/search.py` | FastAPI endpoint definitions: `/search.json`, `/search/carousels.json`, etc. |
| `scripts/solr_updater/solr_updater.py` | The long-running daemon that tails the Infobase changelog and calls `update_keys()`. |
| `scripts/solr_updater/trending_updater.py` | Separate daemon that writes trending scores into Solr. |
| `scripts/solr_builder/` | Full reindex pipeline (Jenkins + Docker). |
| `docker/ol-solr-updater-start.sh` | Entrypoint for the `solr-updater` container. Starts both daemons. |

## How It Works

### Document types

Solr stores four document types in the single `openlibrary` core, distinguished by the `type` field:

| Type | Key format | Indexed by |
|------|-----------|-----------|
| `work` | `/works/OL123W` | `WorkSolrUpdater` |
| `work` (orphaned edition) | `/works/OL123M` (fake key) | `WorkSolrUpdater` via fake-work path |
| `author` | `/authors/OL123A` | `AuthorSolrUpdater` |
| `list` | `/lists/OL123L` | `ListSolrUpdater` |

Subjects are **not stored as documents**. They are derived at query time from work `subject_facet` values by the `SubjectSearchScheme`.

### The solr-updater daemon

`scripts/solr_updater/solr_updater.py` is a long-running daemon that keeps the index current:

1. On startup, reads a **state file** (`/solr-updater-data/solr_state`) containing the last consumed changelog offset, formatted as `YYYY-MM-DD:N` (e.g. `2023-02-11:4217`).
2. Polls the **Infobase changelog** at `http://{infobase_host}/openlibrary.org/log/{offset}?limit=100`, which returns up to 100 log records and the new offset.
3. Extracts the affected OL keys from each log record and passes them to `update_keys()`.
4. Persists the new offset to the state file after each batch.
5. On empty response, waits and retries.

A second daemon, `trending_updater.py`, runs in parallel and writes trending scores from the OL DB into Solr periodically.

The `docker/ol-solr-updater-start.sh` entrypoint starts both. The OSP (Open Syllabus Project) dump is downloaded on startup from IA to `/solr-updater-data/osp_totals.db`.

### Indexing flow

```
OL database (postgres/infobase)
    │
    │  solr-updater daemon
    │  polls /log/{offset} → extract changed keys
    ▼
openlibrary/solr/update.py → update_keys()
    │  runs [EditionSolrUpdater, WorkSolrUpdater, AuthorSolrUpdater, ListSolrUpdater]
    │  order matters (Edition before Work; Work embeds edition data)
    │
    │  per key: fetch document from data_provider
    │           run updater.update_key(doc) → SolrUpdateRequest
    │           accumulate adds/deletes
    ▼
openlibrary/solr/utils.py → solr_update()
    │  httpx POST to Solr /update?commit=true with JSON body
    ▼
Solr (ol-solr0 / ol-solr2 via HAProxy port 8984)
```

Key behaviors in `update_keys()`:
- **Redirect handling**: if a key resolves to `/type/redirect`, the original key is deleted and the redirect target is indexed instead.
- **Deleted records**: `/type/delete` → queue for deletion.
- **Fake work keys**: a key matching `/works/OL123M` is a fake work created for an orphaned edition; the real book key `/books/OL123M` is fetched instead.
- **Cascading**: an `EditionSolrUpdater.update_key()` call returns the parent work's key in `new_keys`, so the work also gets re-indexed.

### WorkSolrBuilder (work.py)

`WorkSolrBuilder.build()` assembles the full work document by:
1. Running `AbstractSolrBuilder.build()` — introspects all non-`_` properties, skips `None` and empty iterables, converts `EbookAccess` to string.
2. `build_identifiers()` — merges `id_*` identifiers from all editions (e.g. `id_project_gutenberg`, `id_librivox`).
3. `build_subjects()` — maps `work.subjects` → `subject`, `subject_facet`, `subject_key`; same for `subject_people`, `subject_places`, `subject_times`.
4. `build_legacy_ia_fields()` — collects `ia_box_id` from editions.
5. `build_ratings()` — calls `data_provider.get_work_ratings()` → `WorkRatingsSummary`.
6. `build_reading_log()` — calls `data_provider.get_work_reading_log()`.
7. Merges `self._trending_data` (hourly/daily score fields).

**Key work fields computed:**

| Field | Source | Notes |
|-------|--------|-------|
| `seed` | work key + edition keys + author keys + subject keys | Used for list membership queries |
| `title_sort` | `sort_title(title, subtitle)` | Articles moved to end: "The Great Gatsby" → "Great Gatsby, The" |
| `alternative_title` | work + all editions + translation_of | Union of all titles |
| `edition_count` | `len(editions)` | |
| `first_publish_year` | `min(publish_year for all editions)` | |
| `number_of_pages_median` | `ceil(median(pages for all editions))` | |
| `ebook_access` | `max(e.ebook_access for all editions)` | Best access level across all editions |
| `ia` | IA editions, sorted: public first, non-goog before goog | |
| `lending_edition_s` | first borrowable/public IA edition OLID | Deprecated; will be removed |
| `lending_identifier_s` | first borrowable/public IA identifier | Deprecated; will be removed |
| `printdisabled_s` | semicolon-joined OLIDs of printdisabled editions | Deprecated; will be removed |
| `author_facet` | `["{OL key} {author name}", ...]` | Format required by `read_author_facet()` |
| `osp_count` | Open Syllabus Project lookup by work key | From `osp_totals.db` |

### EditionSolrBuilder (edition.py)

Editions are indexed as **nested Solr documents** within their parent work via block-join. `EditionSolrBuilder.build()` produces a flat dict (no None/empty values) with:

- `key`, `work_key` (OLIDs without `/books/` prefix), `type: "edition"`
- `title`, `subtitle`, `alternative_title` (all titles + `work_titles` + `other_titles`), `chapter` (table of contents entries — format: `"{OLID} | {label} | {title} | {pagenum}"`)
- `cover_i` (first non-(-1) cover ID), `language` (3-letter codes from `/languages/` keys)
- `author_name`, `author_key`, `author_alternative_name`, `author_facet` — **duplicated from the parent work**
- `publisher` (sine nomine → "Sine nomine"), `format` (physical_format), `publish_date`, `publish_year`
- `isbn` — ISBN-10 and ISBN-13, with complementary conversions (`opposite_isbn()`); strips `_` and spaces
- `lccn`, `oclc`
- `ia`, `ia_collection` (excluding `fav-*`), `ia_box_id`
- Dynamic `id_*` fields from `edition.identifiers` (key sanitized: `.,()/:#` replaced with `_`)
- `ebook_access` (from `EbookAccess` enum), `ebook_provider`, `has_fulltext`, `public_scan_b`

**Orphaned edition handling**: `EditionSolrUpdater.update_key()` checks if the edition has a `works` field. If not, it returns the fake work key `/works/OL{id}M` in `new_keys`, and `WorkSolrUpdater` later picks that up and indexes the edition as a standalone work document.

### AuthorSolrBuilder (author.py)

`AuthorSolrUpdater` is unique: it **queries Solr** during indexing to aggregate statistics from all of the author's works. It uses the Solr JSON Facet API (`POST /query`) with:
- `q: "author_key:{OL author ID}"`, `fq: "type:work"`
- Facet sums for `ratings_count_1`-`5`, `readinglog_count`, `want_to_read_count`, etc.
- Facet terms for `subject_facet`, `time_facet`, `person_facet`, `place_facet`

The result feeds `AuthorSolrBuilder` to compute:
- `top_work` — title of the author's most-edition work
- `work_count` — total works in Solr
- `top_subjects` — up to 10 most frequent subjects across all works
- Aggregated reading log + ratings counts

### Edition block-join

Work documents in Solr embed a nested `editions` block via Solr's block-join feature. The `/search` page uses `editions:[subquery]` in `fl` to return per-work edition data in a single Solr query. `EditionSearchScheme` governs what edition fields are returned in that subquery. The `_root_` and `_nest_path_` fields in the schema support this.

### Availability (ebook_access)

The `ebook_access` field is a custom Solr enum type (`ebookAccessLevel`, defined in `enumsConfig.xml`). Values in ascending order: `protected` → `printdisabled` → `borrowable` → `public`.

The enum is **sortable** — Solr can range-query it. This is how availability filters work:

| UI filter | Solr filter query |
|-----------|-------------------|
| "Readable online" | `ebook_access:[borrowable TO *]` (via `has_fulltext=true`) |
| "Borrow online" | `ebook_access:[borrowable TO borrowable]` |
| "Free to read" | `ebook_access:public` (via `public_scan=true`) |

`AVAILABILITY_TO_PARAMS` in `worksearch/code.py` **must stay in sync** with the JS `constants.js` file — both encode the same mapping from UI filter names to Solr `fq` clauses.

### Near-realtime loan availability (`ebook_unavailable`)

Written to **edition** documents by `scripts/solr_updater/loan_availability_updater.py`, a daemon that **polls** the archive.org search index for the set of books that are checked out right now and reconciles Solr to it. See that module's docstring for the design; this section covers the schema side.

> An earlier revision followed IA's loan-changes feed with a two-loop
> follower/repairer. That was abandoned — the changes API cannot report loan
> **expiry**, so the feed can never free a book — and this doc described it for
> longer than the code did. If you find feed or two-loop language anywhere in
> this section, it is stale.

Two fields, both numeric, both `docValues=true stored=false indexed=false`:

| Field | Meaning |
|---|---|
| `ebook_unavailable` | `1` = no borrowing capacity right now. Absent or `0` = available. |
| `ebook_unavailable_ts` | Epoch seconds when `ebook_unavailable` was last set to `1`. Read by nothing here; it ships so the feed/poll hybrid is a code-only change. |

**These record exceptions, not state.** An `ebook_access:borrowable` edition is assumed AVAILABLE unless `ebook_unavailable=1` says otherwise, so the common case writes nothing. Consumers must query:

```
ebook_access:borrowable AND -ebook_unavailable:1
```

Treating a missing value as "unknown" is wrong — absent means available.

**Why the field flags are what they are.** `stored=false indexed=false` is *required* for `update.partial.requireInPlace` to work, and in-place updates are what keep each poll's writes cheap — a normal atomic update to a nested edition reindexes the parent work and every edition under it, which at poll cadence would be ruinous. The write set is small (the delta between polls, measured at 0–2 editions against ~766 marked); the saving is in not rewriting a whole work block per edition touched. Solr additionally requires the field be **numeric**: a `pdate` field returns `HTTP 400 — Can not satisfy 'update.partial.requireInPlace'`, verified against both `last_modified` and a dynamic `*_dt`. Both of those are `indexed=true stored=true`, so that test does not isolate the type from the flags — what it establishes is that **`plong`/`pint` with `docValues=true stored=false indexed=false` demonstrably works and `pdate` as configured here does not.** Use epoch `plong` for timestamps, not `pdate`.

**Filtering on them is cheap — measured, not assumed.** With `indexed=false` these are a docValues scan rather than an index lookup, which sounds expensive and is not: sparse docValues iterate only the documents that *have* the field.

Measured on Solr 10.0.0 with this configset, single node, **2,900,000 borrowable editions** nested under works (matching production's `ebook_access:borrowable` count):

| query | numFound | QTime cold | QTime warm |
|---|---|---|---|
| `type:edition AND subject_key:X AND ebook_access:borrowable` | 58,000 | 3–12 ms | 0 ms |
| the same **plus** `-ebook_unavailable:1` | 58,000 | 3–7 ms | 0 ms |
| `type:edition AND -ebook_unavailable:1` (no pre-filter) | 2,871,014 | 20 ms | 0 ms |
| `type:edition AND ebook_unavailable:1` | 29,000 | 0 ms | 0 ms |

Re-run with **290,000** marked (10× more) and the negation still added nothing measurable, so the cost does not scale with the marked set at these magnitudes. Cold figures were taken with the filterCache defeated by a unique clause; in practice `-ebook_unavailable:1` is *identical across every page using it*, so one cached filter serves them all — but production soft-commits every 60s and drops that cache, so treat the cold column as the steady state. It is single-digit milliseconds.

Caveats: one node, one shard, no replicas, no concurrent query load, and synthetic documents carrying few fields. Filter evaluation does not read stored fields so this should transfer, but it is not production.

So an edition-level filter such as `genre_key:X AND ebook_access:borrowable AND -ebook_unavailable:1` is viable **without changing the field design**. `indexed=true` is not required and should be avoided: it forfeits in-place updates, and a non-in-place atomic update to a nested child reindexes the parent work and all its editions.

The fields stay absent from `EditionSearchScheme.all_fields`. That governs whether a bare `field:value` typed by an end user is treated as a Solr field — a separate question from whether internal code may build an `fq` on them, which it may.

**A field cannot be cleared in place.** `requireInPlace` rejects `"set": null` unconditionally — a value can be set or incremented, never removed. "Available" is therefore written as `0` rather than by deleting the field, and `ebook_unavailable_ts` keeps its last value through a clear, which is why it is meaningful only while `ebook_unavailable` is `1`.

That same constraint is why `ebook_becomes_available` ("available in N days") was dropped: it went stale the moment a loan was renewed, and could not be cleared when it did. The distinction worth keeping is that a stale *mark time* is inert — nothing reads it unless the book is marked, and a re-mark overwrites it — whereas a stale *expiry time* was shown to users. `loan_uid`, the changes-feed cursor, was dropped with the feed.

**There is no cold start to operate.** Each poll is a complete statement of what should be marked, so the first poll after any start performs the whole job and a reindex that wipes the field self-heals on the next cycle. There is no cursor, no state file and no `--reset`. What follows describes the single step a poll takes:

1. **Seed.** The archive.org search index is asked for books that are lendable but currently neither borrowable nor browsable — `lending___is_lendable:true AND lending___available_to_borrow:false AND lending___available_to_browse:false`. That is the answer set directly, measured at ~600 books in 2026-10. It replaced a replay of `LOAN_MAX_AGE_DAYS` of loan events, which produced only *candidates* and cost one availability request per hundred of them — the daemon's last unbounded path.
2. **Reconcile.** Solr's currently-marked set is read back, and one bulk in-place update marks what the index newly calls unavailable and clears what it no longer does. That is the whole cycle; there is no second mechanism.

**The seed is complete or the daemon refuses to start.** The set grows with traffic, so a fixed `rows` would silently cap it — and a short seed *under*-marks: the omitted books look returned, so the reconcile clears them and they are published as borrowable while they are out. The next poll would re-mark them, but only if the next seed is complete — a persistently short read is persistently wrong, which is why this refuses rather than accepting what arrived. So the read pages to completeness (`CHECKED_OUT_INDEX_PAGE_ROWS` at a time) and compares what it assembled against the `numFound` the index reported. Any shortfall raises `CheckedOutSeedIncomplete` and the supervisor retries. Measured 2026-10, `advancedsearch.php` answers while `start + rows <= 10000` and returns HTTP 200 with no `response` envelope past that, so `CHECKED_OUT_INDEX_MAX_ROWS` is the endpoint's own ceiling rather than a policy choice.

**A set larger than that ceiling is the one failure no retry fixes**, and it is the trigger for the authenticated Scrape API — which pages further but needs credentials, and which unauthenticated was measured silently ignoring its `q`, returning a per-client cached total for any query including deliberate nonsense. The error names Scrape for that reason. Swapping endpoints means changing `get_checked_out_candidates_async` and nothing else.

Note one deliberate strictness: if books are borrowed *while* the seed pages, `numFound` climbs and the final count falls short, so this raises on a set that was never actually missed. That is a spurious refusal, and it happens precisely when under-marking would matter most — a retry is the right answer rather than accepting whatever arrived. At today's ~600 the seed is a single page and the loop never runs twice, so it cannot fire now.

**When multi-page seeds become routine, do not relax this with a flat tolerance.** A shortfall has two causes with one symptom. Either `numFound` grew because books were borrowed mid-paging — benign, and the overlap replay already catches those, since each has a recent acquiring event — or a page under-delivered against the rows it requested, which is a real retrieval miss of books that were unavailable the whole time and therefore have *no* recent event for the overlap to find. A threshold such as "assembled ≥ 90% of `numFound`" cannot tell the two apart, so it would mask the second while buying relief only for the first: strictly worse than refusing. The correct fix tolerates pure growth and raises when a page returns fewer rows than it asked for while `start + len(docs) < numFound` says more were available. Today's code cannot make that distinction, because it reads a short page as the end of the result set — which is a limit on the *tolerant* version, not a live hole: an intermediate page that under-delivers ends the loop early, the assembled count falls below `numFound`, and the strict check turns it into a refusal rather than a silent miss.

**The index is never written to Solr as-is.** It is a lagged view, and a sibling lending field (`loans__status__status`) was measured disagreeing with live availability in *both* directions. So the seed is a candidate set: identifiers go through the availability service, `MIN_RECONCILE_COVERAGE` still applies, and a degraded service raises rather than half-applying. Sampling in 2026-10 found the two fields used here agreeing with live availability 80/80 across two independent samples, but that is a spot check, not a guarantee — hence ground truth still decides.

**The clear direction is the dangerous one, and it is guarded twice.** Marking wrongly hides a book until the next poll — recoverable. Clearing wrongly publishes a checked-out book as borrowable, and nothing revisits it. So a poll that would clear more than `CLEAR_BREAKER_FRACTION` of the marked set (or more than an absolute floor) does not proceed on the index's word: the whole clear set goes to the bulk availability service and each edition is decided on its own answer. Available → cleared. Still out, or no answer → keeps its mark. Zero confirmed → the index is what is wrong, and every clear is held.

That is deliberately not sampled. A sample that comes back still-unavailable disproves a mass-free; one that comes back available only *supports* it, and promoting that to a universal licenses the unrecoverable action. Checking the full set is affordable because it is rare and bounded — at most the marked set, ~766, about 8 batched requests.

> **The index's own lag has never been measured.** It bounds how stale a poll can be, and it is the number the follow-on hybrid's margin must be sized from. To take it: pull acquiring events from the loan-changes feed with timestamps and find the newest one *absent* from the index's checked-out set. That needs feed credentials and the production box. A partial measurement from outside, 2026-10-06: of 60 identifiers the index called unavailable, 3 were already free in live ground truth, and a watch on those three saw one leave the index's set after 15 minutes while two had not after an hour and forty. That is a staleness rate and a tail, not a distribution.

**Reindex wipes these fields.** They live on nested edition children, and reindexing a work rewrites its children from the indexer's own view, which has no knowledge of them. This is not limited to a full reindex — the main `solr_updater` reindexes a work on any change to it or its editions, continuously, from the infobase changelog.

The poll **removes** that problem rather than handling it. Each cycle restates the whole answer, so a wiped field is simply re-marked on the next poll and the exposure is one cycle, with nothing to run by hand. The design this replaced needed an operator to notice and re-run a cold start, because the wipe also destroyed the list its re-check worked from.

### Trending fields

Trending data (written by `trending_updater.py`) uses dedicated fields:
- `trending_score_hourly_0` through `trending_score_hourly_23` — pageviews per hour of day (rolling 24h)
- `trending_score_daily_0` through `trending_score_daily_6` — daily scores (rolling 7 days)
- `trending_score_hourly_sum` — sum of all 24 hourly slots
- `trending_z_score` — Z-score for trend detection

All trending fields are `indexed=false, stored=false` in the schema — they are **not searchable or retrievable**. They are used only in `sort` and `function` queries (e.g. `sort=def(trending_z_score, 0) desc`).

### `solr_next` flag

`get_solr_next()` in `utils.py` returns a boolean. Used during schema migrations: new code can conditionally write new fields only when the flag is set, allowing a reindex to complete before the flag is flipped in production.

## Schema Field Types

Key field types in `managed-schema.xml`:

| Type | Usage | Analyzer |
|------|-------|---------|
| `string` | Exact-match fields: facets, keys, IDs, enums | None (verbatim) |
| `text_en_splitting` | English full-text: title, subject, publisher | Tokenize → English stop words → Porter stemming |
| `text_general` | Multi-language text: contributor, lccn | Tokenize → standard stop words → lowercase; query-time synonyms |
| `text_international` | Author names | Tokenize → ICU folding (accent-insensitive) |
| `text_international_sort` | Sort fields for author names, title | ICU collation (no analyzer allowed) |
| `ebookAccessLevel` | `ebook_access` | Custom Solr enum — `enumsConfig.xml` |
| `pint`, `pfloat`, `plong` | Numeric: edition_count, ratings, years | KD-tree point fields; docValues enabled by default |
| `random` | `random_*` dynamic fields | RandomSortField — time-seeded random sorts |

Notable dynamic field patterns:
- `id_*` → `string` multiValued=true — for custom identifiers (e.g. `id_project_gutenberg`)
- `random_*` → random sort field — used for `sort=random.hourly` (e.g. `random_{YYYYMMDTHH} asc`)
- `*_s` → string, `*_i` → pint, `*_b` → boolean, `*_f` → pfloat

**Copy-fields**: Solr copies field values at index time (not stored, just indexed):
- `title` → `title_suggest` (3.4 GB; noted as TODO: unused internally)
- `publisher` → `publisher_facet`; `subject/place/person/time` → their `*_facet` equivalents
- Most text fields → `text` (the catch-all field)
- `name` → `name_sort` (for author sort)

## Search Endpoints

All `*.json` endpoints are defined in `openlibrary/fastapi/search.py`, served by FastAPI (the primary server on port 8080 in local dev; port 18080 behind the site proxy in production/staging).

| Endpoint | Handler | Purpose |
|----------|---------|---------|
| `GET /search.json` | `search_json()` | Primary work/book search API. Facets disabled (speed). Public docs: `https://openlibrary.org/dev/docs/api/search` (also returned in every response as `documentation_url`). |
| `GET /search/subjects.json` | `search_subjects_json()` | Subject search. Returns `type` and `count` compat fields. |
| `GET /search/authors.json` | `search_authors_json()` | Author search. Strips `/authors/` prefix from key. |
| `GET /search/lists.json` | `search_lists_json()` | List search. `?api=next` for new response shape. |
| `GET /search/inside.json` | `search_inside_json()` | Fulltext (inside-book) search. |
| `POST /search/carousels.json` | `search_carousels_json()` | Up to 20 queries in one call. Used by OPDS. Max 20. (PR #12987) |
| `GET /search` (HTML) | `search` in `worksearch/code.py` | Search results page — facets, ISBN redirect, spellcheck. |
| `GET /subjects/{key}` | `subjects` in `worksearch/subjects.py` | Subject page: works list + related subjects. |
| `GET /search/subjects` | `subject_search` in `worksearch/code.py` | Subject autocomplete (HTML). |
| `GET /search/authors` | `author_search` in `worksearch/code.py` | Author search (HTML). |
| `GET /advancedsearch` | `advancedsearch` in `worksearch/code.py` | Advanced search form (HTML). |

### `search.json` parameters

| Param | Notes |
|-------|-------|
| `q` | Main query. ISBN queries auto-detected and normalized by `WorkSearchScheme`. |
| `title`, `author`, `subject`, `place`, `person`, `time`, `publisher`, `isbn` | Field-specific filters. Author accepts `OL123A` key or name string. |
| `has_fulltext` | `true`/`false` → `ebook_access:[borrowable TO *]` |
| `public_scan` | `true`/`false` → `ebook_access:public` |
| `language` | 3-letter ISO codes. Multiple values OR'd. |
| `author_key` | OL author key (e.g. `OL1394244A`). |
| `subject_facet`, `person_facet`, `place_facet`, `time_facet`, `publisher_facet` | Facet filters. |
| `first_publish_year` | Year filter. |
| `sort` | See sort options below. |
| `fields` | Comma-separated. Defaults to `WorkSearchScheme.default_fetched_fields`. |
| `page`, `limit`, `offset` | Pagination. |

### Sort options

Valid values for `sort=` parameter (from `WorkSearchScheme.sorts`):

| Value | Solr sort |
|-------|-----------|
| `editions` | `edition_count desc` |
| `old` | `def(first_publish_year, 9999) asc` |
| `new` | `first_publish_year desc` |
| `title` | `title_sort asc` |
| `rating` / `rating asc` / `rating desc` | `ratings_sortable` |
| `readinglog` | `readinglog_count desc` |
| `want_to_read`, `currently_reading`, `already_read`, `stopped_reading` | Respective count fields desc |
| `trending` / `trending asc/desc` | `def(trending_z_score, 0)` |
| `trending_score_hourly_sum` | 24h pageview sum |
| `ebook_access` | Enum value (public first) |
| `lcc_sort` / `ddc_sort` | Library classification |
| `osp_count` | Open Syllabus Project citation count |
| `key` | `/works/OL...` key alphabetically |
| `random` | `random_1 asc` |
| `random.hourly` | `random_{YYYYMMDTHH} asc` — hourly-seeded random |
| `random.daily` | `random_{YYYYMMDD} asc` — daily-seeded random |
| `scans` | `ebook_count_i desc` (legacy) |

### Querying editions

**You cannot search editions directly.** `EditionSearchScheme` has the comment *"Kind of mostly a stub for now since you can't really search editions directly"* and its `universe = frozenset(["type:work"])` — it still filters to works, same as `WorkSearchScheme`. There is no `/editions/search.json` endpoint.

Editions are nested documents; access them via:
- `fl=editions:[subquery]` in a work query — block-join child query returns edition fields alongside each work
- `q=edition.isbn:1234567890` — the `edition.` prefix is stripped by `WorkSearchScheme.q_to_solr_params()` and passed as a block-join subquery filter
- Direct Solr: `{!child of=type:work}isbn:1234567890`

### SearchScheme pattern

Each document type has a `SearchScheme` subclass in `openlibrary/plugins/worksearch/schemes/`:

- `default_fetched_fields` — Solr fields returned by default
- `facet_fields` — which fields get facet counts
- `facet_rewrites` — maps UI filter values to Solr `fq` clauses (e.g. `("public_scan","true")` → `"ebook_access:public"`)
- `field_name_map` — aliases: `author` → `author_name`, `title` → `alternative_title`, `trending` → `trending_z_score`, etc.
- `sorts` — valid sort options
- `transform_user_query()` — rewrites the luqum parse tree (ISBN normalization, LCC/DDC normalization, field name aliasing)
- `build_q_from_params()` — builds `q` from structured API params
- `q_to_solr_params()` — adds boosting, highlighting, edition subquery

`WorkSearchScheme` also handles `work.` and `edition.` field prefixes in queries, allowing users to target nested edition fields directly.

## Facets

Facets are returned on the HTML `/search` page; `search.json` disables them for performance.

| Facet field | Notes |
|-------------|-------|
| `has_fulltext` | Boolean. Drives availability filter. |
| `language` | 3-letter codes. Multiple facet values are OR'd (unlike most facets which AND). |
| `author_facet` | Format: `"OL123A Author Name"`. Parsed by `read_author_facet()` which splits at first space after the OL key. |
| `subject_facet` | Also used as a direct filter (`fq=subject_facet:...`). |
| `first_publish_year` | Integer year. |
| `publisher_facet` | Copy-field from `publisher`. |
| `person_facet` | Subjects that are people. |
| `place_facet` | Subjects that are places. |
| `time_facet` | Subjects that are time periods. |
| `public_scan_b` | Boolean — maps to `ebook_access:public`. |

`process_facet()` and `process_facet_counts()` in `worksearch/code.py` convert raw Solr facet responses into `(key, display_name, count)` tuples.

## solrconfig.xml: Commit Settings and Performance Flags

**`conf/solr/conf/solrconfig.xml`** governs runtime behavior. Key settings:

### Commit chain (how quickly edits appear in search)

| Setting | Value | Meaning |
|---------|-------|---------|
| `autoSoftCommit.maxTime` | 3000ms (default) | Changes become **visible to searches** every 3 seconds. Override via `solr.autoSoftCommit.maxTime` env var. |
| `autoCommit.maxTime` | 15000ms (default) | Durable flush to disk every 15 seconds. Override via `solr.autoCommit.maxTime`. |
| `autoCommit.openSearcher` | `false` | Hard commit does NOT immediately open a new searcher — visibility and durability are decoupled. |

Combined with solr-updater's 0–5s polling latency, end-to-end latency from an OL edit to appearing in search is **3–8 seconds** in the happy path.

### Caches

| Cache | size | autowarmCount | Notes |
|-------|------|--------------|-------|
| `filterCache` | 512 | 128 | Filter queries (`fq` clauses). See issue #11472 for production tuning discussion. |
| `queryResultCache` | 512 | 128 | Ordered doc ID lists by query+sort. |
| `documentCache` | 512 | 0 | Stored field sets by doc ID. No autowarm (IDs change on reopen). |
| `perSegFilter` | 10 | 10 | Block-join cache for edition nested docs. **Intentionally small** — may be a bottleneck on edition-heavy queries. |

`enableLazyFieldLoading=true` — only loads stored fields that appear in the `fl` request param. Significant perf gain when `fl` doesn't include large text fields.

`queryResultWindowSize=20` — prefetches ±20 docs around the requested page range.

### Searcher warming

On every new searcher open, Solr runs warming queries from the `newSearcher` listener in `solrconfig.xml`:
1. `q=harry potter` with all 9 facets (`language`, `subject_facet`, `author_facet`, `first_publish_year`, `has_fulltext`, `person_facet`, `place_facet`, `publisher_facet`, `time_facet`) — primes filterCache and queryResultCache for typical faceted search
2. `q=*:*` filtered to `author_key:OL2162284A` with subject facets — primes author-works page
3. `q=subject:"Reading Level-Grade 6"` filtered to `ebook_access:[printdisabled TO *]` — primes availability-filtered search

**The warming queries also document the exact facet sidebar format** — use `facet=true` + `facet.field=<name>` for each sidebar dimension, plus `rows=0` if you want only facets:
```
fq=type:work&facet=true&facet.field=language&facet.field=subject_facet&facet.limit=25&rows=0
```

`useColdSearcher=false` — blocks all requests until the new searcher finishes warming (protects against cold-cache spikes at the cost of momentary queuing on commit).

`maxWarmingSearchers=4` — up to 4 searchers can warm in parallel.

### Replication

`ReplicationHandler` supports leader/follower via env vars: `ol.replication.role.leader=true` or `ol.replication.role.follower=true`. Follower polls leader every **60 seconds** after commits, replicating after commit and on startup.

Production: ol-solr0 and ol-solr2 run as followers under HAProxy unless one is temporarily designated leader during a full reindex.

### Update processors

- `tolerant-chain` (`maxErrors=-1`) — a single malformed document never fails the whole batch
- `update.autoCreateFields=true` by default — schemaless mode ON; unknown fields get auto-typed rather than rejected. Can be disabled to enforce strict schema validation.

## Local Development

```bash
# Check Solr is running
curl "http://localhost:8983/solr/openlibrary/select?q=*:*&rows=0"

# Trigger a full reindex (wipes and rebuilds from DB — takes 10–30 min)
docker compose run --rm home make reindex-solr

# If schema mismatch after adding fields to managed-schema.xml.
#
# The volume is per compose project, so name it from THIS project. A bare
# `openlibrary_solr-data` is the main checkout's, and deleting it from inside a
# worktree destroys an index that is not yours. Measured on one dev machine
# 2026-10-03: 66 `*_solr-data` volumes exist, one per worktree, and
# `openlibrary_solr-data` is among them -- so the bare instruction names a real
# volume and succeeds.
#
# Ask docker which volume is yours. Do not reconstruct the name: measured
# 2026-10-03, `basename "$PWD"` disagrees with the project name compose
# computes in 4 of 5 shapes, because compose lowercases and strips dots,
# spaces and a leading underscore. It agrees for our hyphenated lowercase
# worktree names, which is why a wrong form reads as correct.
#
# This needs nothing but docker -- no jq, no parsing.
docker compose stop solr
docker volume rm $(docker volume ls -q \
  --filter label=com.docker.compose.project="$(docker compose ps -a --format '{{.Project}}' | head -1)" \
  --filter name=solr-data)
docker compose up -d solr
docker compose run --rm home make reindex-solr

# Index a single work
docker compose run --rm home python -m openlibrary.solr.update --config conf/openlibrary.yml /works/OL45883W

# Check total indexed documents
curl "http://localhost:8983/solr/openlibrary/select?q=*:*&rows=0" | python3 -m json.tool | grep numFound

# Inspect a work document
curl "http://localhost:8983/solr/openlibrary/select?q=key:/works/OL45883W&rows=1&wt=json" | python3 -m json.tool

# Run a full-text search against Solr directly (bypassing the app)
curl "http://localhost:8983/solr/openlibrary/select?q=frankenstein&rows=3&wt=json" | python3 -m json.tool

# Print what a key would index (without sending to Solr)
docker compose run --rm home python -m openlibrary.solr.update --config conf/openlibrary.yml --update pprint /works/OL45883W
```

## Public Documentation

| Audience | URL | What's there |
|----------|-----|-------------|
| Developers (search.json API) | `https://openlibrary.org/dev/docs/api/search` | Embedded in every `search.json` response as `documentation_url`. FastAPI also serves OpenAPI at `/openapi.json`. |
| General users (search help) | `https://openlibrary.org/help/faq/search` | How to search on Open Library (FAQ page). **TODO: verify URL is current.** |
| Developers (full API) | `https://openlibrary.org/developers/api` | API overview including Books, Authors, Covers, Search, and Lists APIs. |

**Search syntax that works in `q=`**: Solr Lucene query syntax — field-qualified terms (`title:frankenstein`), boolean operators (`frankenstein AND shelley`), phrase queries (`"creature created"`), wildcards (`frank*`). The `WorkSearchScheme` also accepts field aliases (`author:shelley`, `subject:gothic`, `isbn:9780141439471`).

## Solr Reindex

### Local (development)

```bash
# Full reindex from DB (10–30 min)
docker compose run --rm home make reindex-solr

# If schema changed: reset this project's volume first (not `openlibrary_...`,
# which is the main checkout's — see the troubleshooting section above)
docker compose stop solr
docker volume rm $(docker volume ls -q \
  --filter label=com.docker.compose.project="$(docker compose ps -a --format '{{.Project}}' | head -1)" \
  --filter name=solr-data)
docker compose up -d solr
docker compose run --rm home make reindex-solr
```

### Production

Production reindexes use the `ReplicationHandler` leader/follower setup in `solrconfig.xml`:

1. One node is designated **leader** (`ol.replication.role.leader=true`)
2. The full reindex runs against the leader (either via Jenkins job or manual trigger)
3. Followers (ol-solr0, ol-solr2) poll leader every **60 seconds** and replicate the committed index
4. HAProxy automatically routes traffic away from a node being reindexed if it fails the health check

Full process: see the [olsystem wiki: Solr Re-Indexing](https://github.com/internetarchive/olsystem/wiki/Solr-Re%E2%80%90Indexing#doing-a-full-solr-reindex) (requires IA staff access).

## Bugs & Known Issues

**Q: Books are in the DB but not appearing in search.**
Diagnosis: `curl "http://localhost:8983/solr/openlibrary/select?q=*:*&rows=0"` — if numFound is 0, the index is empty.
Fix: `docker compose run --rm home make reindex-solr`. If schema mismatch persists, reset the volume first.

**Q: `solr-updater` fails with "unknown field" errors.**
Cause: `managed-schema.xml` was updated but the running Solr core still has the old schema.
Fix: Restart Solr and reset the volume — it reloads the schema from the config directory on startup.

**Q: Local Solr exits with code 137 (OOM).**
Cause: Insufficient heap for the local container.
Fix: Add `-e SOLR_HEAP=512m` to the Docker run, or skip Solr if your feature doesn't need search.

**Q: `solr_next` flag — when do I use it?**
Use it when adding new schema fields that require a full reindex before they're active in production. New indexing code writes the new fields only when `solr_next=True`. Once the reindex completes and the flag is deployed, remove it.

**Q: A query that works on `/search` returns nothing from `search.json`.**
Common cause: the HTML search page applies additional query rewriting in `_prepare_solr_query_params()` in `worksearch/code.py`. Check there first.

**Q: `datetimestr_to_int()` in `work.py` has Python 2 syntax.**
Line 256: `except TypeError, ValueError:` — this is Python 2 multi-exception syntax. It causes `SyntaxError` under Python 3.12 when the full file is imported. See `conftest.py` workaround notes in the test suite.

**Q: Solr hangs or fails to start after modifying `managed-schema.xml`.**
See [#12952](https://github.com/internetarchive/openlibrary/issues/12952). Reset the volume.

## Product Direction

Active issues — check these before adding new Solr fields or modifying the schema:

| Issue | What | Priority |
|-------|------|---------|
| [#11650](https://github.com/internetarchive/openlibrary/issues/11650) | 2026 H1 Full Solr Reindex | P2 |
| [#12138](https://github.com/internetarchive/openlibrary/issues/12138) | Index OPDS feeds + pricing data from BWB/Lenny | P2 |
| [#7450](https://github.com/internetarchive/openlibrary/issues/7450) | Realtime book availability in Solr | Feature |
| [#9156](https://github.com/internetarchive/openlibrary/issues/9156) | Cover width/height fields (`cover_width`, `cover_height`) for CLS | P3 |
| [#12978](https://github.com/internetarchive/openlibrary/issues/12978) | Context-aware facet values API | P2 |
| [#11472](https://github.com/internetarchive/openlibrary/issues/11472) | Tune Solr cache configs | P2 |
| [#11695](https://github.com/internetarchive/openlibrary/issues/11695) | Deprecate/rename dynamic field declarations | P4 |
| [#7551](https://github.com/internetarchive/openlibrary/issues/7551) | English stemming applied to non-English author/title text | Bug |
| [#5393](https://github.com/internetarchive/openlibrary/issues/5393) | Stopword detection | P3 |
| [#12079](https://github.com/internetarchive/openlibrary/issues/12079) | Unify series search algorithm | P3 |
| [#11586](https://github.com/internetarchive/openlibrary/issues/11586) | Remove legacy IA-related Solr fields (`lending_edition_s`, `lending_identifier_s`, `printdisabled_s`) | P4 |
| [#11651](https://github.com/internetarchive/openlibrary/issues/11651) | Integration tests for Solr | P2 |

## PR Review Expectations

Any PR that touches Solr should address these before merging:

**Schema changes (`managed-schema.xml`)**
- [ ] New field has a clear purpose; not derivable from existing fields at query time
- [ ] Field type is appropriate: `string` for facets/filters, `text_en_splitting` for English full-text, `text_international` for author names, `pint`/`pfloat` for numerics
- [ ] `multiValued` is explicit and correct
- [ ] If `stored=false`: documented why (facet-only fields typically don't need stored values)
- [ ] `indexed=false, stored=false` for sort-only function fields (like trending)
- [ ] A full reindex will be required — noted in the PR description
- [ ] `solr_next` flag used if rolling out before reindex is complete

**Updater changes (`openlibrary/solr/updater/`)**
- [ ] New data fetched via `data_provider` — not direct DB calls inside the updater
- [ ] Handles missing/null values gracefully (many OL records are incomplete)
- [ ] Orphaned edition path still works (fake work key `/works/OL123M`)
- [ ] Order of updaters in `update.py` is preserved unless there's a documented reason to change it
- [ ] `author.py` updater: any changes to what's fetched from Solr use the JSON facet API correctly

**Search/query changes (`worksearch/`)**
- [ ] `AVAILABILITY_TO_PARAMS` in `code.py` kept in sync with `constants.js` in the JS frontend
- [ ] New facet fields added to `facet_fields` in the appropriate `SearchScheme`
- [ ] `facet_rewrites` updated if new filter values are added
- [ ] `field_name_map` updated if new field aliases are needed

**Any Solr PR**
- [ ] Tested locally with a running Solr instance (not just unit tests)
- [ ] `docker compose run --rm home make reindex-solr` completes without errors
- [ ] `curl "http://localhost:8983/solr/openlibrary/select?q=frankenstein&rows=3"` returns expected results
- [ ] If new fields added: `--update pprint /works/OL45883W` output shows the new field populated

## Pending Schema Changes (Open PRs)

These PRs add new Solr fields and have schema-first deployment requirements. Reviewed June 2026 by Saul.

---

### PR #12689 — Near-Realtime Loan Availability (`ebook_unavailable`)

**Branch:** `7450/loan-availability-updater`

> The review that stood here was written in June 2026 against a design that no
> longer exists. It described three fields — `ebook_availability`,
> `ebook_becomes_available` and `loan_uid` — a `pdate` type, and a cursor used
> as a resume watermark, and its open item was that `ebook_becomes_available`
> needed `docValues="true"`. None of that applies: the PR now adds **one**
> field.

**Schema addition — BOTH fields, or the daemon is inert.**

```xml
<field name="ebook_unavailable" type="pint" multiValued="false" docValues="true" stored="false" indexed="false"/>
<field name="ebook_unavailable_ts" type="plong" multiValued="false" docValues="true" stored="false" indexed="false"/>
```

`docValues=true`, `stored=false`, `indexed=false` on a numeric type is exactly
the shape `update.partial.requireInPlace` demands — verified against a live
Solr 10.0.0 core, where a stored+indexed field and an unknown field are both
rejected with HTTP 400 while these are accepted, singly and together.

**Applying only the first field is worse than applying neither.** The daemon
writes both in one atomic update, so an undeclared `ebook_unavailable_ts` makes
Solr reject the whole document with HTTP 400 — the same rejection that control
experiment demonstrates. The daemon catches that, logs "Poll failed; prior
state stands", and loops forever: alive, healthy-looking, marking nothing. And
because marks are ordered ahead of clears in the batch, the clears never land
either. The result is every checked-out book published as borrowable, which is
the exact failure this field exists to prevent.

The other two fields were dropped because the poll cannot honestly maintain
them: there is no cursor to record, and the index exposes no due date from
which to compute "available in N days" (probed with controls — every plausible
date field matches 0 documents). A renewal would move such a date with no event
to observe, and `"set": null` cannot clear a stale one.

**Deploy note:** this is still a schema change and still needs the special
deploy, but it is now one field rather than three.

### PR #12916 — Cover Dimensions in Solr (`cover_i`, `cover_width`, `cover_height`)

**Branch:** `feature/cover-size-in-solr`  
**Status:** Open. Labeled `Needs: Special Deploy` ✅. Dependency #12915 already merged ✅.

**Schema additions in `managed-schema.xml`:**

```xml
<field name="cover_i" type="pint" />
<field name="cover_width" type="pint" />
<field name="cover_height" type="pint" />
```

**Analysis:**

1. `cover_i` (`pint`): This field previously matched the `*_i` dynamic field rule and was already being indexed. Making it an explicit static field is correct — explicit declarations take precedence over dynamic fields and allow setting specific properties. Safe to add.

2. `cover_width` / `cover_height` (`pint`): Genuinely new fields. Values come from `SELECT width, height FROM cover WHERE id=$cover_id` against the covers DB. Both `EditionSolrBuilder` and `WorkSolrBuilder` are updated.

3. All three fields are missing `multiValued="false"`. A work or edition has one primary cover, so this should be explicit. The default is `multiValued="false"` in most Solr configurations, so it works, but explicit is better per the PR review checklist.

4. For `pint` fields, docValues are enabled by default via the field type definition — no explicit `docValues="true"` is needed. Sort and function queries will work.

**Deployment ordering:**

The `Needs: Special Deploy` label is correctly applied. Without it, if the code deploys before the schema update, schemaless mode would auto-create `cover_width` and `cover_height` as `text_general` (storing pixel integers as tokenized text — wrong type, queryable as numbers would break). Schema must go to production Solr first.

Correct deploy sequence:
1. Apply the three field declarations to production Solr schema
2. Deploy app code (#12916)

The dependency on #12915 (dead code cleanup) is satisfied — #12915 merged.

---

### PRs #12852 and #12846 — TBP Prices/Acquisition Feed

**Status:** Open. Related issue #12993 (affiliate server broken) blocks the full flow.

**Solr schema impact: none.** Neither PR touches `managed-schema.xml`. Both add:
- `openlibrary/core/schema.sql` — PostgreSQL table `tbp_feed_registry`
- `openlibrary/core/tbp.py` — Python class for feed ingestion
- Tests

The prices/acquisition data lands in the OL PostgreSQL DB (via TBP feed). The path from DB to Solr is future work — field names TBD. These PRs have no Solr deployment ordering constraint.

---

### Conflict Analysis

No field name conflicts among the three PR sets. All three add distinct fields:
- #12689: `ebook_unavailable`, `ebook_unavailable_ts` (two fields; `ebook_becomes_available` and `loan_uid` were removed before merge)
- #12916: `cover_i`, `cover_width`, `cover_height`
- #12852/#12846: no Solr fields

Both #12689 and #12916 modify `managed-schema.xml`. They can be applied to the production schema in a single operation (one Solr schema update with all five fields), or sequentially in any order.

**Recommended deploy sequence (all three):**

| Step | Action |
|------|--------|
| 1 | Apply #12689 + #12916 schema fields to production Solr (can do both at once) |
| 2 | Deploy #12916 code (cover dimensions) |
| 3 | Deploy #12689 code (loan availability updater + core changes) |
| 4 | Run `loan_availability_updater.py` as a one-time backfill |
| 5 | #12852 / #12846 — independent; no Solr ordering concern |

## For New Contributors

1. Read the [OL dev setup](../ai-coding-guide.md) first — Docker is required
2. Start with `conf/solr/conf/managed-schema.xml` to understand what fields exist and why
3. Read `openlibrary/solr/updater/work.py` — it's the most complex piece; understanding `WorkSolrBuilder` unlocks everything
4. Read `openlibrary/plugins/worksearch/schemes/works.py` — this is the bridge between user queries and Solr parameters
5. The `ebook_access` enum and `AVAILABILITY_TO_PARAMS` are a frequent source of bugs — understand both before touching availability filters
6. Public docs: [docs.openlibrary.org/advanced/solr.html](https://docs.openlibrary.org/advanced/solr.html)
7. For OPDS/batch search integration, see [pm/workflows/opds-system.md](../../../pm/workflows/opds-system.md)
