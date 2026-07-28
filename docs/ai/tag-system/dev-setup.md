# Tags System — Dev Setup

How to run the tags classification system locally for development and testing.

---

## Repo

```bash
git clone https://github.com/Open-Book-Genome-Project/tags.git
cd tags
```

## Install

```bash
pip install -e ".[dev]"
# Installs: pytest, pytest-cov, requests, pydantic + the tags package itself
```

## Run Tests

```bash
pytest
# Expected: 200+ passed, 1 skipped (the skipped test requires a live OL connection)
```

Targeted subsets:

```bash
pytest tests/test_vocabulary.py   # data contract checks (slug values, no duplicate keys, etc.)
pytest tests/test_loader.py       # tag type loading, registry, priority ordering
pytest tests/test_migrate.py      # SubjectClassifier unit tests
pytest tests/test_api_db.py       # SQLite FTS5 search index
pytest tests/test_tag_type.py     # TagType dataclass, TagMatch, normalize(), default_classify()
```

## Directory Layout

```
tag_types/
  <type>/
    vocabulary.json     ← canonical slugs (controlled types only)
    vocabulary.md       ← human-readable companion
    mappings.json       ← subject string → slug lookup
    classify.py         ← optional pattern-matching plugin
    README.md           ← decision rules for this type
    proposals.md        ← proposal history (accepted / rejected / deferred)
tags/
  __init__.py           ← load_all() — classification engine entry point
  tag_type.py           ← TagType dataclass, TagMatch, default_classify()
scripts/
  migrate_subjects.py   ← SubjectClassifier — classifies OL work subjects
  normalize_mapping_values.py ← converts Title Case mapping values to slugs
  backfill_genre_tags.py      ← two-phase script to write genre:slug prefixes to OL
tests/
```

## CLI

```bash
# Classify a single work by OL ID
tags analyze OL82563W

# Show unmapped subjects across the corpus (requires a dump file)
tags unmapped --dump ol_dump_works_latest.txt.gz | head -50
```

## Classifying a Work Programmatically

```python
from tags import load_all

tag_types = load_all()
work = {"subjects": ["Fantasy fiction", "Pirates--Fiction", "Dragons"]}

for tt in tag_types:
    matches = tt.classify(work)
    if matches:
        print(f"{tt.name}: {[m.value for m in matches]}")
# genres: ['fantasy']
# literary_form: ['fiction']
```

## Data Contract (key rules)

- `mappings.json` keys must be lowercase + NFC-normalized (`normalize()` from `tags.tag_type`)
- `mappings.json` values must be slugs (lowercase, hyphenated) — NOT display names
- `vocabulary.json` slugs and `mappings.json` values must agree
- No duplicate keys in any JSON file
- `vocabulary.json` and `vocabulary.md` must be kept in sync

Run `pytest tests/test_vocabulary.py` after any data change to verify the contract.

## Normalizing Mapping Values

If a `mappings.json` has Title Case values:

```bash
python3 scripts/normalize_mapping_values.py --dry-run   # preview
python3 scripts/normalize_mapping_values.py             # apply
git diff --stat                                          # verify only values changed
pytest tests/test_vocabulary.py                          # confirm green
```
