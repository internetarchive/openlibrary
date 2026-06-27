# Genre / subject browse

Design notes for the subject-page browse experience and the path toward a
controlled **genre** taxonomy. This is a living document — update it as the
phases land.

## Goal

Turn subject pages from a flat category listing into a guided, visual
"genre dashboard" that helps a reader decide **what to read next**, not just
browse every book with a tag. The guiding principle (borrowed from the best
book/media sites): _fewer, better, interpreted paths_ — and explain **why**
each book is here.

## Phase 1 — shipped

Branch: `claude/genre-taxonomy-browse-9ohm0f`.

What a `/subjects/<topic>` page renders now:

- **`<ol-subject-hero>`** — a cover-wall masthead built from the subject's top
  covers, with the heading, a stat strip (works / readable-now / years in
  print), and search slotted on top. (`openlibrary/components/lit/OLSubjectHero.js`)
- **`<ol-carousel>`** — the book rows use the web-component carousel instead of
  the legacy Slick carousel, threaded through a `web_component` flag on
  `QueryCarousel` → `RawQueryCarousel` → `books/custom_carousel.html`, with
  load-more preserved (`openlibrary/plugins/openlibrary/js/ol-carousel/`).
- **Interpreted rails** — `macros/SubjectRail.html`: each row is a title +
  optional badge + a one-line "why this is here" caption above a carousel for
  an arbitrary query. Generic subjects get six differentiated intent paths
  (Trending / Most loved / Want-to-read / Short standalones / Fresh /
  Read-now) instead of redundant popularity sorts.
- **Featured editorial layer** — `openlibrary/plugins/worksearch/subject_config.py`
  holds hand-curated content (tagline, prose description, a "choose your
  flavor" subgenre map, and curated collections) for flagship subjects
  (science fiction, fantasy, romance, mystery). Attached in `subjects.py`'s
  `GET`. Every other subject falls back to the generic rails.
- **`macros/SubjectFlavors.html`** — the subgenre map grid.
- **`macros/SubjectAuthors.html`** — top authors as photo cards.

Phase-1 collections are backed by **real search queries**; the curation (which
collections exist, their framing, the subgenre map, the prose) is the authored
value-add. Award rails (Hugo/Nebula/Edgar) lean on award **subject tags** in
the catalog and are illustrative where coverage is thin — they can later be
replaced with hand-picked work lists.

### Known limitations to revisit

- Award/curated rails depend on subject-tag coverage; thin tags → thin rails.
- Subgenre links in the flavor map point at `/subjects/<slug>`; some slugs may
  be sparse until the genre vocabulary (below) exists.
- The flavor map and curated collections are only as good as the hardcoded
  config; they do not scale to every subject by design.

## Phase 2 — the "reading feel" unlock (proposed)

The single highest-leverage next step. Open Library **already collects** the
reader-feel metadata that powers mood/pace/constraint browsing — it is just not
queryable.

### The hidden asset: observations

`openlibrary/core/observations.py` defines a controlled, user-contributed
taxonomy and already aggregates it per work via `get_observation_metrics()`:

- **Pace** (slow / medium / fast)
- **Mood** (multi-select)
- **Length**
- **Content Warnings**
- **Audience** (children / YA / adult …)
- **Genres**, **Difficulty**, **Style**, **Purpose**, **Fictionality**, **Features**

This is OL's StoryGraph-style "reading feel" layer. The problem: it lives in
the Postgres `observations` table and is **not indexed in Solr**, so you can
fetch it for one book but cannot browse, filter, or sort a subject by it.

### The work

1. **Index observation aggregates into Solr.** During work indexing
   (`openlibrary/solr/updater/work.py`), pull the per-work observation metrics
   and emit faceted fields, e.g. `pace_facet`, `mood_facet` (multi-valued),
   `content_warning_facet`, `audience_facet`, `length_facet`. Only emit a value
   above a small confidence threshold (e.g. ≥ N respondents and a clear
   plurality) to avoid noise from a single tagger.
   - Data source: `get_observation_metrics(work_olid)` in `core/observations.py`.
   - Decide refresh strategy: recompute on work re-index; observations change
     independently of works, so a periodic re-index or an observation-write
     hook that marks works dirty is needed.
2. **Expose the new facets in the work search scheme**
   (`openlibrary/plugins/worksearch/schemes/works.py`): add the fields to the
   facet list and `field_name_map` so `mood:cozy`, `pace:fast`,
   `content_warning:*` work in queries.
3. **Light up the UI for free.** Because rails are just queries, new mood/pace
   paths become one-line `SubjectRail` calls, and the "choose your flavor" grid
   can mix subgenre links with mood/pace queries:
   - "Cozy & low-stakes" → `subject_key:fantasy mood:cozy`
   - "Fast & funny" → `subject_key:fantasy pace:fast mood:funny`
   - "No heavy content warnings" → `subject_key:... -content_warning:*`
   - Vibe chips on book cards from `get_observation_metrics` (data already there).
4. **Content-warning filtering.** We already blur `content_warning:cover`
   covers via carousel `safe_mode`; extend that to an opt-in filter/hide.

### Why this is the right next step

It converts ~70% of the "ideal genre page" wishlist (mood, pace, length,
constraints, vibe chips) from impossible into a templating exercise on the
Phase-1 infrastructure, with no new product surface to design — only an
indexing project.

## Phase 3 — taste & trust (research bets)

Sequence only after Phase 2 proves the genome:

- **Taste-matched shelves** — "loved by readers who share your 5-star books."
  Needs per-reader vectors (a recommender project).
- **Reader-segment ratings** — ratings split by reader type instead of one
  average.
- **Read-alikes by axis** — similar premise / mood / prose / pacing.
- **Series confidence** — complete vs ongoing, reading order, cliffhangers.
  (We index `series_name` but not completion/order state.)

## Toward a controlled genre vocabulary

The original project goal. Genres should be a small, curated, **hierarchical**
vocabulary (cyberpunk under science fiction, cozy under fantasy) — distinct
from the open-ended, scraped `subject` facet. The `/type/tag` model
(`tag_type`, descriptions, disambiguation) is the natural backing store. The
Phase-1 "choose your flavor" map is a hand-built preview of that hierarchy;
formalizing it would let the subgenre links, faceting, and parent/child
roll-up be data-driven rather than hardcoded.
