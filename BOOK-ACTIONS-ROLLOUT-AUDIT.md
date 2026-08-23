# Rolling `ol-shelf-button` / `ol-book-actions` into the product

Audit of what it would take to make the new book-action components the standard
way readers shelve, rate, and list books — and what breaks if we do it naively.

Branch audited: `feat/shelf-button-book-actions` (components) plus
`feat/books-display-kit` (the carousel kit, draft PR #13381).

---

## 1. What we have

Three components, all already exported from `openlibrary/components/lit/index.js`,
which `site/footer.html` loads as a module on **every page**. So the bundle cost is
paid the moment the components PR merges; rolling them out onto surfaces adds no
further JS weight (~8KB gzipped, minified, for all three plus `books-api.js`).

| Component | Role |
|---|---|
| `ol-book-actions` | The popover: four shelf rows, a 5-star rating, and a sliding "Add to list" pane with filter + inline create. Caller supplies the trigger via `slot="trigger"`. |
| `ol-shelf-button` | The trigger, in two shapes: `split` (bordered, labelled, main half toggles Want to Read) and `icon` (round bookmark for floating over cover art). |
| `ol-book-cover` | Cover art with an `overlay` slot, which is where the icon variant lives. |

**Contract worth preserving.** Both controls are stateless — they never write their
own `shelf`/`rating`, they emit `ol-book-state-change` (optimistically, and again
with the old value on failure) and the owning surface applies it. That is what keeps
two cards for the same work in step, and it makes the optimistic write and its
rollback one code path. Any host we add them to has to own that state.

**Data plumbing.** `GET /reading-state.json?work_ids=OL1W,OL2W` (FastAPI, new on this
branch) returns `{shelves: {...}, ratings: {...}}` for the signed-in reader. Server-
rendered surfaces can skip it and set `shelf`/`rating` directly; client-rendered ones
(carousels, partial-loaded results) need the batch call.

---

## 2. What is in production today

The legacy stack, all rendered through `openlibrary/templates/my_books/dropper.html`:

- `my_books/primary_action.html` — the "Want to Read" `<form>` button
- `my_books/dropdown_content.html` — shelf forms, list checkboxes, "Use this Work", create-list modal
- `my_books/check_ins/check_in_prompt.html` — "Read on <date>" + edit, rendered as a **sibling** of the dropper
- `macros/StarRatings.html` — a separate five-star form, not part of the dropper
- `js/my-books/MyBooksDropper.js` + `lists/ShowcaseItem.js` — behaviour and the sidebar list chips

Where it appears:

| Surface | Template | Dropper | Separate stars |
|---|---|---|---|
| Work / edition page | `macros/databarWork.html` → `lists/widget.html` | yes | yes (with schema.org RDFa) |
| Search results | `macros/SearchResultsWork.html` (`work_search.html`) | yes (async) | byline only |
| List pages | `type/list/view_body.html` | yes | — |
| Author works | `type/author/view.html` | yes | — |
| Trending | `trending.html` | yes | — |
| Reading log | `account/reading_log.html` | yes (own pages) | yes |
| Loan history | `account/loan_history.html` | — | yes |
| Fulltext results | `macros/FulltextResults.html` | yes | — |
| Author page sidebar | `type/author/view.html` → `lists/widget.html` | yes (author seed, no work) | — |
| **Carousels** | `books/custom_carousel_card.html` | **none** | **none** |

One useful de-risking fact: the legacy primary-action button is server-rendered
`disabled` and enabled by JS. There is **no no-JS baseline to protect** — a Lit
component is no regression on that axis.

---

## 3. Feature-parity gaps

Ranked by how much they hurt.

### 3.1 Blockers — fix before any production surface

**i18n.** Every string in both components is an English default in `DEFAULT_LABELS`.
Nothing on the server passes `labels`. OL is heavily translated; shipping this to a
real surface ships English to every locale. The patterns to fix it already exist in
the codebase — the work is picking the right one and wiring it. See §5.1.

**Check-in destruction, silently.** `process_work_bookshelves` calls
`BookshelvesEvents.delete_by_username_and_work` whenever a book comes off a shelf
(`openlibrary/plugins/openlibrary/api.py:159`). The legacy dropper confirms first —
*"Removing this book from your shelves will delete your check-ins for this work.
Continue?"*. `ol-shelf-button`'s main half and the popover's shelf rows both remove
without asking. On any surface where a reader has check-ins, this is quiet data loss.

**`{"error": "Invalid bookshelf"}` returns HTTP 200.** `books-api.js`'s `request()`
only throws on `!response.ok`, so a rejected shelf write resolves successfully, the
optimistic UI sticks, and the reader believes it saved. This is exactly the failure
shape behind the dev-only "Invalid bookshelf" bug already in the notes. Needs a body
check, not just a status check.

### 3.2 Real gaps — surface-dependent

| Capability | Legacy | New | Matters on |
|---|---|---|---|
| Check-in prompt ("Read on 3 May") | yes | no | work page, search, list, reading log |
| Confirm before deleting check-ins | yes | **no** | everywhere signed-in |
| "Use this Work" — edition vs work seed for lists | yes | no (always uses `book.key`, the work) | edition pages |
| Sidebar list showcase chips update on add | yes | no | work page |
| Author / subject seeds (list-only, no work) | yes | no | author page sidebar |
| Create list with a description | yes | name only | minor |
| `data-ol-link-track` analytics | yes | no | all — see §5.3 |
| Login-intent preservation | yes | yes (`queuePendingAction`) | — |
| schema.org `reviewRating` RDFa | yes (`StarRatings.html`) | no | **work page SEO** |

The check-in gap is smaller than it looks: `check_in_prompt.html` is already a
sibling of the dropper, found by `document.querySelector('#check-in-container-<olid>')`.
A ~30-line adapter that listens for `ol-book-state-change` and opens/hides the
existing prompt gets us parity without touching check-in code.

### 3.3 Scaling concerns

- `/partials/MyBooksDropperLists.json` returns **every seed key of every one of the
  user's lists** (`get_list_data` → `list_items`). A reader with a 5,000-book list
  ships that whole array. The new component prefetches it on the *first popover open*
  and shares one promise page-wide, which is no worse than the legacy dropper — but
  it will now fire on surfaces that never loaded it before.
- `/reading-state.json` caps at 100 work ids (`MAX_STATE_WORKS`); over that is a 422.
  Long carousels or a 100+ item list page need chunking.
- A page with both the legacy dropper and a new popover has **two list caches**
  (`myBooksStore` and the module-level `_listsPromise`). ~~Toggling a list in one
  leaves the other stale.~~ **Wired** (author-page rollout): the only cross-talk
  that matters is list *creation* — membership state doesn't cross seeds — and
  both sides now announce it with an `ol-list-created` DOM event. The popover
  dispatches it (bubbling) after its inline create; `CreateListForm` dispatches
  it on `document`; each side folds the other's creations into its own cache.
  This also fixed a sibling bug: `_onCreateSubmit` replaced the lists object, so
  already-loaded sibling popovers never saw a newly created list.

---

## 4. Status

**Shipped:** search results, PR #13400 (stacked on #13399). Then **trending and
author works** — both were the predicted flag flip plus the page-level
`get_patrons_reading_states` batch, with one addition each worth recording:
trending can list the same work twice (`shelf-buttons.js` already keeps
duplicate buttons in step), and the author page is the first **mixed page** —
its sidebar keeps the legacy author-seed dropper — which forced wiring the
list-cache bridge described in §3.3.

`SearchResultsWork` gained a `use_shelf_button` flag; `work_search.html` turns it
on. Everything else still renders `my_books/dropper`.

### What made search results the right first surface

Not that it was lowest-risk in the abstract — carousels are — but that it is
**not user-cached**. `render_cached_macro` only applies to macros wrapped in
`CacheableMacro`, so shelf, rating and check-in state server-render as
attributes with nothing to hydrate. All six `SearchResultsWork` callers share
that property; carousels do not.

One thing server-rendering does *not* solve, which cost a real bug: the buttons
are stateless by contract, so the page still has to apply what they report.
`js/my-books/shelf-buttons.js` is that owner. Server-rendering supplies only the
opening state.

### Remaining surfaces

| Surface | What it still needs |
|---|---|
| **Reading log** | `hide-rating` — the only surface where `macros.StarRatings` is a real input. Shelf is implicit from the page (`/want-to-read`), so it needs no shelf query at all, and `ratings[idx]` is already batched. Owner-only (`include_dropper=(bookshelf_id and owners_page)`). |
| **List pages** | Edition seeds render `doc = seed.document`, so `doc.key` is `/books/OL…M` and `work-key` needs `doc.works[0].key`. Also `decorations=remove_item_link()` already offers remove-from-this-list, which the popover's list pane would then offer twice on one row. |
| **Fulltext results** | **Deliberately deferred — needs its own look.** It passes `doc['edition']`, a search-index edition doc with no work key readily available, so it likely falls into the dropper's `old-style-lists` path today: lists only, **no shelves at all**. Adding shelves there is a feature change, not a swap, and wants a Solr work-key lookup. |
| **Author page sidebar** | Not a candidate. `lists/widget.html` renders a dropper for an *author* seed with no work key; `ol-book-actions` is work-shaped. |
| **Carousels** | Blocked on a state-hydration story. Cards are `CacheableMacro`-cached across users and lazy-loaded via `CarouselCardPartial`, so `user-key`/`shelf`/`rating` cannot be baked in. `ol-books-display` (draft PR #13381) was going to own this but is not merged; the alternative is the existing Templetor card plus a hydration controller. |
| **Work / edition page** | Last. Showcase chips, the edition-vs-work list seed, mobile modal links, and `StarRatings.html`'s schema.org RDFa (keep it — the popover runs with `hide-rating`). |

## 5. Component API

### 5.1 Label plumbing — settled: pattern B

Three patterns exist in the codebase:

| Pattern | Used by | Shape |
|---|---|---|
| **A.** Individual `label-*` attributes | `ol-pagination` (5), `ol-carousel` (4), `ol-scorecard` (7), `ol-read-more` (2) | Lit, one instance per page |
| **B.** One JSON blob on the instance | search-bar trigger, `ReturnForm`, `login`, `history` | self-describing instance |
| **C.** One `render_once()` blob per page, queried by JS | `list-i18n-strings`, `reading-log-i18n-strings` | many instances share one blob |

**B was chosen.** 23 label keys, 773 bytes of JSON, 1,233 HTML-escaped. The
obvious objection — repeating it per card — does not survive measurement:

| | raw | gzipped |
|---|---|---|
| 20 instances | +24.9KB | **+627B** |
| 120 instances | +149KB | **+1.6KB** |

Every instance carries byte-identical JSON, so after the first each repeat costs
about **3 bytes** on the wire. B also needs no component change (`labels: { type:
Object }` already JSON-parses the attribute) and composes with async-loaded
markup, which C does not.

Implemented as `my_books/book_actions_i18n.html`, rendered once per request in
`work_search.html` and passed down. `ol-book-cover` has one label (`by %(name)s`)
and is genuinely pattern A territory.

### 5.2 Added in #13400

- `hide-rating` — drops the popover's stars.
- `has-check-in` — a removal would destroy something, so ask first.
- `get_patrons_reading_states()` — batches shelf, rating and last-read-date.
- `trackEvent` for the Lit bundle, keeping the `ReadingLog|*` names.

### 5.3 Still worth doing

- **`seed-key`.** `_seedKey` is still hardcoded to `book.key`, so an edition page
  cannot add the edition to a list and "Use this Work" has nowhere to live.
  Blocks list pages and the book page.
- **A leaner list-membership endpoint.** `/partials/MyBooksDropperLists.json`
  returns every seed key of every one of the user's lists.

## 6. Bugs found and fixed in #13400

1. `bookshelves.json` answers a rejected write with 200 and an `error` key;
   `books-api`'s status-only check let a failed write look like a save.
2. Removing a shelf deletes the work's check-ins server-side; the components did
   not warn, the dropper did. Now warns only when there is one to lose.
3. ILE's selection guard ignores clicks inside `a, button, details`, but a click
   in a shadow root retargets to the host — so opening the popover also selected
   the row for the librarian toolbar.
4. Signed out, the button resumed on the book's page after login rather than the
   page the reader was on.
5. Nothing applied the state the (deliberately stateless) buttons reported, so
   the label stopped matching the server after the first change.

Bugs 3 and 5 lived in the seam between server-rendered attributes and a component
that upgrades later — invisible to unit tests, which is why
`tests/e2e/shelf-button.spec.ts` exists.

## 7. Open questions

1. Should list membership move off `/partials/MyBooksDropperLists.json` to a
   leaner endpoint (`{key, name, count, contains}` for one seed) before this
   reaches higher-traffic surfaces?
2. A signup interstitial for logged-out readers ("sign up to save this") instead
   of a bare login bounce. Cheaper after the migration than before it — one
   change in `_onLoggedOut` rather than one per surface.
3. On the reading log, removing a book from the shelf you are looking at leaves a
   row that is now lying. Left as-is for now; treatment to be explored.
4. Does `ol-books-display` (#13381) land before carousels are attempted, or do
   carousels go direct on the Templetor card with a hydration controller?
