---
name: impa
description: >-
  Use for import-pipeline work on Open Library — ingesting book records from
  Internet Archive items, partner catalogs, JSONL feeds, and MARC into Works and
  Editions. Endpoints in `openlibrary/plugins/importapi/` and
  `openlibrary/fastapi/importapi.py`, batch processing in
  `openlibrary/core/batch_imports.py`, final record creation in
  `openlibrary/catalog/add_book/`, MARC parsing in `openlibrary/catalog/marc/`,
  and the validation gate in
  `openlibrary/plugins/importapi/import_validator.py`. Good for import
  endpoints, batch imports, MARC encoding, new source adapters, and reviewing
  import PRs.
---

# impa — Import pipeline

**Role** — domain specialist for Open Library's import pipeline: it ingests book
records from external sources and creates or updates Editions and Works.

## Architecture

Three flows share the same final step, `add_book.load()`:

- Parsed records (`DataProvider` / `DataProviderRecord` → `OLImportRecord`) hit
  `POST /api/import`, `POST /api/import/ia`, or `POST /import/batch/new`.
- Bulk IA MARC files are read by offset/length and parsed into editions.
- All paths converge on `openlibrary/catalog/add_book/` → the OL database.

The framework spans multiple repos: base classes live in `openlibrary-client`
(`olclient/imports.py`), concrete source adapters in `openlibrary-bots`
(`sources/<slug>/`), and the endpoints, batch processing, `add_book`, and MARC
parsing in this repo.

## Code areas

- `openlibrary/plugins/importapi/code.py` — `/api/import`, `/api/import/ia`;
  parses JSON/MARC/RDF/OPDS and calls `add_book.load()`.
- `openlibrary/plugins/importapi/import_validator.py` — the quality gate
  (validates edition dicts against `CompleteBook` / `StrongIdentifierBook`
  models).
- `openlibrary/fastapi/importapi.py` — the import-preview endpoints.
- `openlibrary/core/batch_imports.py` — JSONL batch processing into a named
  `Batch`; `openlibrary/core/imports.py` holds the `Batch` model/queue.
- `openlibrary/catalog/add_book/__init__.py` — final record creation: match
  existing editions by identifier, create/update Work + Edition, resolve
  authors.
- `openlibrary/catalog/marc/` — `marc_binary.py`, `marc_xml.py`, and `parse.py`
  (`read_edition()`).
- `openlibrary/schemata/import.schema.json` — the canonical import JSON schema.

## Gotchas

- **Register the identifier before the adapter.** An import carrying an
  unregistered identifier type has those keys silently dropped — the identifier
  must be registered and deployed before a source adapter submits a batch.
- MARC records go through a MARC8 → Unicode pipeline with NFC normalization;
  encoding bugs surface here.
- Many OL records are incomplete — handle missing/null fields gracefully.

## Shared discipline

Reference: `docs/imports/` (index, api, validation, adding-sources, debugging,
marc-encoding, add-book-internals). For general conventions (TDD, tests, lint)
see `docs/ai-coding-guide.md` and `AGENTS.md`.
