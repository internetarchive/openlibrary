# First Edits: execution plan

*Branch `FirstEdits`. Revised 2026-09-22. Everything in this repo; no sidecar, no new tables, no Solr changes, no scheduler. Phase 1 is a click-through proof of concept of the user experience with nothing saved; phase 2 wires evidence and answers; phase 3 is the gate.*

**Status (2026-09-22):** phase 1 is built and walkable on the dev site. Package `openlibrary/first_edits/`, pages in `openlibrary/plugins/openlibrary/contribute.py`, templates under `contribute/`, stylesheet `page-contribute.css`. Dev seeding recipe in `dev-setup.md`. Open items from the walkthrough: a `/volunteer` page link still needs adding on the site (it is a wiki page, not a template), and the three-week sequence below is now the checklist for polish rather than a build order.

## 1. Constraints this plan honors

| Constraint | How |
|---|---|
| Everything in the Open Library repo | A small Python package, `openlibrary/first_edits/`. Bookie is reference only. |
| Minimal external calls | Phase 1: none required (fixture evidence for a demo set, optional live Google Books). Phase 2: Google Books and Library of Congress, both with parsers already in this repo. |
| No tables, no schema | Phase 1 saves nothing. Phase 2 uses memcache for evidence and site store documents for answers and progress. |
| No Solr changes | Existing `readinglog` and `trending` sorts; existing `publisher_facet`. |
| No scheduler | Evidence on demand with a cache; an optional warm-up script only prefills it. |
| No edits or queue writes in phase 1 | Submit renders a receipt from the posted values and nothing else. |

## 2. Phase 1: the walkthrough

Goal: a person with a beta-tester account can click from `/contribute/start` through orientation, practice, the list, three real books, the wizard, the receipt, and a mocked status page, on the dev site, inside the real site shell, on a phone. Nothing is written anywhere.

### What is live and what is fixture

| Thing | Phase 1 source |
|---|---|
| Book title, cover, authors, edition line, edition count | Live, local Open Library database |
| Sibling editions and their value counts per field | Live, `work.get_sorted_editions()` counted in Python |
| Your shelves list | Live, the user's reading log |
| Popular list | Fixture: a demo set of about twelve well-known editions with a "readers" number copied from production reading-log counts |
| External evidence (what Google Books and the Library of Congress say) | Fixture: JSON per demo edition, converted once from Bookie's golden snapshots into the two-source shape. Optional flag to call Google Books live for editions without a fixture |
| Practice tasks and verdicts | Fixture, three books |
| Answers, skips, progress | Not saved. A `sessionStorage` list of task keys makes chaining and "already done" work within one browser session |
| Receipt and status page | Rendered from posted values plus fixture states (pending, accepted, declined with note) |

### Simplifications this phase takes

1. **No FastAPI in phase 1.** With fixture evidence there is nothing slow to load progressively, so the list page is fully server-rendered by web.py page handlers. The row-evidence and publisher-facet endpoints move to phase 2. (Section 5 explains why pages are web.py regardless.)
2. **No store documents, no memcache.** Evidence and demo data are JSON files in `openlibrary/first_edits/fixtures/`. Progress is client-side session storage.
3. **Publisher suggestions come from siblings only.** The "Something else" field suggests spellings used by other editions of the work, with counts, from the live sibling scan. The Solr facet merge waits for phase 2.
4. **Three fields, three playbooks:** language, page count, publisher. Subtitle waits.
5. **Popular is the demo set.** The demo set is resolved at runtime by ISBN against the local database, so it shows whichever demo editions exist locally. Seed them with shelfie by ISBN query. The Solr popularity sort is a one-line swap in phase 2.
6. **Practice reuses the task template** with a verdict step appended, not its own screens.
7. **The gate becomes fixture-backed pages, not a separate wireframe document.** The receipt, the "Your suggestions" status page with its three states, and one librarian review row are built as real Jinja templates fed by fixture data. They are the wireframes, they are part of the click-through, and phase 3 reuses them. Nothing in them can be clicked into an action.
8. **Gate on `/usergroup/beta-testers`,** which already exists with a model check; no new group.
9. **Quick wins is a checkbox** on the list ("only sure things"), filtering on the fixture verdicts.

### What gets built

- `openlibrary/first_edits/`
  - `scope.json`, `scope.py`: per field enabled, modes, minimum evidence level, playbook id. A JSON file from day one so the librarian conversation can change it without code.
  - `playbooks.py`: per field, the question per mode, convention notes with guideline links, link-out templates keyed by ISBN, answer labels, traps.
  - `sources.py`: explainer copy for Google Books, Library of Congress, and "other editions on Open Library".
  - `compare.py`: five comparators ported from Bookie (year, pages with tolerance, publisher token overlap, language exact, subtitle similarity). Used in phase 1 for sibling counts and the practice verdict; used in phase 2 on live sources.
  - `evidence.py`: builds the per-field evidence view (OL value, source values with match method and URL, verdict, suggestion, meter sentence) from a normalized input. In phase 1 the input is a fixture; in phase 2 it is live sources. Same function.
  - `siblings.py`: live sibling scan and value counts.
  - `fixtures/demo_books.json`, `fixtures/evidence/<isbn>.json`, `fixtures/practice/*.json`, `fixtures/status.json`.
