# Import API Reference

HTTP endpoints for importing records into Open Library. See [index.md](index.md) for architecture overview.

## Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `POST` | `/api/import` | write access | Import one record (JSON/MARC/RDF/OPDS). Body = raw record. `?preview=true` dry-run. |
| `POST` | `/api/import` | write access | Bulk MARC: `?bulk_marc=true&identifier=ocaid/file:offset:len&local_id=type`. |
| `POST` | `/api/import/ia` | write access | Import one IA item by `ocaid`. `?require_marc=false` allows MARC-less path. |
| `POST` | `/import/batch/new` | logged in | Batch JSONL import. `multipart/form-data` with `jsonl` file and optional `batchName`. |
| `GET`  | `/import/preview.json` | write access | FastAPI: preview a record import without writing (PR #12745). |
| `POST` | `/import/preview.json` | write access | FastAPI: same, accepts a JSON body. |

## Single-record import (`POST /api/import`)

Accepts JSON, MARC binary, MARC XML, RDF, or OPDS format. The handler in `importapi/code.py::importapi.POST()`:

1. Calls `parse_data(raw_bytes)` — dispatches to format-specific parsers
2. Normalizes to an edition dict via `import_edition_builder`
3. Calls `add_book.load(edition)` which deduplicates by identifier and writes to Infobase

The `?preview=true` query param runs the full parse + dedup without writing.

**Response:**

```json
{"success": true, "edition": {"key": "/books/OL123M", "status": "created"}}
// or
{"success": false, "error_code": "missing-required-field", "error": "..."}
```

## Bulk MARC import (`POST /api/import?bulk_marc=true`)

The primary path for IA scanning partners (Better World Books, etc.) and the main source of usable records for archive.org's scanning metadata. Previously documented in the [OL wiki](https://github.com/internetarchive/openlibrary/wiki/data-importing#marc-records) and [public docs](https://docs.openlibrary.org/advanced/data-importing.html#marc-records).

Identifier format: `ocaid/filename:offset:length` — addresses a single MARC record within a bulk MARC item on IA.

Flow in `importapi/code.py` when `bulk_marc=true`:

1. Parse `ocaid/filename:offset:length` from the `identifier` param
2. `get_from_archive_bulk(identifier)` — HTTP range request to IA for the record bytes; also returns `next_offset`/`next_length` for sequential processing
3. `MarcBinary(data)` — parse the binary record
4. `read_edition(rec)` — convert to OL edition dict
5. `edition["source_records"] = "marc:ocaid/filename:offset:actual_length"`
6. If `local_id` param is present, extract barcode and add to edition (see below)
7. `add_book.load(edition, save=not preview)`

Response includes `next_record_offset` and `next_record_length` so callers can walk the file sequentially:

```json
{"success": true, "edition": {...}, "next_record_offset": 12345, "next_record_length": 678}
```

## `local_id` — scanning partner barcode metadata

When `bulk_marc=true`, callers can pass `local_id=<barcode_type>` (e.g. `local_id=bwbsku`). This maps to an OL `/local_ids/{name}` document containing:
- `urn_prefix` — e.g. `bwbsku`
- `id_location` — e.g. `"035$a"` — which MARC field and subfield holds the partner's barcode

The endpoint extracts those values from the MARC record and adds them to the edition:
```
edition["local_id"] = ["urn:bwbsku:ABC123", ...]
```

`local_id` presence also forces `force_import = True`, bypassing the non-monograph filter. This is how IA scanning partner records are linked back to partner inventory systems.

The `promise_batch_imports.py` script and BWB integrations use `local_id` extensively.

## Batch import (`POST /import/batch/new`)

Used for large partner ingestions. Accepts a JSONL file where each line is an `OLImportRecord`-shaped JSON object. Flow in `core/batch_imports.py::batch_import()`:

1. Parse each JSONL line into an `OLImportRecord` via Pydantic
2. Validate against `import.schema.json`
3. Add valid records to a named `Batch` (`{username}:{batchName}`, default `{username}:main`)
4. Return a `BatchResult` with the `Batch` and any per-line `BatchImportError`s

The `batchName` parameter (PR #12657) lets repeated calls accumulate into the same batch instead of creating orphan batches.

**Preferred path for new sources.** The direct single-record endpoint (`POST /api/import`) writes immediately to the catalog and is planned for deprecation in BookWorm Phase 3. New source adapters should submit through the batch queue instead.

**Trust level.** Batches submitted by non-admin users land in `status="needs_review"` and wait for manual admin approval at `/import/batch/pending`. Admin accounts bypass this and go straight to `status="pending"` (processed by ImportBot). There is currently no trusted-partner tier.

## IA import (`POST /api/import/ia`)

Specialized path for Archive.org items: accepts an `ocaid` identifier, fetches the item's per-item MARC file from IA via `get_marc_record_from_ia()` (tries `{ocaid}_meta.mrc` then `{ocaid}_marc.xml`), converts with `catalog/marc/parse.py::read_edition()`, then calls `add_book.load()`.

If `require_marc=false` is passed and no MARC file exists, falls back to the MARC-less path which uses IA metadata directly and runs `import_validator.validate()` on the result. See [validation.md](validation.md).
