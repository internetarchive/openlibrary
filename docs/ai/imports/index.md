# Import Pipeline

Open Library's import pipeline ingests book records from external sources — Internet Archive items, partner catalogs, bulk JSONL feeds, MARC files, and more — and creates or updates Editions and Works in the OL database.

## Architecture Overview

Two separate flows share the same final step (`catalog/add_book.py`):

```
External source (JSONL/API/IA)
        │
        ▼
DataProvider / DataProviderRecord        ← olclient (openlibrary-client repo)
(JSONLProvider, PaginatedAPIProvider)
        │
        ▼
OLImportRecord  ──────────────────────── POST /api/import  ← importapi plugin
                                          POST /api/import/ia
                                          POST /import/batch/new
        │
        ▼
    add_book.load()                       ← openlibrary/catalog/add_book.py
        │
        ▼
    OL database (Work + Edition)
```

**Multi-repo layout:**

| Repo | Purpose |
|------|---------|
| `internetarchive/openlibrary-client` | `olclient/imports.py` — base classes (DataProvider, DataProviderRecord, OLImportRecord) |
| `internetarchive/openlibrary-bots` | `sources/<slug>/` — concrete source adapters |
| `internetarchive/openlibrary` | `plugins/importapi/` — HTTP endpoints; `core/batch_imports.py` — batch processing; `catalog/add_book.py` — record creation |

## Key Files

| File | What it does |
|------|-------------|
| `openlibrary-client/olclient/imports.py` | `DataProvider`, `DataProviderRecord`, `OLImportRecord`, `JSONLProvider`, `PaginatedAPIProvider` — the abstract import framework |
| `openlibrary/plugins/importapi/code.py` | HTTP handlers for `/api/import`, `/api/import/ia`. Parses JSON/MARC/RDF/OPDS, calls `add_book.load()`. |
| `openlibrary/plugins/importapi/import_edition_builder.py` | Converts parsed data into an edition dict for `add_book.load()` |
| `openlibrary/plugins/importapi/import_validator.py` | Validates edition dicts against `import.schema.json` |
| `openlibrary/core/batch_imports.py` | Processes JSONL POST to `/import/batch/new`; validates each line; accumulates into a named `Batch` |
| `openlibrary/core/imports.py` | `Batch` model — OL's internal batch queue |
| `openlibrary/catalog/add_book.py` | Final record creation: match existing editions by identifier, create or update Work/Edition, resolve authors |
| `openlibrary/schemata/import.schema.json` | Canonical JSON schema (`additionalProperties: false`). `OLImportRecord` mirrors it exactly. |
| `openlibrary-bots/sources/itan/provider.py` | Example concrete `JSONLProvider` for ITAN Global Publishing |
| `openlibrary-bots/sources/itan/record.py` | Example concrete `DataProviderRecord` for ITAN |

## How It Works

### Single-record import (`POST /api/import`)

Accepts JSON, MARC binary, MARC XML, RDF, or OPDS format. The handler in `importapi/code.py::importapi.POST()`:

1. Calls `parse_data(raw_bytes)` — dispatches to format-specific parsers
2. Normalizes to an edition dict via `import_edition_builder`
3. Calls `add_book.load(edition)` which deduplicates by identifier and writes to Infobase

The `?preview=true` query param runs the full parse + dedup without writing.

### Batch import (`POST /import/batch/new`)

Used for large partner ingestions. Accepts a JSONL file where each line is an `OLImportRecord`-shaped JSON object. Flow in `core/batch_imports.py::batch_import()`:

1. Parse each JSONL line into an `OLImportRecord` via Pydantic
2. Validate against `import.schema.json`
3. Add valid records to a named `Batch` (`{username}:{batchName}`, default `{username}:main`)
4. Return a `BatchResult` with the `Batch` and any per-line `BatchImportError`s

