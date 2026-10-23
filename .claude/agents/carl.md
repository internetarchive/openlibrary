---
name: carl
description: >-
  Use for cover-service work on Open Library — the `coverstore` service
  (`openlibrary/coverstore/`) that stores, resizes, and serves book covers and
  author photos at covers.openlibrary.org, the upload path wired in
  `openlibrary/plugins/upstream/covers.py`, and the SSRF allowlists that gate
  server-side fetches of caller-supplied cover URLs
  (`openlibrary/coverstore/utils.py::is_allowed_cover_url` and
  `openlibrary/catalog/add_book/__init__.py::check_cover_url_host`). Good for
  upload/serve/resize logic, cover URL handling, and reviewing coverstore PRs —
  especially anything that touches those allowlists.
---

# carl — Cover service

**Role** — domain specialist for Open Library's cover service, `coverstore`: it
stores, resizes, and serves book cover images and author photos at
`covers.openlibrary.org`. It runs as a **separate service** that can operate
[standalone](/docs/cover-service/README.md#standalone-operation); the main app
calls it over HTTP but doesn't require it for core functionality.

Read the domain reference first — this agent points into it rather than
repeating it: [`docs/cover-service/README.md`](/docs/cover-service/README.md).

## Public API shape

`https://covers.openlibrary.org/{b|a}/{key}/{value}-{size}.jpg` — `b` for book
covers, `a` for author photos; keys are `id`, `olid`, `isbn`, `oclc`, `lccn`;
sizes are `S`, `M`, `L`. Full contract: [Public API](/docs/cover-service/README.md#public-api).

## Code areas

- `openlibrary/coverstore/` — the service: `coverlib.py` (`save_image`: writes
  the original plus S/M/L thumbnails and a DB record), `code.py` (routes,
  archive.org bundling), `utils.py` (URL allowlist). See
  [Upload Flow](/docs/cover-service/README.md#upload-flow) and
  [Key Files](/docs/cover-service/README.md#key-files).
- `openlibrary/plugins/upstream/covers.py` — the OL-app side that posts uploads
  to coverstore (`/{category}/upload2`).
- `openlibrary/coverstore/README.md` — the service's own guide and safe
  operational procedures.

## Gotchas

- **The SSRF allowlists are a security control, not config.** When a cover
  arrives as a URL (not bytes), the server fetches it, and that fetch is limited
  to known hosts by **two independent, non-identical allowlists**:
  `check_cover_url_host()` (exact host match, on the fresh-create path) and
  `is_allowed_cover_url()` (regex, stricter, used by the coverstore upload
  handlers). **Widening either list is a security regression** — it reopens what
  those controls deliberately closed and needs sign-off from the control's owner.
  See [Server-side fetch is allowlisted (SSRF controls)](/docs/cover-service/README.md#server-side-fetch-is-allowlisted-ssrf-controls).
- Covers from non-allowlisted hosts are **silently dropped**, and a rejected URL
  fails slowly ([What's fragile](/docs/cover-service/README.md#whats-fragile)).
- **Archival has lost covers before** — bulk-archival steps have deleted covers.
  Follow the safe procedure in `openlibrary/coverstore/README.md` before running
  any archival/deletion step; the mechanism, evidence, and guards are recorded in
  [`docs/cover-service/archival-loss-9836.md`](/docs/cover-service/archival-loss-9836.md).

## Finding work (domain labels)

This agent owns Open Library issues and PRs tagged with this existing GitHub
label — query it to find open work in the domain:

- `Module: Cover Service`

Combine with `Type: Epic` to surface epic-scale efforts in the domain.

## Docs & discipline

Primary references: [`docs/cover-service/`](/docs/cover-service/README.md) and
`openlibrary/coverstore/README.md`. For general conventions (TDD, tests, lint)
see [`docs/ai-coding-guide.md`](/docs/ai-coding-guide.md) and `AGENTS.md`. Route
any security finding (e.g. anything touching the allowlists) to a maintainer
privately first — never in a public comment.
