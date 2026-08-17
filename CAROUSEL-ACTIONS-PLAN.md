# Carousel actions — plan

Branch `carousel-actions` off `upstream/master` (297ed7c20). Goal: on the
subject page, replace the slick carousel with `<ol-carousel>`, add a
Covers/List view toggle, and add a per-book "+" popover with shelf actions,
rating, and add-to-list.

## 1. What exists today (findings)

**Subject page carousel** — `templates/subjects.html:60` calls
`macros.QueryCarousel(query=page.solr_query, sort='trending,...', lazy=True)`.
Lazy path emits a `.lazy-carousel` stub → `js/lazy-carousel.js` →
`GET /partials/LazyCarousel.json` → `{"partials": "<html>"}` (whole section,
rendered by `books/custom_carousel.html` + `custom_carousel_card.html`) →
slick (`js/carousel/Carousel.js`). Load-more: `GET /partials/CarouselLoadMore.json`
→ `{"partials": ["<card html>", ...]}`. Data: `_CAROUSEL_FIELDS`
(`plugins/openlibrary/partials.py:470`) = key, title, subtitle, editions,
author_name, availability, cover_i, ia, provider ids. **Missing** for the
list view: `author_key`, `ratings_average`, `ratings_count`,
`first_publish_year`, `edition_count`, `ebook_count_i` — all exist in Solr,
just not requested. CTA/availability is server-side only
(`macros/LoanStatus.html` → `lending.get_lending_state()`).

