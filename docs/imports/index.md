# Import Pipeline

Open Library's import pipeline ingests book records from external sources — Internet Archive items, partner catalogs, bulk JSONL feeds, MARC files, and more — and creates or updates Editions and Works in the OL database.

## Architecture Overview

Three flows share the same final step (`catalog/add_book.py`):

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

IA bulk MARC file (ocaid/filename:offset:length)
        │
        ▼
POST /api/import?bulk_marc=true&identifier=ocaid/file:offset:len&local_id=bwbsku
        │
        ▼
get_from_archive_bulk() → MarcBinary → read_edition() → add_book.load()
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
| `openlibrary/plugins/importapi/code.py` | HTTP handlers for `/api/import`, `/api/import/ia`. Parses JSON/MARC/RDF/OPDS, calls `add_book.load()`. Handles `bulk_marc` + `local_id` path. |
| `openlibrary/plugins/importapi/import_edition_builder.py` | Converts parsed data into an edition dict for `add_book.load()` |
| `openlibrary/plugins/importapi/import_validator.py` | Quality gate: validates edition dicts against `CompleteBook` and `StrongIdentifierBook` Pydantic models |
| `openlibrary/fastapi/importapi.py` | FastAPI handlers for `GET/POST /import/preview.json` (added in PR #12745) |
| `openlibrary/core/batch_imports.py` | Processes JSONL POST to `/import/batch/new`; validates each line; accumulates into a named `Batch` |
| `openlibrary/core/imports.py` | `Batch` model — OL's internal batch queue |
| `openlibrary/catalog/add_book/__init__.py` | Final record creation: match existing editions by identifier, create or update Work/Edition, resolve authors |
| `openlibrary/catalog/get_ia.py` | `get_marc_record_from_ia()` — fetches per-item MARC from IA; `get_from_archive_bulk()` — reads binary MARC from bulk files by offset/length |
| `openlibrary/catalog/marc/marc_binary.py` | Parses binary MARC records (`MarcBinary`) |
| `openlibrary/catalog/marc/marc_xml.py` | Parses MARC XML records (`MarcXml`) |
| `openlibrary/catalog/marc/parse.py` | `read_edition()` — converts a MARC record to an OL edition dict |
| `openlibrary/schemata/import.schema.json` | Canonical JSON schema (`additionalProperties: false`). `OLImportRecord` mirrors it exactly. |
| `openlibrary-bots/sources/itan/provider.py` | Example concrete `JSONLProvider` for ITAN Global Publishing |
| `openlibrary-bots/sources/itan/record.py` | Example concrete `DataProviderRecord` for ITAN |
| `scripts/manage-imports.py` | ImportBot: processes pending batch items in a configurable multiprocessing pool; runnable locally via `compose.near-prod.yaml` (PR #12999) |
| `compose.near-prod.yaml` | Near-prod compose override — adds `importbot` service and Solr replication; use with `COMPOSE_FILE="compose.yaml:compose.override.yaml:compose.near-prod.yaml"` |

## Sub-docs

| Topic | Doc |
|-------|-----|
| API endpoints, bulk MARC, `local_id`, batch import | [api.md](api.md) |
| Validation gate, required fields, `not-differentiable` | [validation.md](validation.md) |
| Adding a new source adapter, identifier registration | [adding-sources.md](adding-sources.md) |
| Debugging, known limitations | [debugging.md](debugging.md) |
| MARC8 → Unicode pipeline, NFC normalization, pymarc internals | [marc-encoding.md](marc-encoding.md) |
| `add_book.load()` internals: matching, scoring, author resolution | [add-book-internals.md](add-book-internals.md) |

## Open Issues and Active PRs

| PR / Issue | Status | What |
|------------|--------|------|
| [#13017](https://github.com/internetarchive/openlibrary/pull/13017) | Open, CI green | NFC normalization in `marc_binary.py` `BinaryDataField.translate()` |
| [#12947](https://github.com/internetarchive/openlibrary/pull/12947) | Ready to merge | `itan_technologies` identifier |
| [#447 (bots)](https://github.com/internetarchive/openlibrary-bots/pull/447) | CI infra failures (not our code) | ITAN source adapter |
| [#12657](https://github.com/internetarchive/openlibrary/pull/12657) | Open | `batchName` param for `/import/batch/new` |
| [#12953](https://github.com/internetarchive/openlibrary/pull/12953) | Ready to merge | HTML numeric entity unescape in `normalize_import_record` |
| [#12945](https://github.com/internetarchive/openlibrary/pull/12945) | Draft | `work_identifiers` support for work-level matching |
| [#12091](https://github.com/internetarchive/openlibrary/issues/12091) | Open | ITAN import request |
| [#12655](https://github.com/internetarchive/openlibrary/issues/12655) | Open, not ready for action | Epic: BookWorm — modernize import pipeline |
| [#10756](https://github.com/internetarchive/openlibrary/issues/10756) | Open, proposal posted | `not-differentiable` for pre-ISBN IA items; proposed `IABook` validator |
| [#7236](https://github.com/internetarchive/openlibrary/issues/7236) | Fixed in PR #12999 | Local dev ImportBot now runnable via `compose.near-prod.yaml` |
| [#8542](https://github.com/internetarchive/openlibrary/issues/8542) | Open | Batch import documentation gap |

**Identifier PR before adapter PR**: #12947 must merge and deploy before the ITAN adapter PR (#447) can submit a batch. `itan_technologies` keys are silently dropped until the identifier is registered.