- `openlibrary/plugins/openlibrary/contribute.py`: page handlers copied from `design.py`. Routes: `/contribute/start`, `/contribute/practice` (GET and POST), `/contribute` (with `view=popular|shelves` and `quick=1`), `/contribute/task/OL…M/<field>` (GET and POST), `/contribute/task/OL…M/<field>/done`, `/contribute/mine` (fixture status page), `/contribute/review-preview` (one fixture librarian row, linked from the start page's "who checks it" card).
- `openlibrary/templates/contribute/*.html.jinja` and `openlibrary/macros/contribute/*.html.jinja`: start, practice, index, task, done, mine, review, and macros for the book header, evidence table, sibling chips, meter, link-outs, answer chooser. Each renders with no arguments. Gettext with named placeholders; regenerate the POT.
- `static/css/page-contribute.css`: mobile-first, single column, sticky answer block, evidence rows stacked under the small breakpoint, two columns above the large one.
- A few lines of JS: reveal the free-text field on "Something else", sibling-count suggestions under it, session-storage progress, `ol-popover` for explainers.
- Tests: scope validation, comparators, evidence sentences, template compile.

### Sequence, three weeks

| Week | Milestone |
|---|---|
| 1 | Package, scope, playbooks for three fields, evidence builder on fixtures, demo set seeded locally. Start page and list page render inside the site shell. |
| 2 | Wizard for all three fields with live book data and sibling counts, link-outs, pre-filled note, receipt, chaining via session storage. |
| 3 | Practice with verdicts, status page and review row from fixtures, mobile pass, deep link on the volunteer page. Walk three Slack volunteers through it and take notes. |

### Exit test

Log in as the dev user in the beta-testers group on a phone, open the start link, do the practice task, open a demo book from Popular, answer publisher with the sibling suggestion, land on the receipt, take the next field on the same book, then open "Your suggestions" and see the three fixture states. No request writes to the database.

## 3. Phase 2: live evidence and saved answers

Same pages, real data underneath. Nothing new in the UI beyond a "couldn't check right now" row state.

- `sources/google_books.py`: lift `fetch_google_book` and `process_google_book` from `scripts/affiliate_server.py` into an importable module (they already return publishers, date, pages, subtitle from an ISBN).
- `sources/loc.py`: one SRU request by ISBN with `recordSchema=marcxml`, parsed by the existing `MarcXml` and `read_edition` in `openlibrary/catalog/marc/`.
- `evidence.get_evidence(edition_key)`: live sources through the same builder, wrapped in `memcache_memoize` with a seven-day timeout. Two-source rules: both agree by ISBN is Strong, one source is Fair, disagreement is Needs judgment and no task.
- Popular from Solr with the existing `readinglog` sort, `trending` as fallback. Demo set retired.
- FastAPI, `openlibrary/fastapi/contribute.py`: `GET /contribute/evidence/OL…M.json` so list rows load progressively; `GET /contribute/publishers.json` from a `facet.prefix` query on `publisher_facet` (not a stored field, so it mirrors `openlibrary/plugins/worksearch/publishers.py`), merged with sibling counts.
- Answers become site store documents (type `first_edits_answer`, key from edition, field and username, indexed properties for edition, field, username, status), the way the workbench branch stores requests. Progress becomes a per-user store document like `User.save_preferences`. The status page reads real documents and drops the fixtures.
- Optional `scripts/first_edits/warm_cache.py` to prefill memcache before an alpha session.
- Subtitle playbook, if librarians want it.

## 4. Phase 3: the gate

Reads the answer documents. Review tab with strong, judgment and not-sure groups; decline reason picker mapped to guidelines; accept-with-edit; the apply path through the normal edition save with a comment and its own action string; first-acceptance email. If the team prefers the merge queue as the home for proposals, moving the documents there is a data migration, not a schema change. Details stay in the design report.

## 5. Why pages are web.py and JSON is FastAPI

Every HTML page on the site today, including new ones like `/developers/design` and `/authors`, is served by a web.py page handler that renders a Jinja template, and web.py's delegate wraps it in the site shell: the Templetor head and navigation, the CSS and JS bundles, flash messages, the language switcher, the logged-in user.

FastAPI routers on master return JSON or redirects. Their one HTML response, the borrow interstitial, is deliberately rendered bare. The reason is mechanical: the shell's head and nav read `web.ctx` (`ctx.user`, `ctx.path`, `ctx.cssfile`, flash messages), and FastAPI requests populate ContextVars instead; `openlibrary/core/layout.py` notes the bridge is still to be done.

Two honest options: pages in web.py and JSON in FastAPI (proven, what this plan assumes, and the CLAUDE.md rule against new web.py endpoints is aimed at APIs), or a two-to-three-day spike to build the layout context from ContextVars and shim the head and nav so FastAPI can return a full page. Worth doing as platform work; not worth blocking the walkthrough on.

## 6. Decisions to bring to librarians during phase 1

- The first field list and modes. Proposed: language, page count, publisher, then subtitle.
- Publisher convention wording: imprint on the book, not the parent company.
- Whether two agreeing sources earn the word "Strong", or whether siblings must agree too.
- The wait estimate to print on the receipt before real data exists.

## 7. Risks

- **A walkthrough can mislead.** Fixture evidence is always clean. Put one demo book in the set whose sources disagree so the "Needs judgment" state is seen, and one with a single source so "Fair" is seen.
- **Dev data.** Seed the demo set and a reading log with shelfie before any session; otherwise the lists are empty.
- **Two sources is thin for non-English books** (phase 2). Adding a national library later is one file in `sources/`.
- **Google Books quota** (phase 2). Keyless quota is per IP; cache aggressively, add the key config if needed.
- **Store documents as a queue** (phase 2). Fine at alpha volume; the migration path into the merge queue is written above.
