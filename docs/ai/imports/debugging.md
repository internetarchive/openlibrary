# Import Pipeline Debugging

Debugging guide and known limitations. See [index.md](index.md) for architecture context.

## Known Limitations

These are current-state constraints that affect new source adapters. Most are addressed by longer-term roadmap work — but every new adapter must account for them.

### Cover URL allowlist

`catalog/add_book/__init__.py` has a hardcoded allowlist:

```python
ALLOWED_COVER_HOSTS = (
    "archive.org", "books.google.com", "commons.wikimedia.org",
    "covers.openlibrary.org", "m.media-amazon.com"
)
```

If a source's cover URL host is not on this list, `check_cover_url_host()` returns `False` and the cover is silently set to `None` — the record imports fine but cover-less. No error or warning is raised. Most partner CDNs are not on the list. Options per source: (a) expand the allowlist via PR, (b) fetch and re-host the image on IA/covers.openlibrary.org before submitting, or (c) accept cover-less imports.

### `ol import` CLI does not exist

The `ol import --provider ...` command described in `pm/workflows/import_workflow.md` is aspirational — it is not implemented in `openlibrary-client/olclient/cli.py`. Batch submission today requires a Python script that calls `DataProvider.iter_ol_records()` directly and POSTs the results to `/import/batch/new`.

### Identifier registration requires a deploy

Adding a new identifier type to `identifiers.yml` requires a PR merge followed by the weekly OL deploy cycle. Until the deploy, any `identifiers` key in submitted records that references the new type is **silently dropped** — no error, no warning. Design implication: either (a) block batch submission until after the identifier PR deploys, or (b) submit records without the `identifiers` field and run an update pass afterward.

### Local dev ImportBot does not run

`scripts/manage-imports.py` (ImportBot) is not wired into the Docker Compose dev setup. Records submitted to `/import/batch/new` locally will queue but never be processed. To test the full queue→process loop, either call `add_book.load()` directly in tests or test against a staging environment. Tracked in [#7236](https://github.com/internetarchive/openlibrary/issues/7236).

---

## Debug Playbook

### Record not appearing after import

```bash
# Check the import API response directly
curl -s -X POST http://localhost:8080/api/import \
  -H "Content-Type: application/json" \
  -d '{"title":"Test","source_records":["test:1"],"authors":[{"name":"A"}],"publishers":["B"],"publish_date":"2020"}' \
  | python3 -m json.tool

# Preview mode — parse + dedup without writing
curl -s -X POST "http://localhost:8080/api/import?preview=true" \
  -H "Content-Type: application/json" \
  -d '@record.json' | python3 -m json.tool
```

### `not-differentiable` error from `/api/import/ia`

Returned when `require_marc=false` is used and the item's metadata doesn't satisfy either `CompleteBook` or `StrongIdentifierBook`. Common for pre-ISBN public domain items with title + author + date but no publisher or ISBN/LCCN.

Workaround: if the item has a MARC file (check `{ocaid}_meta.mrc` or `{ocaid}_marc.xml` in the IA metadata), the MARC path bypasses the validator entirely. See [validation.md](validation.md) and [#10756](https://github.com/internetarchive/openlibrary/issues/10756).

### Deduplication mismatch

`add_book.load()` matches existing editions by: ISBN-13, ISBN-10, LCCN, OCLC, then `source_records` prefix. If a record already exists under a different identifier, it will update rather than create. Use `preview=true` to see what `add_book.load()` would match before committing.

### Cover not appearing on imported edition

If an edition was created but has no cover, the cover URL was probably from a non-allowlisted host. Check whether the source URL's domain is in `ALLOWED_COVER_HOSTS` (see [Known Limitations](#cover-url-allowlist)):

```bash
python3 -c "
from urllib.parse import urlparse
ALLOWED = ('archive.org','books.google.com','commons.wikimedia.org','covers.openlibrary.org','m.media-amazon.com')
url = 'https://your-cover-url.example.com/image.jpg'
host = urlparse(url).hostname
print('ALLOWED' if host in ALLOWED else f'BLOCKED — {host} not in allowlist')
"
```

No error is raised. The `cover` field is silently set to `None` in `add_book.load()`.

### ValidationError from OLImportRecord

`OLImportRecord` in `openlibrary-client` uses `extra="forbid"` — any field not in `import.schema.json` causes a `ValidationError`. `DataProviderRecord` subclasses use `extra="allow"` to absorb source-specific fields, but only fields listed in `OLImportRecord` survive the `to_ol_import()` conversion. Common culprits: `ebook_access` (ITAN-specific, must be stripped in `to_ol_import()`), `cover_url` (use `cover` instead), non-EDTF dates.

### Batch: records not accumulating

If repeated POSTs to `/import/batch/new` create orphan batches rather than accumulating, pass `batchName` in the form data. Without it, the default is `{username}:main` (after PR #12657 merges — previously a SHA hash).

### Testing locally

```bash
# Single record via API (Docker must be running)
curl -s -X POST "http://localhost:8080/api/import" \
  -H "Content-Type: application/json" \
  --cookie "session=..." \
  -d @sample_record.json

# Run import-related tests
docker compose run --rm home python -m pytest openlibrary/plugins/importapi/tests/ -xvs
docker compose run --rm home python -m pytest openlibrary/tests/core/test_batch_imports.py -xvs
docker compose run --rm home python -m pytest openlibrary/catalog/add_book/tests/ -xvs

# Test a DataProvider locally (from openlibrary-bots)
cd ~/Projects/openlibrary-bots
python3 -c "
from sources.itan.provider import ITANProvider
for i, rec in enumerate(ITANProvider().iter_ol_records()):
    print(rec.model_dump(exclude_none=True))
    if i >= 4: break
"
```
