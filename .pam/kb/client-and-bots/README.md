# Open Library Client (ol-client)

> **Status:** partial
> **Sources:** `raw/openlibrary-docs-ai/imports/` (index, adding-sources, debugging), code synthesis (`openlibrary/api.py`)
> **Last ingested:** 2026-06-27
> **Repo:** `github.com/internetarchive/openlibrary-client` (not checked out locally — see note below)

Two distinct "client" concepts exist in OL:
1. **`openlibrary-client`** — external Python library on PyPI; provides the `DataProvider` framework used by import adapters. Lives in its own repo.
2. **`openlibrary/api.py`** — internal `OpenLibrary` client class inside the main OL repo; used for scripting against the OL API.

---

## openlibrary-client (external repo)

**Package:** `olclient` · **PyPI:** `openlibrary-client`
**Key module:** `olclient/imports.py`

### DataProvider Framework

The base classes for building import adapters:

```python
# olclient/imports.py
class DataProviderRecord:
    # Pydantic model for source-native data
    # extra="allow" — absorbs unknown source fields
    def to_ol_import(self) -> OLImportRecord | None:
        # Map source fields → OLImportRecord; return None to skip

class OLImportRecord:
    # Pydantic model mirroring import.schema.json
    # extra="forbid" — unknown fields raise ValidationError
    source_records: list[str]  # e.g. ["myslug:ID123"] — dedup key

class DataProvider:
    def iter_ol_records(self) -> Iterator[OLImportRecord]:
        # Chains iter_records() + to_ol_import() + filters None

class JSONLProvider(DataProvider):
    # Reads JSONL from a URL; yields records line by line
    SOURCE_SLUG = "..."       # stable prefix for source_records
    SOURCE_URL = "..."        # JSONL endpoint
    RECORD_CLASS = ...        # your DataProviderRecord subclass

class PaginatedAPIProvider(DataProvider):
    # For paginated REST APIs or OPDS feeds
```

### Adding a New Import Source

Define two classes in `openlibrary-bots/sources/<slug>/`:

```python
# sources/<slug>/record.py
class MyRecord(DataProviderRecord):
    title: str
    authors: list[dict]
    def to_ol_import(self) -> OLImportRecord | None: ...

# sources/<slug>/provider.py
class MyProvider(JSONLProvider):
    SOURCE_SLUG = "myslug"
    SOURCE_URL = "https://..."
    RECORD_CLASS = MyRecord
```

`DataProvider.iter_ol_records()` → batch POST to `/import/batch/new`.

**⚠️ Before batching:** Register any new identifier type in `openlibrary/plugins/openlibrary/config/edition/identifiers.yml` and deploy — OL silently drops unknown identifier keys.

### OLImportRecord constraints

- `extra="forbid"` — any field NOT in `openlibrary/schemata/import.schema.json` causes `ValidationError`
- Fields that seem obvious but fail: `ebook_access` (ITAN-specific, must be stripped in `to_ol_import()`), `cover_url` (use `cover` instead), non-EDTF dates
- `source_records` prefix is the deduplication key — once set, changing it creates duplicates

### ol CLI

`olclient/cli.py` provides a CLI. The `ol import --provider ...` subcommand is **aspirational** — it is not implemented in the current version of the CLI. Batch submission requires a Python script calling `DataProvider.iter_ol_records()` directly.

### Schema

`olclient/schemata/` holds JSON Schema files for OL types (edition, work, author). These are the import validation targets.

---

## openlibrary/api.py (internal client)

An `OpenLibrary` class inside the main OL repo, used for scripting and internal tooling:

```python
ol = OpenLibrary("https://openlibrary.org")
ol.login("username", "password")
# or:
ol.autologin()  # reads ~/.olrc

# Read
page = ol.get("/books/OL7M")
results = ol.query(type="/type/work", limit=10)

# Write
ol.save("/books/OL7M", data, comment="fix title")
ol.save_many([...], comment="bulk update")

# Import
ol.import_ocaid("adventuresoftomsa00twaiuoft")
ol.import_data(json_string)

# Search
ol.search("great gatsby", limit=5)
```

**Authentication:**
- `login(username, password)` → POSTs to `/account/login`, stores session cookie
- `autologin()` → reads `~/.olrc` (INI format, section = hostname, e.g. `[openlibrary.org]`)

**`~/.olrc` format:**
```ini
[openlibrary.org]
username = joe
password = secret

[0.0.0.0:8080]
username = joe
password = admin123
```

`OPENLIBRARY_RCFILE` env var overrides the default `~/.olrc` path.

**Marshal/unmarshal:** `api.py` includes `marshal()` / `unmarshal()` to convert between Python objects and OL's Infogami JSON format (e.g., datetime objects ↔ `{"type": "/type/datetime", "value": "..."}`, string references ↔ `{"key": "..."}` dicts).

---

## Key Files

| File | Purpose |
|------|---------|
| `olclient/imports.py` | `DataProvider`, `DataProviderRecord`, `OLImportRecord` — import framework (external repo) |
| `olclient/cli.py` | CLI wrapper — `ol import` aspirational, not implemented |
| `olclient/schemata/` | JSON Schema for OL edition/work/author types |
| `openlibrary/api.py` | Internal `OpenLibrary` client class + marshal/unmarshal helpers |
| `openlibrary/schemata/import.schema.json` | Canonical import schema; `OLImportRecord` mirrors it exactly |
| `openlibrary/plugins/openlibrary/config/edition/identifiers.yml` | Registered identifier types — must be present before batch submission |

---

## Common Confusion

- **Two different "clients":** `openlibrary-client` (external package, `olclient`) is the import framework. `openlibrary/api.py` is a separate simpler internal client in the main repo. They are not the same codebase.
- **`ol import` CLI doesn't work:** Documented in pm/workflows as the import workflow, but `olclient/cli.py` doesn't implement it. Use `DataProvider.iter_ol_records()` directly.
- **`extra="forbid"` on OLImportRecord:** Adding a field to your `DataProviderRecord` doesn't automatically make it importable — it must also be in `import.schema.json`.

---

## Note on Local Availability

The `openlibrary-client` repo is not checked out at `/Users/internetarchive/Projects/`. Code synthesis above is from `raw/openlibrary-docs-ai/imports/` (AI-compiled docs) + knowledge of the public interface. To add ground-truth detail: `git clone github.com/internetarchive/openlibrary-client` and add to cq for a Unit A ingest.

---

## Dependencies

**Depends on:**
- [[imports]] — `DataProvider` pattern feeds `add_book.load()` via import API
- [[core-operations]] — `openlibrary/api.py` talks to OL's web.py/Infogami API

**Depended on by:**
- [[imports]] — all import adapters in `openlibrary-bots` use `DataProvider` as base class

---

*Sources: `imports/index.md`, `imports/adding-sources.md`, `imports/debugging.md`, `openlibrary/api.py` · See [[README]] · [[METHODOLOGY]]*
