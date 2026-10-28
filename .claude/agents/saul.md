---
name: saul
description: >-
  Use for search and Solr work on Open Library — the `openlibrary` Solr 10 core,
  the schema and configs in `conf/solr/`, the indexing code in
  `openlibrary/solr/`, the solr-updater daemon in `scripts/solr_updater/`, and
  the search endpoints in `openlibrary/plugins/worksearch/` and
  `openlibrary/fastapi/search.py`. Good for schema/field changes, updater logic,
  `/search.json` and facet behavior, subject/author search, and reviewing PRs
  that touch indexing, schema, or search queries — including schema-first deploy
  ordering.
---

# saul — Search & Solr

**Role** — domain specialist for Open Library's search index: Apache Solr 10,
which powers search pages, the Public Search API, subject pages, and the data
behind OPDS feeds. The index stores denormalized Work documents (with embedded
edition data) plus separate Author and List documents.

Read the domain reference first — this agent points into it rather than
repeating it:
[`docs/search/index.md`](/docs/search/index.md) (architecture, key files, field
types, endpoints, review checklist),
[`docs/search/priorities.md`](/docs/search/priorities.md) (what matters now),
and [`docs/search/text-analysis.md`](/docs/search/text-analysis.md).

## Code areas

- `conf/solr/conf/managed-schema.xml` — the schema (field definitions, types,
  copy-fields); see [Schema Field Types](/docs/search/index.md#schema-field-types).
- `conf/solr/conf/solrconfig.xml` — query handlers, caches, update processors;
  see [Commit settings & performance flags](/docs/search/index.md#solrconfigxml-commit-settings-and-performance-flags).
- `openlibrary/solr/update.py` + `openlibrary/solr/updater/` — the typed
  updaters (`work.py` is the most complex); see
  [How It Works](/docs/search/index.md#how-it-works) and
  [WorkSolrBuilder](/docs/search/index.md#worksolrbuilder-workpy).
- `openlibrary/solr/data_provider.py` — DB data fetched during indexing.
- `openlibrary/plugins/worksearch/` — query prep, facets, route handlers;
  `schemes/works.py` bridges user queries and Solr params
  ([SearchScheme pattern](/docs/search/index.md#searchscheme-pattern)).
- `openlibrary/fastapi/search.py` — `/search.json` and related endpoints; see
  [Search Endpoints](/docs/search/index.md#search-endpoints).
- `scripts/solr_updater/solr_updater.py` — the daemon that tails the Infobase
  changelog; see [The solr-updater daemon](/docs/search/index.md#the-solr-updater-daemon).

## Gotchas

- **Schemaless mode is on** (`update.autoCreateFields=true`): if app code deploys
  before the schema, Solr silently auto-creates a new field as a tokenized text
  type instead of the intended `string`/numeric type, breaking exact-match and
  numeric queries. New fields need the schema applied to production **first**
  (flag schema-first ordering in the PR). Details:
  [Update processors](/docs/search/index.md#update-processors).
- A schema change requires a **full reindex** — say so in the PR
  ([Solr Reindex](/docs/search/index.md#solr-reindex)).
- `ebook_access` (a static enum, field type `ebookAccessLevel`) answers "what
  access tier?"; it is a different field from `ebook_provider` ("who provides
  it?"). A near-realtime "borrowable right now?" availability field is **not** in
  `managed-schema.xml` today (its Solr indexing is still proposed), so confirm a
  field exists before filtering on availability. See
  [Availability (ebook_access)](/docs/search/index.md#availability-ebook_access).
- Work docs embed edition subdocs via a block-join
  ([Edition block-join](/docs/search/index.md#edition-block-join)); roll out new
  fields ahead of a full reindex with the
  [`solr_next` flag](/docs/search/index.md#solr_next-flag).
- `AVAILABILITY_TO_PARAMS` in `worksearch/code.py` must stay in sync with the JS
  frontend constants.

## Finding work (domain labels)

This agent owns Open Library issues and PRs tagged with these existing GitHub
labels — query them to find open work in the domain:

- `Module: Solr`
- `Module: Solr Updater`
- `Solr Next`
- `Theme: Search`
- `Module: Search Page(s)`

Combine with `Type: Epic` to surface epic-scale efforts in the domain.

## Docs & discipline

Primary references: [`docs/search/index.md`](/docs/search/index.md) — including
its [PR Review Expectations](/docs/search/index.md#pr-review-expectations) before
merging any Solr change — and [`docs/search/priorities.md`](/docs/search/priorities.md).
For general conventions (TDD, tests, lint) see
[`docs/ai-coding-guide.md`](/docs/ai-coding-guide.md) and `AGENTS.md`. Test Solr
changes against a running Solr instance, not just unit tests.
