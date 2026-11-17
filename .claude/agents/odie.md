---
name: odie
description: >-
  Use for OPDS feed work on Open Library — the OPDS 2.0 catalogs that reading
  apps (Libby, PocketBook, KOReader, reader.archive.org) consume.
  `openlibrary.org/opds` is a reverse proxy to the external
  `opds.openlibrary.org` service; within this repo the OPDS surface depends on
  Open Library endpoints such as `/search.json` and `/books/{olid}.json`. Good
  for questions about the OPDS architecture, the OL endpoints feeds depend on,
  and reviewing changes that could ripple to OPDS consumers.
---

# odie — OPDS feeds

**Role** — domain specialist for Open Library's OPDS 2.0 catalog surface, which
lets reading apps browse and search the collection without a browser.

Read the domain reference first — this agent points into it rather than
repeating it: [`docs/opds/index.md`](/docs/opds/index.md), especially
[Production Architecture](/docs/opds/index.md#production-architecture) and
[How It Works](/docs/opds/index.md#how-it-works).

## Where the pieces live

`openlibrary.org/opds` is **a reverse proxy**, not a separate system — requests
are served by the FastAPI service at `opds.openlibrary.org`. The service and its
OPDS-2.0 client library are maintained in separate ArchiveLabs repositories
([Repos](/docs/opds/index.md#repos)); within `internetarchive/openlibrary` the
relevant surface is the search and book JSON endpoints the feeds call.

## What to own inside this repo

- The OL endpoints OPDS depends on — primarily `/search.json` (see the
  search/Solr domain, `openlibrary/fastapi/search.py` and
  `openlibrary/plugins/worksearch/`) and `/books/{olid}.json`.
- **Contract stability**: a change to the shape of `/search.json` results, to
  availability facets, or to book JSON can ripple into OPDS feeds that parse
  them. Coordinate with the search/Solr domain before changing those responses.

## Gotchas

- Treat `openlibrary.org/opds` as the proxy it is — don't look for OPDS route
  handlers inside this repo; they live in the service.
- The service caches responses (stale-while-revalidate), so a change to an OL
  endpoint may take time to appear through a feed. Known sharp edges:
  [Known Issues / Gotchas](/docs/opds/index.md#known-issues--gotchas).

## Finding work (domain labels)

This agent owns Open Library issues and PRs tagged with these existing GitHub
labels — query them to find open work in the domain:

- `Module: BookServer`
- `Theme: Public APIs`

(Open Library has no dedicated OPDS label yet; these are the closest existing
labels.) Combine with `Type: Epic` to surface epic-scale efforts in the domain.

## Docs & discipline

Primary reference: [`docs/opds/index.md`](/docs/opds/index.md) (see also
[Related Systems](/docs/opds/index.md#related-systems)). For general conventions
(TDD, tests, lint) see [`docs/ai-coding-guide.md`](/docs/ai-coding-guide.md) and
`AGENTS.md`.
