# Tags System — Debugging Guide

Common failure modes and how to diagnose them.

---

## CI Failures

### `ModuleNotFoundError` during test collection

```
ERROR tests/test_migrate.py -- ModuleNotFoundError: No module named 'requests'
ERROR tests/test_api_db.py  -- ModuleNotFoundError: No module named 'pydantic'
```

**Cause:** Missing dev dependencies — `requests` (used by `scripts/migrate_subjects.py`) and `pydantic` (used by `api/models.py`) must be in `[project.optional-dependencies].dev`.

**Fix:** `pip install -e ".[dev]"` — if still failing, check `pyproject.toml` to confirm `requests` and `pydantic` are listed.

---

### `AssertionError: mapping value 'Fantasy' is not a slug`

```
FAILED tests/test_vocabulary.py::TestMappingsSchema::test_all_values_are_slugs[genres-...]
AssertionError: genres/mappings.json has non-slug values: [('fantasy fiction', 'Fantasy')]
```

**Cause:** `mappings.json` values must be slugs (`"fantasy"`), not display names (`"Fantasy"`). This often happens when new mappings are added by hand without checking the contract.

**Fix:**
```bash
python3 scripts/normalize_mapping_values.py --dry-run   # preview
python3 scripts/normalize_mapping_values.py             # apply
pytest tests/test_vocabulary.py                          # verify
```

---

### `AssertionError: <type>/mappings.json has duplicate keys`

```
FAILED tests/test_vocabulary.py::TestMappingsSchema::test_no_duplicate_keys[literary_themes-...]
AssertionError: literary_themes/mappings.json has duplicate keys
assert 64 == 63
```

**Cause:** The same key appears twice in a `mappings.json`. Python's `json.load` silently uses the last value, but the test catches it by comparing the raw key list vs. the set.

**Fix:** Open the file and search for the duplicated key. Remove the earlier (incorrect) entry, keeping the one with the right slug value.

---

### `AssertionError: values that are not valid slugs in vocabulary.json`

```
FAILED tests/test_vocabulary.py::TestMappingsSchema::test_values_reference_valid_slugs[audience-...]
AssertionError: audience/mappings.json values that are not valid slugs in vocabulary.json:
  [('juvenile fiction', 'Juvenile'), ...]
```

**Cause:** The mapping value (`"Juvenile"`) doesn't match any `slug` field in `vocabulary.json`. Either the slug was renamed, or the value was written as a display name instead of a slug.

**Fix:** Check `tag_types/<type>/vocabulary.json` for the correct slug, update `mappings.json`.

---

## Classification Bugs

### Subject not being classified

```python
from tags import load_all
tt_map = {tt.name: tt for tt in load_all()}
result = tt_map["genres"].classify({"subjects": ["My mystery novel"]})
# returns []
```

**Diagnosis steps:**

1. **Check normalize output** — the mapping lookup is case-insensitive and strips whitespace, but also NFC-normalizes Unicode:
   ```python
   from tags.tag_type import normalize
   print(normalize("My mystery novel"))   # "my mystery novel"
   # is this key in mappings.json?
   ```

2. **Check the mappings file directly:**
   ```python
   import json
   m = json.load(open("tag_types/genres/mappings.json"))
   print(m.get("my mystery novel"))   # None = not mapped
   ```

3. **Check if the type has a classify.py plugin** — if so, the plugin runs INSTEAD of the default mapping lookup for subjects it handles. Read `tag_types/<type>/classify.py` to see if your subject would be caught or fall through.

4. **Check droppable.json** — if the subject appears in `tag_types/droppable.json`, it's silently discarded before classification:
   ```python
   import json
   droppable = set(json.load(open("tag_types/droppable.json")))
   print(normalize("My mystery novel") in droppable)
   ```

---

### Wrong slug returned from classify()

If `classify()` returns a slug that doesn't match `vocabulary.json`, the most likely cause is a `classify.py` plugin returning a hardcoded display name instead of a slug.

**Check:** `TagMatch.value` must always be a slug. Verify the plugin:

```python
result = tt.classify({"subjects": ["Children: Grades 1-2"]})
print(result[0].value)   # should be "children", not "Children"
```

**Fix:** Update the `classify.py` to return the slug from `vocabulary.json` (`"children"`, `"young-adult"`, etc.) not the display name.

---

### Conflict resolution not working (literary_form)

If a work with both `"Historical fiction"` and `"biography"` subjects gets classified as `fiction` when you expect `nonfiction`:

The `literary_form/classify.py` conflict resolution fires only when **both** `fiction` AND `nonfiction` signals appear. If only one side matches, there's no conflict to resolve — the single match wins.

To inspect:
```python
from tags import load_all
tt = {t.name: t for t in load_all()}["literary_form"]
result = tt.classify({"subjects": ["Historical fiction", "Biography"]})
print([(m.value, m.reason) for m in result])
```

Strong nonfiction override signals: `biography`, `biographies`, `biographical`, `autobiography`, `memoir`, `memoirs`, `autobiographical`, `autobiographies`.

---

## Backfill Script Issues

### Phase 1 scan produces no output

```bash
python3 scripts/backfill_genre_tags.py scan --dump ol_dump.txt.gz
# (no output)
```

**Diagnosis:**
- Confirm the dump format: OL dumps are tab-separated with 5 fields — `type\tkey\trevision\tlast_modified\tjson`. Records with fewer than 5 fields are skipped.
- Confirm the file is uncompressed if not `.gz`: plain `.txt` files use `open()` not `gzip.open()`.
- Run on a small sample: `head -10000 dump.txt | python3 scripts/backfill_genre_tags.py scan --dump /dev/stdin`

### Phase 2 live mode rejected by OL

```
requests.exceptions.HTTPError: 403 Client Error
```

**Cause:** The OL account lacks write permission, or the login cookie was rejected.

**Fix:** Confirm the credentials work at `https://openlibrary.org/account/login` in a browser. The account must have write access to Works. **Do not run live mode without @mekarpeles sign-off.**
