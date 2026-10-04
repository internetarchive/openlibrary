# Adding Import Sources

How to add a new external data source to the Open Library import pipeline. See [index.md](index.md) for architecture context.

## Bulk Adapter Pattern

For new external data sources, define two classes in `openlibrary-bots/sources/<slug>/`:

```python
# sources/<slug>/record.py
class MyRecord(DataProviderRecord):
    # Source-native fields as Pydantic attrs
    title: str
    authors: list[dict]
    # ...
    def to_ol_import(self) -> OLImportRecord | None:
        # Map source fields → OLImportRecord; return None to skip this record
        ...

# sources/<slug>/provider.py
class MyProvider(JSONLProvider):
    SOURCE_SLUG = "myslug"          # prefix for source_records, e.g. "myslug:ID123"
    SOURCE_URL = "https://..."      # JSONL URL
    RECORD_CLASS = MyRecord
```

`DataProvider.iter_ol_records()` chains traversal + mapping, yielding only non-None results. Each record's `source_records` field (`["myslug:ID123"]`) is the deduplication key — submitting the same value twice is idempotent.

For paginated APIs or OPDS feeds, override `iter_records()` in a `PaginatedAPIProvider` or `OPDSProvider` subclass rather than using `JSONLProvider`.

Reference examples:
- `openlibrary-bots/sources/itan/record.py` — `ITANRecord(DataProviderRecord)`
- `openlibrary-bots/sources/itan/provider.py` — `ITANProvider(JSONLProvider)`

See the full end-to-end walkthrough in `pm/workflows/import_workflow.md`.

## Registering a New Identifier Type

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

## PR Review Expectations

When reviewing import-related PRs:

- **`source_records` prefix** — must be a stable slug. Once records are submitted, changing it creates duplicates. Verify the slug is documented and consistent with any registered identifier name.
- **`to_ol_import()` return None** — skipping a record is the correct behavior for bad data. Verify the skip criteria are documented and not too aggressive.
- **`extra="forbid"` on OLImportRecord** — any new field in a record class must map to a field in `import.schema.json`. Check the schema before approving a new field.
- **Identifier registration** — if the PR introduces a new `identifiers` key, confirm there's a corresponding entry in `identifiers.yml` already merged, or the PR includes one.
- **Batch submission is irreversible** — `source_records` deduplication prevents exact re-imports, but bad data (wrong authors, wrong dates) that passes validation will land in OL. Require a dry-run output (`?preview=true` or local validation) in the PR description for any new source adapter.
- **Date formats** — `publish_date` must be EDTF. Reject `"Month YYYY"` formats; they are common bugs in new adapters.
- **`local_id` / bulk MARC** — if a PR touches the `bulk_marc` path or `local_id` handling, verify that the `/local_ids/{name}` document exists for the partner barcode type and that `id_location` points to the correct MARC subfield.
