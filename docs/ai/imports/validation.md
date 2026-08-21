# Import Validation

`import_validator.py` is the quality gate for the MARC-less IA import path. See [index.md](index.md) for architecture context.

## Validation Gate

`import_validator.py` is called when `POST /api/import/ia` is used with `require_marc=false` and no MARC file exists for the item. It tries two Pydantic models in order:

1. **`CompleteBook`** — requires `title + source_records + authors + publishers + publish_date`. Most records with a publisher pass here.
2. **`StrongIdentifierBook`** — requires `title + source_records + (isbn_10 | isbn_13 | lccn)`. Records with a strong identifier but no publisher pass here.

If both fail, raises `BookImportError("not-differentiable", ...)`.

**The MARC-based paths do NOT run the validator.** Records imported via `get_marc_record_from_ia()` (MARC file found) or via `bulk_marc=true` call `add_book.load()` directly after `read_edition()`.

## Required Fields (JSONL/JSON path)

```
title, source_records, authors, publishers, publish_date
```

`source_records` format: `["<slug>:<source-id>"]` — e.g. `["itan_technologies:BOO1017"]`. This is the deduplication key — submitting the same value twice is idempotent.

`publish_date` must be EDTF: `"2023"`, `"2023-04"`, `"2023-04-15"` are all valid. `"April 2023"` is not.

## Known Gap: Pre-ISBN IA items (`not-differentiable`)

Pre-ISBN public domain IA items often have title + author + date but no publisher and no ISBN/LCCN. Both `CompleteBook` and `StrongIdentifierBook` fail → `not-differentiable`.

See [#10756](https://github.com/internetarchive/openlibrary/issues/10756) for the proposed `IABook` third model:
- Requires: `title + source_records + authors + publish_date`
- Does NOT require: publishers, isbn, lccn
- Constraint: `source_records` must have `ia:` prefix (ensures only IA items use this looser model)
- Would be tried as third fallback in `validate()` after `CompleteBook` + `StrongIdentifierBook`

Workaround today: if the IA item has a MARC file (`{ocaid}_meta.mrc` or `{ocaid}_marc.xml`), the MARC path bypasses the validator entirely.
