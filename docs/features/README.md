# Features

> **Status:** partial
> **Sources:** code synthesis (`openlibrary/core/bookshelves.py`, `ratings.py`, `observations.py`, `booknotes.py`, `yearly_reading_goals.py`, `follows.py`, `lists/model.py`)
> **Last ingested:** 2026-06-27

OL's patron-facing social and engagement features: reading log (bookshelves), ratings, observations, booknotes, reading goals, lists, series, and follows. All features are keyed by `work_id` (not edition) except booknotes, which has edition granularity.

---

## Reading Log (Bookshelves)

**DB table:** `bookshelves_books`
**PK:** `(username, work_id, bookshelf_id)`

Four preset shelves — hardcoded, not user-configurable:

| ID | Name | JSON key |
|----|------|---------|
| 1 | Want to Read | `want_to_read` |
| 2 | Currently Reading | `currently_reading` |
| 3 | Already Read | `already_read` |
| 4 | Stopped Reading | `stopped_reading` |

A work can be on only one shelf at a time per user (one row per `(username, work_id)`).

**Display flow:** `Bookshelves.get_users_logged_books()` queries `bookshelves_books` for work IDs + logged dates, then fetches full work data from Solr (search scheme, not Infogami). DB holds "when" and "which shelf"; Solr holds "what book details." Results support pagination, sorting, and full-text filtering (`q=` param runs a filtered Solr query against the user's logged work IDs).

**Year-based filtering:** `checkin_year` param filters `bookshelves_books.created` to a specific year — used for annual reading stats.

---

## Ratings

**DB table:** `ratings`
**PK:** `(username, work_id)`
**Scale:** 0–5 stars (0 = no rating)

Star ratings are per-work, per-user. A `WorkRatingsSummary` TypedDict stores `ratings_average`, `ratings_sortable` (Bayesian-smoothed via Wilson lower bound or similar), and `ratings_count_1` through `ratings_count_5` breakdown.

---

## Observations (Community Tags)

**DB table:** `observations`
**PK:** `(username, work_id, type_id, value_id)`

Structured community metadata. Not free-form — users pick from defined options per category. Observation types with active values (as of 2026):

| ID | Label | Example values |
|----|-------|---------------|
| 1 | Pace | Slow paced, Medium paced, Fast paced, Meandering |
| 2 | Enjoyability | Boring, Engaging, Exciting, Neutral |
| 3 | Clarity | Succinct, Dense, Incomprehensible, Confusing, Clearly written |
| … | … | (more in `observations.py::OBSERVATIONS`) |

Each category supports `multi_choice`. Older values are marked `deleted: True` — they still exist in the DB but are hidden in UI. New values get new IDs (no in-place edit).

---

## Booknotes

**DB table:** `booknotes`
**PK:** `(username, work_id, edition_id)`
**Edition sentinel:** `edition_id = -1` (constant `NULL_EDITION_VALUE`) means note is not edition-specific

Free-text private notes. One note per (user, work, edition). Notes are not public.

---

## Yearly Reading Goals

**DB table:** `yearly_reading_goals`
**Key:** `(username, year)` → `target` (integer: number of books to read)

Only the target is stored — the progress is computed at read time by counting `bookshelves_books` entries with `bookshelf_id=3` (Already Read) and `created` within the target year. No separate progress counter is maintained.

`YearlyReadingGoals.select_by_username_and_year(username, year)` returns the goal record.
Goal update: `update_target(username, year, new_target)`.

---

## Follows (PubSub)

**DB table:** `follows`
**PK:** `(subscriber, publisher)` — both are OL usernames

Patron-follows-patron. `PubSub.subscribe(subscriber, publisher)` creates the edge; `unsubscribe` removes it. Used to surface followed patrons' reading activity in a patron's feed. `is_subscribed(a, b)` checks the edge.

---

## Likes (in review as of 2026-07-28, PR #12932 — not yet merged)

**DB table:** `likes`
**PK:** `(username, key)` — `key` is a **full generic Infogami key** (`TEXT`, e.g. `/works/OL123W`), not a `work_id` integer like every sibling feature above.
**Value:** `SMALLINT CHECK (value IN (1, -1))` — 1 = like, -1 = dislike

This is a structurally different design from every other feature on this page: because `key` is a generic string column with **no type or existence validation anywhere in the API layer** (`openlibrary/plugins/upstream/likes.py`), it can reference a work, edition, author, list, or any arbitrary/nonexistent string — nothing in the code rejects a `/lists/OL...L` key or a key that doesn't resolve to a real object. Every sibling feature above is hard-scoped to `work_id` (or edition for booknotes) and structurally cannot reference an author or list at all.

**Scope decision (2026-07-29):** intentionally used for lists only for now (and possibly future prompts/activity-feed events) — **not** works, editions, or authors, even though nothing in the code enforces this. This sidesteps the redirect/merge gap below for the current use case, since lists don't go through the librarian merge/redirect flow works and authors do.

**Redirect/merge gap (deferred, not currently applicable given the scope decision above, but relevant if that ever changes):** `Likes` does not inherit `db.CommonExtras` and has no `update_work_id` — confirmed not wired into the mechanism described below. A `likes` row pointing at a work/author key that later gets merged/redirected would not be updated or deleted; it would become orphaned (invisible from the new canonical key's like count, but not corrupted — the old row and key are unaffected). See "What's Broken / Fragile" below. Note this gap would be broader for `likes` than for its siblings if it were ever extended to works/authors: `likes` can reference authors too, and there is no author-redirect resolver anywhere in the codebase (only `Work.resolve_redirects_bulk`/`resolve_redirect_chain` exist).

---

## Lists and Series

**Infogami type:** `/type/list` — stored as Infogami objects (not DB tables)
**URL pattern for lists:** `/people/{username}/lists/OL{n}L`
**URL pattern for series:** `/series/OL{n}L`

`List` (class in `lists/model.py`) extends `Thing`. Lists are user-created collections of seeds (works, editions, authors, subjects). Series are curated sequences of works — also `/type/list`-based but with position ordering via `WorkSeriesEdgeDB`.

Registered types:
- `/type/list` → keys matching `/people/.*/lists/OL\d+L`
- `/type/series` → keys matching `/series/OL\d+L`

**Series ordering:** `List.get_work_sort_key()` sorts by `series_position` edge from the work back to the series list.

---

## Key Files

| File | Purpose |
|------|---------|
| `openlibrary/core/bookshelves.py` | Reading log — add/remove/query shelves; `get_users_logged_books()` |
| `openlibrary/core/ratings.py` | Star ratings — add, get, aggregate |
| `openlibrary/core/observations.py` | Structured community tags; `OBSERVATIONS` dict is the schema |
| `openlibrary/core/booknotes.py` | Free-text patron notes per edition |
| `openlibrary/core/yearly_reading_goals.py` | Reading goals — create/update/delete per user+year |
| `openlibrary/core/follows.py` | `PubSub` — patron-follows-patron |
| `openlibrary/core/lists/model.py` | `List` and `Series` Infogami thing classes |
| `openlibrary/core/bookshelves_events.py` | Events triggered by bookshelf changes (integrations) |

---

## What's Broken / Fragile

- **Filter limit hardcoded:** `FILTER_BOOK_LIMIT = 30_000` — reading log search loads up to 30k work IDs from DB to build a Solr filter query. At scale, this is expensive.
- **Observations schema is code:** `OBSERVATIONS` dict in `observations.py` is the canonical schema. Adding a new observation type requires a code deploy, not a data change.
- **Deleted observation values:** Values with `deleted: True` remain in the DB — old patron data references IDs that the UI no longer shows. No migration path exists.
- **Series integration status:** Series are functional as Infogami types, but deeper OL integration (e.g., auto-populated next-book suggestions) is not complete.
- **Redirect/merge resolution only covers 5 tables, only for works:** when a Work gets merged/redirected, `Work.resolve_redirect_chain()` (`openlibrary/core/models.py`) explicitly updates exactly `Bookshelves` (readinglog), `Ratings`, `Booknotes`, `Observations`, and `Bestbook` via their shared `db.CommonExtras.update_work_id()` method (hardcoded to a `work_id` column). This is invoked in bulk via `scripts/update_stale_work_references.py` → `Work.resolve_redirects_bulk()`. `Follows` and `Likes` are not wired in at all. There is also no equivalent mechanism anywhere for Author merges/redirects — confirmed via code search, not just absence of docs.

---

## Common Confusion

- **Lists vs. Bookshelves:** Bookshelves (Want to Read, etc.) are the reading log — one shelf per work, backed by a DB table. Lists are user-created named collections stored as Infogami `/type/list` objects — arbitrary, not preset.
- **Reading goal progress:** Not stored — always computed from the "Already Read" shelf count filtered by year.
- **Observations vs. Subjects:** Subjects are OL metadata on works (from MARC, imports, etc.). Observations are patron-assigned structured tags — separate concept, separate table.

---

## Dependencies

**Depends on:**
- [[core-operations]] — Infogami `Thing` class for List/Series; `web.ctx.site` for data access
- [[search]] — `get_users_logged_books()` enriches DB records with Solr work data
- [[auth]] — all features require a logged-in patron

**Depended on by:**
- [[lending]] — reading log `Currently Reading` shelf can reflect borrowed books
- [[bookreader]] — reading progress, bookmarks within BookReader integrate with reading log
- [[core-vitals]] — `bookshelves_books` is the primary demand signal for the Demand Score; `monthly_edition_readinglog_counts` and `historical_work_readinglog_counts` feed directly into the CVS formula

---

*Sources: `bookshelves.py`, `ratings.py`, `observations.py`, `booknotes.py`, `yearly_reading_goals.py`, `follows.py`, `lists/model.py` (code synthesis) · See [[README]] · [[METHODOLOGY]]*
