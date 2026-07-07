# Open Library Performance Review — July 2026

An exhaustive review of where page-load latency comes from across the stack — the Python data-access layer, Solr and search, caching, and frontend delivery — with an argued case for the ten highest-leverage changes. Every claim below was verified directly against the code (file and line references are to `master` at the time of review).

Five of the ten are low-risk quick wins and have been opened as draft PRs:

| Draft PR | Change |
|---|---|
| [#13130](https://github.com/internetarchive/openlibrary/pull/13130) | Avoid duplicate IA loan API call in `get_loan` |
| [#13131](https://github.com/internetarchive/openlibrary/pull/13131) | Restore real TTLs on cached list fetchers |
| [#13132](https://github.com/internetarchive/openlibrary/pull/13132) | Batch the per-doc ratings lookup on the reading log |
| [#13133](https://github.com/internetarchive/openlibrary/pull/13133) | Defer athena.js and all.js footer scripts |
| [#13134](https://github.com/internetarchive/openlibrary/pull/13134) | Reserve search-result cover space to reduce layout shift |

The other five need production metrics, relevance validation, or infra coordination before shipping and are argued here as proposals.

## Method

Three parallel deep-dives (backend data layer; Solr/search; frontend delivery and templates), followed by direct verification of every load-bearing claim in the source. One initially promising candidate was disproven and is documented in "Rejected" below so it isn't re-litigated.

---

## The Top 10

### 1. Dedupe the duplicate IA loan API calls on every book page — [#13130](https://github.com/internetarchive/openlibrary/pull/13130)

`get_loan()` (`openlibrary/core/lending.py:634-644`) made two sequential, unconditional blocking POSTs to the archive.org loan API and let the second result overwrite the first. For anonymous lookups — every edition-page loan check via `get_edition_loans()` (`plugins/upstream/borrow.py`) — the two calls were byte-identical. Fixing this also fixes two correctness bugs: a found loan being clobbered by `None`, and an unfiltered fallback query that could return another patron's loan when an account has no linked `itemname`.

**Why it's #1:** it removes a synchronous external HTTP round-trip from the render path of one of the most-viewed page types, for a five-line diff.

### 2. Fix the two broken `timeout=0` list caches — [#13131](https://github.com/internetarchive/openlibrary/pull/13131)

`get_cached_recently_modified_lists` and `get_active_lists_in_random` (`plugins/openlibrary/lists.py:1094-1156`) passed `timeout=0` to `cache.memcache_memoize`. The staleness check in `core/cache.py` (`t + self.timeout < time.time()`) is then true on **every call**, so every request through these functions spawned a background thread re-running `site.things` + `get_many` over ~120 lists. A stranded `# dateutil.HALF_HOUR_SECS)` comment shows a temporary cache-disable that was never reverted. The PR restores 30 min / 5 min TTLs.

### 3. Resize Solr's caches and slow the soft-commit churn *(proposal)*

`conf/solr/conf/solrconfig.xml`: `filterCache`, `queryResultCache`, and `documentCache` are all size **512** (lines 351-375) for a catalog of tens of millions of documents with heavily-reused filter queries (`type:work`, `ebook_access`, `author_key`, availability). Meanwhile `autoSoftCommit maxTime=3000` (line 251) opens a new searcher every 3 seconds under indexing load, discarding those caches with only 128 autowarmed entries. The two compound: caches that are too small to begin with are also flushed constantly.

**Recommendation:** check `admin/mbeans` cache hit-rates in production; raise `filterCache`/`queryResultCache` well above 512 (filter cache entries for a 40M-doc index are ~5MB bitsets, so size against heap), raise `documentCache` to at least a few thousand, and stretch `autoSoftCommit` to 30-60s unless near-real-time search freshness is a hard product requirement. Needs prod cache-stat validation and heap headroom checks — config-only, but not blind-shippable.

### 4. Eliminate the second Solr round-trip on every search *(proposal)*

`_get_readable_count` (`plugins/worksearch/code.py:181-207`) runs a second full Solr query per `/search` — with the expensive editions block-join opted in via `fields=["key","editions"]` — purely to compute the count under the "Readable Only" toggle. The facets were already moved off the critical path into an async partial (`partials.py`, `SearchFacetsPartial`); this count should either move into that same async partial, drop the block-join from its query shape, or be approximated from the `ebook_access` facet.

**Why it matters:** it roughly doubles the Solr cost of the most common expensive request on the site.

### 5. Shrink the 16-field `qf` toward the `text` field *(proposal)*

Every keyword search scores across ~16 query fields plus `pf`/`pf2` phrase passes plus a function-query boost (`plugins/worksearch/schemes/works.py:355-368`), and on `/search` also a nested edismax inside the editions block-join with a per-row `editions:[subquery]` executed once per returned work (×20). The code's own TODO (works.py:361) already prescribes the fix: rework the `text` copyField to exclude noisy sources (`first_sentence`, `by_statement`, …) and collapse most of `qf` into `text`. Bonus: `first_sentence` and `subject` are currently both `stored` and copied into `text`, inflating the index.

**Risk:** relevance-sensitive; needs A/B or offline relevance evaluation against a query log. Highest ceiling of any search change here.

### 6. Batch the ratings N+1 on the reading log — [#13132](https://github.com/internetarchive/openlibrary/pull/13132)

`LoggedBooksData.load_ratings` (`core/models.py`) ran one `SELECT` per displayed book on the My Books already-read shelf — up to 25 sequential Postgres round-trips per page view. The PR adds `Ratings.get_users_ratings_for_works` (single `IN`-list query, mirroring `Bookshelves.get_users_read_status_of_works`) and rebuilds the list in doc order with the same 0-default.

### 7. Shrink the fixed `all.js` payload on every page *(proposal)*

The ~60 lazily-loaded feature chunks in `plugins/openlibrary/js/index.js` are genuinely well-split, but the fixed cost that ships on *every* page — jQuery + jquery-ui + jquery-colorbox + the full `@sentry/browser` SDK (~155 KB gz budget, `bundlesize.config.json`) — lands on simple content pages too. Sentry can be lazy-initialized (queue events until loaded); jquery-ui usage should be audited down to the widgets actually used. This is main-thread parse/execute time on every single page view, the frontend change with the broadest reach.

### 8. Backfill memcache on single-key `site.get()` misses *(proposal)*

`plugins/openlibrary/connection.py:293-307`: a revisionless single-key `get` reads memcache but on a miss returns straight from infobase **without writing the result back** — unlike `get_many` (:318-342), which does `mc_set_multi` for its miss set. After any eviction, repeated single-key gets keep hitting infobase/Postgres until some write path repopulates the key. Verify first that the infobase write path doesn't already populate these keys (the asymmetry suggests it populates on document *save*, which doesn't help cold/evicted reads), then mirror the `get_many` backfill.

### 9. Defer athena.js and all.js as a pair — [#13133](https://github.com/internetarchive/openlibrary/pull/13133)

`templates/site/footer.html` loaded analytics (`athena.js`, proxied to archive.org) synchronously ahead of a synchronous `all.js`, blocking the parser and chaining the main bundle behind an external upstream. The dependency is real — `initAnalytics` and `Carousel.js` use `window.archive_analytics` unguarded, so athena must never be deferred *alone* — but `defer` on **both** preserves execution order while unblocking the parser. Also fixes the `server_ms` analytics read, which previously executed before its source div was parsed. Full decoupling (`async` + guards) is the follow-up tracked in #4474.

### 10. Reserve cover space on search results — [#13134](https://github.com/internetarchive/openlibrary/pull/13134)

List-view search covers had CSS-pinned width (175px) but no height signal until load, so every cover — including the first four, which load eagerly for LCP — grew 0→300px and pushed results down. One line of CSS (`aspect-ratio: auto 2 / 3`) reserves a typical cover box pre-load and defers to the intrinsic ratio after load, so settled layout is unchanged. Grid view and carousels already reserve fixed heights; this was the remaining shift source on the most-used page.

---

## Rejected during verification

**"Author page calls `works_by_author` twice"** — the stale TODO at `plugins/upstream/models.py:443` suggests `get_books` and `get_work_count` duplicate a Solr query per author page. Verified false: `get_work_count` is called only from the `/authors/OLxxxA/works` JSON API (`plugins/openlibrary/api.py`), which never calls `get_books`; the HTML author page calls only `get_books` and reads `num_found` from it. The two call sites are on disjoint request paths. The TODO comment should simply be deleted.

## Already well-optimized (verified — don't re-do)

- **Home page**: fully memcached for 5 min with background prethread recompute (`home.py`); featured subjects cached 1 h.
- **Carousels**: lazy-loaded placeholders by default; the partial's Solr fetch is memcached 300 s keyed on query hash; `facet=False`.
- **Work page editions**: `get_sorted_editions` batches via one `get_many` + one bulk availability call; `get_availability_async` batches, reads `get_multi` first, writes back with 5-min TTL.
- **Search facets**: already deferred off the critical path to an async partial with `rows=0`.
- **Solr hygiene**: `fl` explicitly scoped everywhere; large text fields `stored="false"`; numeric sort/boost fields on docValues; user wildcard/fuzzy/regex operators escaped; `timeAllowed` set with cache-warming pass-through; `newSearcher` autowarming for the three main query shapes.
- **Frontend delivery**: per-page CSS splitting (exactly 3 render-blocking stylesheets); ~60 lazily-loaded JS chunks; system-font-only stack (zero webfont requests); `?v=md5` fingerprinting with `expires max` on `/static/build`; book-page hero cover uses preload + `fetchpriority=high` + inline `aspect-ratio` (the pattern #13134 extends to search).

## Honorable mentions (below the top 10)

- `List.load_changesets` runs one `recentchanges()` query per edition (`core/lists/model.py:224-242`) — batchable; affects list detail/export.
- The 5-6 uncached per-user DB reads on every logged-in work-page view (`core/models.py:545-616`) — individually indexed and fast, but a candidate for one combined fetch.
- Reading-log filter path pulls up to 30,000 rows to build a Solr query (`core/bookshelves.py`, `FILTER_BOOK_LIMIT`) — bounded but heavy for power users.
- Non-build `/static` assets get only `expires 1h` in nginx (`docker/web_nginx.conf`) vs `expires max` for `/static/build`.
- The shared Solr `httpx.AsyncClient` has no explicit connection-pool limits and no retry policy (`utils/solr.py`); errors degrade to empty results.
- Trending carousel filters on `trending_score_hourly_sum`, which is `indexed="false"` in the schema — the range predicate falls back to a docValues scan (mitigated by carousel caching and an ANDed indexed filter).
- `macros/CoverImage.html` is dead code (no callers; references Python 2 `basestring`) — delete.
