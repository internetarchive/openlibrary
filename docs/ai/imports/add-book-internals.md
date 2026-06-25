# add_book Internals

Deep reference for `openlibrary/catalog/add_book/`. This covers the orchestration in `__init__.py`, the matching algorithm in `match.py`, and the record-creation helpers in `load_book.py`. Understanding these is necessary for diagnosing import failures, duplicate records, and author-resolution issues.

## Files

| File | Role |
|------|------|
| `catalog/add_book/__init__.py` | `load()` — top-level orchestrator: validate → match → create/update |
| `catalog/add_book/load_book.py` | `build_query()`, `add_db_name()`, author resolution, `import_record_to_edition()` |
| `catalog/add_book/match.py` | `threshold_match()`, `level1_match()`, `level2_match()`, `normalize()` |

## load() Orchestration

`add_book.load(rec)` is the final common step for all import paths. Its phases:

```
normalize_import_record(rec)
  → ISBN normalization, author dedup, source_records cleanup

validate_record(rec)
  → required fields check
  → IA source_records bypass ALL validation

build_pool(rec)
  → collect candidate existing editions by ISBN, LCCN, OCLC, source_records (ia: only)
  → "pool" = list of (edition_key, edition_object) pairs

find_match(rec, pool)
  → for each candidate: threshold_match(rec, candidate)
  → returns first match or None

if match found:
    update_edition_with_rec_data(edition, rec)   ← merges new fields into existing
else:
    import_record_to_edition(rec)                ← creates new Edition + Work
```

### IA validation bypass

`validate_record()` in `__init__.py` skips ALL field validation if the record's `source_records` starts with `"ia:"`:

```python
if any(s.startswith("ia:") for s in rec.get("source_records", [])):
    return  # skip validation entirely
```

This means IA records can have missing required fields (`title`, `authors`, etc.) that would reject any other source. It also means IA records can have `extra` fields that `OLImportRecord` would reject. This bypass exists because the IA MARC pipeline predates the JSON schema validation.

### Promise item behavior

A "promise item" is an IA edition with exactly one revision (i.e., created as a placeholder) that has a MARC record. When `import_first_staged()` finds one:

```python
if existing_edition.revision == 1 and rec.get("source_records", [""])[0].startswith("marc:"):
    # Full overwrite via load_data(), not just merge
    load_data(existing_edition, rec, account=...)
```

`load_data()` replaces the edition's data wholesale rather than merging. This is intentional — a MARC record is authoritative over a stub record.

### Status lifecycle

```
pending → processing (atomic UPDATE by import_first_staged)
         → found     (matched existing edition)
         → created   (new edition created)
         → modified  (existing edition updated)
         → failed    (error_code set)
```

The `processing` state is the race guard: `import_first_staged()` uses an atomic `UPDATE ... RETURNING *` to claim items, preventing two workers from importing the same item simultaneously.

## Matching Algorithm

### Quick match (identifier-based)

`find_quick_match()` checks in order:

1. `ocaid` → `source_records` prefix `"ia:"`
2. ISBN-13 / ISBN-10
3. Non-ISBN ASIN (starts with "B")
4. `source_records` for IA items only (not general source_records)
5. OCLC / LCCN

If any match is found, it's returned immediately without running the threshold match.

### Threshold match

`threshold_match()` in `match.py` runs two scoring levels. Both use threshold = 875.

**Level 1** (fast pre-filter):

| Field | Match score | Mismatch score |
|-------|------------|----------------|
| Short title (first 25 chars) | +450 | 0 |
| LCCN | +200 | -320 |
| Publish date | +200 / -25 (±2yr) | -800 |
| ISBN | +85 | -225 |

If level 1 total ≥ 875, match is confirmed immediately (no level 2).

**Level 2** (full comparison):

| Field | Match score | Notes |
|-------|------------|-------|
| Publish date | +200 / -25 (±2yr) | -800 on mismatch |
| Country | +40 | -205 on mismatch |
| ISBN | +85 | -225 on mismatch |
| Full title | +600 (exact) / +350 (substr) / up to +500 (keyword) | |
| LCCN | +200 | -320 on mismatch |
| Page count | +50-100 | -225 if off by >10 |
| Publisher | +100 | -51 on mismatch |
| Authors | +125 (exact) / up to +74 (keyword) | -200 on mismatch |

A `DATE_MISMATCH = -800` on publish date makes it almost impossible for two records to match across different years. A single missing date when the other record has one also scores -800 (not 0).

### Author matching within threshold

`compare_author_fields()` runs two checks per author pair:
1. Exact match on `db_name` (name + dates) after `normalize()` (NFC, lowercase, strip punct)
2. Exact match on `name` (strip trailing `.`)