**`<ol-carousel>`** (`components/lit/OlCarousel.js`) — presentation only:
light-DOM children, scroll-snap, arrows, `ol-carousel-page-change` event,
`next()/prev()/goToPage()`. No fetch/pagination. Wants real `src` +
`loading="lazy"` (not slick's `data-lazy`). Unused in prod templates so far.

**Shelves** — `POST /works/OL..W/bookshelves.json` form body
`bookshelf_id=1|2|3|4|-1`, `edition_id?`, `dont_remove?` → FastAPI
`fastapi/internal/api.py:281`; returns 401 JSON when logged out (legacy JS
doesn't handle that — star-ratings JS does, `js/star-ratings/index.js:35`).
Shelf ids `core/bookshelves.py:35`. Per-user state for a batch of works:
`Bookshelves.get_users_read_status_of_works(username, work_ids)`
(`core/bookshelves.py:613`) — server-side only, no JSON endpoint.

**Ratings** — `POST /works/OL..W/ratings.json` form `rating=1..5` (omit →
delete); server auto-shelves to Already Read (`core/ratings.py:174`). Current
user's rating: only `get_users_rating_for_work` (single) — no batch helper.

**Lists** — `js/lists/ListService.js`: create `POST {userKey}/lists.json`
`{name, description, seeds}`; add/remove `POST {listKey}/seeds.json`
`{add|remove: [{key}]}`; user's lists + membership
`GET /partials/MyBooksDropperLists.json` → `{dropper: html, listData:
{listKey: {members: [seedKeys], listName}}}` (401 logged-out). Lists-for-seed
`GET /works/OL..W/lists.json` (no ownership flag).

**Auth in JS** — inferred from server markup (`.generic-dropper--disabled`,
`data-user-key`); login intent via `queueAction()` cookie + redirect.

**Icons** — `<ol-icon>` / `$:macros.icon()` are on PR #12955 (still open),
NOT on master. Master Lit components inline Lucide `<svg>` paths
(`OlCarousel.js:272`). Leftover untracked `static/icons/sprite.svg` and
`icons.generated.js` on this checkout are orphans.

**Popover-in-carousel blocker (F2 in BOOK-ACTIONS-AUDIT.md)** — resolved on
master: `OlPopover` promotes to the top layer (`utils/top-layer.js`).

**Dev caveat** — availability mock always returns `{}`, so every card is
"Find in a library" locally (see memory `reference_dev_availability_always_empty`).

## 2. Architecture

### Data: JSON, split into public + per-user
- **`GET /partials/… → new `GET /api/carousel.json`** (FastAPI, alongside
  `fastapi/partials.py`) — params mirror `LazyCarouselParams`/`CarouselLoadMore`:
  `q, sort, limit, offset, has_fulltext_only, safe_mode, fallback`. Returns
  `{docs: [...], num_found, offset, limit}`. Reuses
  `gather_lazy_carousel_data_async` (memcached 300s) with an extended field
  list. Each doc is normalized server-side into a flat card model:
  `key, title, subtitle, authors[{key,name}], cover_id, cover_edition_key,
  edition_key, ia, first_publish_year,
  ratings{average,count}, access{state, label, url, external?, copies?}`.
  `access` comes from `get_lending_state()` so the CTA logic isn't duplicated
  in JS. Cacheable (no user data).
- **`GET /api/me/book-state.json?work_ids=OL1W,OL2W`** — new, uncached, 401
  when logged out. `{shelves: {OL1W: 1}, ratings: {OL1W: 4}}`. Backed by
  `get_users_read_status_of_works` + a new `Ratings.get_users_ratings_of_works`
  (same SQL shape). Client fires it after each page of docs arrives.
- Lists: reuse `MyBooksDropperLists.json` `listData` for the user's lists +
  membership (fetched lazily on first "Add to list", cached per page);
  `ListService` for create/add/remove.
- Existing shelf/rating POST endpoints reused as-is; add 401 handling →
  `queueAction()` + login redirect (decided).

### Components (Lit, `openlibrary/components/lit/`)
- **`<ol-books-display>`** — the controller. Named for what it is (a set of
  books) not how it lays them out: `view` is an open enum — `covers` (carousel),
  `list` (rows) now; `grid` (multi-row cover grid) and others later. Attributes:
  `query, sort, limit, url (see-all), title, has-fulltext-only, fallback`,
  `view="covers|list"` (default set in code; no user preference saved yet),
  plus `label-*` strings for i18n. Owns: fetch +
  pagination (`ol-carousel-page-change` near end → next page; list view
  "Show N more"), the Covers/List `<ol-segmented-control>` toggle, the
  user-state overlay, "Show N more · Collapse · See all" footer in list view.
  Renders `<ol-carousel>` (covers) or a `<ul>` (list) from the same docs.
- **`<ol-book-card>`** — one doc, `variant="cover|row"`. Cover variant: cover
  image (real `src`, `loading="lazy"`), availability badge (NOT ONLINE /
  PREVIEW), "+"/"✓" corner button, title + author below, CTA button. Row
  variant: cover, title, "by author" link, stars + avg · count, "First
  published Y", CTA + shelf split button (`✓ Want to Read | ▾`; the main
  button toggles the shown shelf, the chevron opens `<ol-book-actions>`).
  Dropped from the mock: "N editions · N ebooks" and "N of M copies available".
  Blank-cover fallback = title/author on tinted block (as in mock).
- **`<ol-book-actions>`** — the popover. Header: title + "by author" (single
  line, ellipsis). Pane 1: four shelf rows (Lucide bookmark / book-open /
  circle-check / circle-pause; current shelf marked), star rater ("Rate this
  book"), "Add to list ›", then (phase 2) Preview / Search inside / Find in a
  library / Download options. Pane 2 (slides in from right, Back slides out):
  "+ Create a list" (inlines name input + Create), "Filter lists…" input,
  checkbox rows with seed count, spinner while lists load. Optimistic updates
  + toast on failure. Fires `ol-book-state-change` so the card's ✓ / split
  button and list-view row stay in sync.
- Icons: inline Lucide `<svg>` templates in a shared `book-icons.js` module
  now; swap to `<ol-icon>` when #12955 lands.
- Logged-out "+" / shelf clicks: `queueAction()` intent cookie + redirect to
  login (site convention).

### Templates
- `macros/QueryCarousel.html` gains a `component=True` (or new
  `macros/BookCarouselSection.html`) branch that emits the Lit element with
  the same config the `.lazy-carousel` stub carries today. `subjects.html:60`
  opts in. Home page etc. keep slick until later.

## 3. Phases

1. **Data** — `/api/carousel.json` (+ tests), `/api/me/book-state.json`,
   `Ratings.get_users_ratings_of_works`. Verify list-view fields in dev Solr.
2. **Covers view** — `<ol-books-display>` + `<ol-book-card
   variant="cover">` on `<ol-carousel>`, pagination, subject page opt-in.
   Parity with today (no actions yet).
3. **Toggle + list view** — segmented control, row variant, show-more /
   collapse / see-all. Default view set in code, nothing persisted.
4. **Actions popover** — shelves + rating + user-state overlay + ✓ state on
   cards + split button in list view. Logged-out handling.
5. **Add to list** — pane 2, filter, inline create, membership, spinner.
6. **Phase 2 items** — Preview / Search inside / Find in a library /
   Download options in the popover (coordinate with `BOOK-ACTIONS-AUDIT.md`
   branch `action-button`), roll out to other QueryCarousel surfaces.

## 4. Decisions (2026-08-16)

- Name: `ol-books-display`, `view` is extensible (covers / list / grid…).
- Icons inline for now. Logged-out → login redirect. Split button in list
  view opens the same popover. Preview/Search inside/Find/Download rows are
  phase 2. No saved view preference. No edition/ebook counts, no copies
  line; keep first-publish year. Subject page only.
- Availability API stays in the data path for the CTA (see chat).

## 5. Status (2026-08-16, end of first build session)

Phases 1–5 built and committed on `carousel-actions` (7 commits on top of
297ed7c20), verified in dev on /subjects/fiction, signed in and out:

- Endpoints: `GET /books-display.json`, `GET /books-display/user-state.json`
  (`fastapi/books_display.py`, `fastapi/services/books_display.py`, tests in
  `tests/fastapi/test_books_display.py`). Dev proxy paths registered in
  `deprecated_handler.py`; `fast_web` gets `OL_COVERSTORE_PUBLIC_URL`.
- Components: `components/lit/OlBooksDisplay.js` (light DOM),
  `OlBookActions.js` (shadow), `utils/books-api.js`, `utils/book-icons.js`;
  CSS `static/css/components/ol-books-display.css` (imported by
  `ol-components.css`); jest tests `tests/unit/js/OlBooksDisplay.test.js`,
  `OlBookActions.test.js`.
- Templates: `macros/BooksDisplay.html`, `subjects.html` switched, design
  docs `design/components/books-display.html.jinja` + `book-actions.html.jinja`.

Follow-ups / known gaps:
- Icons: still inline Lucide paths; swap to `<ol-icon>` when #12955 merges.
- Phase-2 popover rows (Preview / Search inside / Find in a library /
  Download options) — coordinate with `BOOK-ACTIONS-AUDIT.md`.
- `grid` view (multi-row cover grid) — `view` enum is ready for it.
- Lists come from `/partials/MyBooksDropperLists.json`, which also renders
  (and we discard) the dropper HTML; a JSON-only lists+membership endpoint
  would be cheaper.
- `join_waitlist` renders a POST form to `/borrow/ia/{ocaid}`; unverified in
  dev (mock availability never yields waitlist state).
- Book preview modal (`data-book-preview`) isn't used for `preview` CTAs; they
  link straight to archive.org.
- Other QueryCarousel callers (home page etc.) still on slick.