The `batchName` parameter (PR #12657) lets repeated calls accumulate into the same batch instead of creating orphan batches.

### Bulk adapter pattern (openlibrary-client + openlibrary-bots)

For new external data sources, the pattern is:

```python
# sources/<slug>/record.py
class MyRecord(DataProviderRecord):
    # Source-native fields as Pydantic attrs
    title: str
    authors: list[dict]
    ...
    def to_ol_import(self) -> OLImportRecord | None:
        ...  # map source fields → OLImportRecord; return None to skip

# sources/<slug>/provider.py
class MyProvider(JSONLProvider):
    SOURCE_SLUG = "myslug"          # prefix for source_records, e.g. "myslug:ID123"
    SOURCE_URL = "https://..."      # JSONL URL
    RECORD_CLASS = MyRecord
```

`DataProvider.iter_ol_records()` chains traversal + mapping, yielding only non-None results. Each record's `source_records` field (`["myslug:ID123"]`) is the deduplication key — submitting the same value twice is idempotent.

### IA import (`POST /api/import/ia`)

Specialized path for Archive.org items: accepts an `ocaid` identifier, fetches MARC from IA, converts with `catalog/marc/parse.py`, then calls `add_book.load()`. Subclasses `importapi` in `importapi/code.py`.

## API Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `POST` | `/api/import` | write access | Import one record (JSON/MARC/RDF/OPDS). Body = raw record. `?preview=true` dry-run. |
| `POST` | `/api/import/ia` | write access | Import one IA item by `ocaid`. Body = `{"identifier": "ocaid"}`. |
| `POST` | `/import/batch/new` | logged in | Batch JSONL import. `multipart/form-data` with `jsonl` file and optional `batchName`. |

**`/api/import` response:**

```json
{"success": true, "edition": {"key": "/books/OL123M", "status": "created"}}
// or
{"success": false, "error_code": "missing-required-field", "error": "..."}
```

**Required fields in every import record:**

```
title, source_records, authors, publishers, publish_date
```

`source_records` format: `["<slug>:<source-id>"]` — e.g. `["itan_technologies:BOO1017"]`. This is the deduplication key.

`publish_date` must be EDTF: `"2023"`, `"2023-04"`, `"2023-04-15"` are valid. `"April 2023"` is not.

## Adding a New Identifier Type

Before batch submission for a source with a proprietary ID (not ISBN/OCLC/LCCN):

1. Add to `openlibrary/plugins/openlibrary/config/edition/identifiers.yml`:
   ```yaml
   - label: My Source ID
     name: my_source_id     # snake_case, stable, unique
     url: https://example.com/books/@@@
   ```
2. Open a PR for the identifier. **This PR must merge and deploy before batch submission** — OL silently drops unknown identifier keys rather than erroring.
3. Verify the identifier appears on a test edition at `https://openlibrary.org/books/OL1M` before batching.

Reference: [PR #12947](https://github.com/internetarchive/openlibrary/pull/12947) — ITAN identifier (`itan_technologies`).

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

### Deduplication mismatch

`add_book.load()` matches existing editions by: ISBN-13, ISBN-10, LCCN, OCLC, then `source_records` prefix. If a record already exists under a different identifier, it will update rather than create. Use `preview=true` to see what `add_book.load()` would match before committing.

### ValidationError from OLImportRecord

`OLImportRecord` uses `extra="forbid"` — any field not in `import.schema.json` causes a `ValidationError`. Check the schema at `openlibrary/schemata/import.schema.json`. Common culprits: `ebook_access` (ITAN-specific, must be stripped in `to_ol_import()`), `cover_url` (use `cover` instead), non-EDTF dates.

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

## Open Issues and Active PRs

| PR / Issue | Status | What |
|------------|--------|------|
| [#12947](https://github.com/internetarchive/openlibrary/pull/12947) | Ready to merge | `itan_technologies` identifier |
| [#447 (bots)](https://github.com/internetarchive/openlibrary-bots/pull/447) | CI infra failures (not our code) | ITAN source adapter |
| [#12657](https://github.com/internetarchive/openlibrary/pull/12657) | Open | `batchName` param for `/import/batch/new` |
| [#12953](https://github.com/internetarchive/openlibrary/pull/12953) | Ready to merge | HTML numeric entity unescape in `normalize_import_record` |
| [#12945](https://github.com/internetarchive/openlibrary/pull/12945) | Draft | `work_identifiers` support for work-level matching |
| [#12091](https://github.com/internetarchive/openlibrary/issues/12091) | Open, 47d stale | ITAN import request — needs response |

**Identifier PR before adapter PR**: #12947 must merge and deploy before the ITAN adapter PR (#447) can submit a batch. `itan_technologies` keys are silently dropped until the identifier is registered.

## PR Review Expectations

When reviewing import-related PRs:

- **`source_records` prefix** — must be a stable slug. Once records are submitted, changing it creates duplicates. Verify the slug is documented and consistent with any registered identifier name.
- **`to_ol_import()` return None** — skipping a record is the right behavior for bad data. Verify the skip criteria are documented and not too aggressive.
- **`extra="forbid"` on OLImportRecord** — any new field in a record class must map to a field in `import.schema.json`. Check the schema before approving a new field.
- **Identifier registration** — if the PR introduces a new `identifiers` key, confirm there's a corresponding entry in `identifiers.yml` already merged, or the PR includes one.
- **Batch submission is irreversible** — `source_records` deduplication prevents exact re-imports, but bad data (wrong authors, wrong dates) that passes validation will land in OL. Require a dry-run output (`?preview=true` or local validation) in the PR description for any new source adapter.
- **Date formats** — `publish_date` must be EDTF. Reject `"Month YYYY"` formats; they are common bugs in new adapters.