`compare_author_keywords()` is the fallback: word-set overlap ratio × 80, + 10 if word order matches.

### normalize() is NFC at compare time

```python
def normalize(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    s = s.replace(" & ", " and ")
    s = re_whitespace_and_punct.sub(" ", s.lower()).strip()
    return s
```

This normalizes to NFC at comparison time. In practice, `BinaryDataField.translate()` already produces NFC output (pymarc 5.3.1 outputs NFC), so stored values should be NFC. The `normalize()` call in `match.py` provides belt-and-suspenders protection. See [marc-encoding.md](marc-encoding.md) for the full encoding pipeline.

## Author Resolution

The most complex part of `load_book.py` is `author_in_db()` / `build_author_record()`. When importing a new edition, for each author in the record:

1. Look up the author by name in Infobase (exact match on `name`)
2. If found and the birth/death dates are compatible, reuse the existing author key
3. If not found, create a new `/authors/OLnA` document

### Confirmed bug: walrus operator in author dedup

In `import_record_to_edition()` around line 243:

```python
# CURRENT (buggy):
seen = set()
for a in authors:
    if key := a["key"] in seen:  # key gets bool, not string
        continue
    seen.add(key)  # adds False or True, not the author key
```

The walrus operator `:=` has lower precedence than `in`. This parses as `key := (a["key"] in seen)` — `key` is assigned the boolean result of the `in` test, not the author key string. After the first author: `seen = {False}`. For all subsequent authors: `a["key"] in seen` is `False` (the key string is not in {False}), so `key = False`, and `seen.add(False)` is a no-op. The dedup loop is broken for all records with >1 author — it always lets every author through.

**Runtime effect**: benign in most cases because downstream author-resolution logic handles actual deduplication. But it means every record with multiple authors does redundant work.

**Fix**:
```python
seen = set()
for a in authors:
    if a["key"] in seen:
        continue
    seen.add(a["key"])
```

### Confirmed bug: `existing.k` attribute access

In `load_book.py` around line 324:

```python
# CURRENT (buggy):
for k in "last_modified", "id", "revision", "created":
    if existing.k:      # accesses literal attribute named "k", not variable k
        del existing.k  # never executes — "k" is not a key in the dict
```

`existing` is a dict-like object. `existing.k` accesses the attribute literally named `"k"`, which doesn't exist. This loop was intended to strip internal metadata keys from a matched author record before re-saving, but it never does so.

**Runtime effect**: matched author records retain `last_modified`, `id`, `revision`, `created` keys when passed to `save_many()`. Depending on how Infobase handles these, this may cause update failures or phantom metadata contamination.

**Fix**:
```python
for k in "last_modified", "id", "revision", "created":
    if k in existing:
        del existing[k]
```

## normalize_import_record()

Called at the start of `load()`. Key operations:

1. **ISBN normalization**: `isbn_10` and `isbn_13` values are cleaned with `isbnlib.clean()`, invalid ones dropped. Mixed-up 10/13 ISBNs are sorted into the correct field.
2. **Author dedup**: Authors with identical `name` values are collapsed to the first occurrence. (This is a second dedup pass — the walrus bug above is in a different dedup loop.)
3. **HTML entity unescape**: PR #12953 adds `html.unescape()` to clean numeric HTML entities (`&#039;`, `&amp;`, etc.) from title/author strings that slip through from partner records.
4. **source_records cleanup**: Ensures every value is a string; drops malformed entries.

## Dead Code: re_normalize

`__init__.py` at line 72:

```python
re_normalize = re.compile("[^[:alphanum:] ]", re.UNICODE)
```

This uses POSIX character class syntax (`[:alphanum:]`) which is not valid in Python `re`. The variable is assigned but never used anywhere in the file. It would raise `re.error` if called, but since it's never called it has zero runtime effect. It is purely dead code.

## Testing add_book

```bash
# Run the full add_book test suite in Docker
docker compose run --rm home python -m pytest openlibrary/catalog/add_book/tests/ -xvs

# Test matching specifically
docker compose run --rm home python -m pytest openlibrary/catalog/add_book/tests/test_match.py -xvs

# Test a specific MARC→edition path
docker compose run --rm home python -m pytest \
  openlibrary/catalog/add_book/tests/test_add_book.py::test_workshuberthowe00racegoog -xvs
```

Key test fixtures in `tests/test_add_book.py`:
- `test_workshuberthowe00racegoog` — verifies double-import of same MARC record produces exactly one author
- `test_missing_source_records` — Nuremberg war crimes trial record (missing source_records field)
- Various ISBN dedup and author resolution cases
