# Cover Service

> **Status:** partial
> **Sources:** `raw/openlibrary-pages/dev_docs_api_covers.json`, code synthesis (`openlibrary/coverstore/`)
> **Last ingested:** 2026-06-27

The cover service stores, resizes, and serves book cover images and author photos. It runs as a separate service (`coverstore`) on a dedicated cover server, accessible at `covers.openlibrary.org`. It can run standalone — the main OL app calls it via HTTP but doesn't require it for core functionality.

---

## Public API

```
# Book covers
https://covers.openlibrary.org/b/{key}/{value}-{size}.jpg

# Author photos
https://covers.openlibrary.org/a/{key}/{value}-{size}.jpg
```

**Keys:** `id` (internal cover ID), `olid`, `isbn`, `oclc`, `lccn` (case-insensitive)
**Sizes:** `S` (small/thumbnail), `M` (medium/detail page), `L` (large)

```
# Same cover via different keys:
https://covers.openlibrary.org/b/id/240727-S.jpg
https://covers.openlibrary.org/b/olid/OL7440033M-S.jpg
https://covers.openlibrary.org/b/isbn/0385472579-S.jpg
https://covers.openlibrary.org/b/lccn/93005405-S.jpg
```

`?default=false` — returns 404 instead of blank image when cover not found.
`.json` suffix — returns API metadata about the cover instead of the image.

**Do not crawl the covers API.** Bulk downloads are available on archive.org.

---

## Upload Flow

OL uploads covers via `POST /{category}/upload2` on the coverstore service (wired in `openlibrary/plugins/upstream/covers.py`). The coverstore handler:

1. Receives image bytes + `olid` (Open Library ID) + category (`b` for book, `a` for author)
2. Calls `save_image(data, category, olid, author, ip, source_url)` in `coverlib.py`
3. `save_image` builds a path prefix: `YYYY/MM/DD/{olid}-{random5}.jpg`
4. Writes the original + three resized thumbnails (`-S.jpg`, `-M.jpg`, `-L.jpg`) to disk
5. Stores a DB record (cover ID, olid, filenames, dimensions, ip, source_url) via `db.new()`
6. Returns the new cover ID

**Storage path** (local disk): `{config.data_root}/localdisk/YYYY/MM/DD/{olid}-{random5}[-S|-M|-L].jpg`

Covers are bundled into archive.org items periodically (221 images per item) for bulk distribution — see `zipview_url_from_id()` in `code.py`.

**Archival has lost covers before.** In 2024 it deleted up to 5,927 covers from `covers_0014_62`. Mechanism, evidence and guards: [`archival-loss-9836.md`](archival-loss-9836.md). Safe procedure: `openlibrary/coverstore/README.md` (after #13725).

---

## Server-side fetch is allowlisted (SSRF controls)

When a cover arrives as a URL (`source_url`), not as image bytes, the Open Library server fetches
it itself. That fetch is limited to known hosts by **two independent, non-identical allowlists**:

1. **`catalog/add_book/__init__.py::check_cover_url_host()`**: an exact host match against
   `ALLOWED_COVER_HOSTS` (archive.org, books.google.com, commons.wikimedia.org,
   covers.openlibrary.org, m.media-amazon.com). It runs only on the fresh-create path
   (`load_data()`). On a mismatch it sets `cover_url = None` silently.
2. **`coverstore/utils.py::is_allowed_cover_url()`**: regex patterns, a stricter set with path
   constraints for archive.org. Coverstore's `upload`/`upload2` handlers call it via
   `download_external_image()`, which is what `add_cover()` posts to. On a mismatch, `upload2`
   returns `400 {"code": 2, "message": "Invalid URL"}`. A code comment requires the list to stay in
   sync with Internet Archive's egress proxy allowlist.

**These are deliberate SSRF controls, not a network firewall.** They were added in `9cd47f4dc`
(2025-01-11, "Imports: only process covers from supported hosts in `load()`") and `dd8b69929`
(2026-06-16, "Restrict allowed URLs for cover import/download"). Outbound HTTP from the
application works; what's gated is coverstore fetching a *caller-supplied* URL. **Widening either
list is a security regression, not a config change.** It reopens what `dd8b69929` closed, and it
needs sign-off from the owner of that control.

### What's fragile

- **Covers from non-allowlisted hosts are dropped.** Importers whose cover hosts aren't on the lists
  attach no covers. Bookdash (#10856) is the measured case: 814 works on the public search API,
  none with a cover from that import (2026-09-21). How covers from arbitrary hosts should be
  fetched is an open design decision in #13682, tracked in epic #13803.
- **A rejected URL is slow to fail.** The match/merge path (`update_edition_with_rec_data()`) has
  no host check of its own and relies on coverstore's. When coverstore rejects the URL,
  `add_cover()` retries 10 times with `sleep(2)`, up to about 20 s per record, before returning
  `None`. It does degrade gracefully (the import record isn't failed); it's just slow.

## Standalone Operation

Coverstore has its own config (`conf/coverstore.yml`), its own web server (`coverstore/server.py`), and its own DB layer (`coverstore/db.py`). It does not depend on the main OL app or Infobase at runtime.

**If covers goes down:** book and author images 404. OL itself continues to function — edition/work/author pages load, just without cover images. The main app reads cover IDs from edition records and constructs the URL client-side; it doesn't proxy through coverstore.

In local dev: set `coverstore_public_url: https://covers.openlibrary.org/` in `conf/openlibrary.yml` to pull covers from production instead of running coverstore locally.

---

## Key Files

| File | Purpose |
|------|---------|
| `openlibrary/coverstore/code.py` | HTTP handlers: `upload`, `upload2`, cover lookup |
| `openlibrary/coverstore/coverlib.py` | `save_image()`, `write_image()`, resize, path generation |
| `openlibrary/coverstore/db.py` | Cover DB layer (cover ID ↔ filename mapping) |
| `openlibrary/coverstore/server.py` | Standalone WSGI server setup |
| `openlibrary/plugins/upstream/covers.py` | OL-side upload trigger (POSTs to coverstore) |
| `conf/coverstore.yml` | Coverstore config (data_root, DB connection) |

---

## Configuration

- `coverstore_url` — internal URL OL uses to POST uploads to coverstore (set in `conf/openlibrary.yml`)
- `coverstore_public_url` — public-facing URL (default: `https://covers.openlibrary.org/`); set to production in local dev to avoid 404s
- `config.data_root` — root path where cover image files are stored on disk

---

## Dependencies

**Depends on:**
- [[infrastructure]] — runs on a dedicated cover server; local disk storage for image files; Sentry for error tracking (project #10)

**Depended on by:**
- [[core-operations]] — edition/work/author pages display covers via `covers.openlibrary.org` URLs
- [[imports]] — imported editions may include cover URLs that get fetched and stored

---

*Sources: `dev_docs_api_covers.json`, `openlibrary/coverstore/` (code synthesis) · See [[README]] · [[METHODOLOGY]]*

## Sub-documents

- [`archival-loss-9836.md`](archival-loss-9836.md): how archival lost covers from batch `covers_0014_62` in 2024, the evidence, and the guards in #13725.
- [`sub8m-census.md`](sub8m-census.md): a census of covers 7.14M–8M, the range with no archive.org copy.

Work in progress on the cover service is tracked in epic #13803.
