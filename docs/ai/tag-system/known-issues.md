# Tags System — Known Issues

Current data quality gaps, architectural limitations, and open questions. Updated June 2026.

---

## Data Quality

### Title Case mapping values (resolved June 2026)

**Status: fixed** — PR #28 normalized all mapping values to slugs across 5 types (`audience`, `content_formats`, `literary_themes`, `literary_tropes`, `main_topics`). The data contract test (`test_all_values_are_slugs`) now enforces this going forward.

---

### audience/classify.py returned Title Case TagMatch values (resolved June 2026)

**Status: fixed** — PR #30 corrected the classify plugin to return slugs (`"children"`, `"young-adult"`) instead of display names.

---

### literary_form has no mappings or classify plugin

**Status: in progress** — PR #33 adds `mappings.json` (38 entries) and `classify.py` (LCSH suffix extraction, conflict resolution). Awaiting review.

Until PR #33 merges, `literary_form` classification relies on the `SubjectClassifier` in `scripts/migrate_subjects.py` only — it will not fire through the `TagType.classify()` path.

---

### audience/mappings.json Title Case values from contributor expansion

When shoaib-inamdar's audience mappings (PR #13) were merged, the values were Title Case (`"Juvenile"`, `"Children"`, etc.). These were normalized by PR #28. However, the `classify.py` plugin added in the same PR also had Title Case values — fixed by PR #30.

**Lesson:** When reviewing contributor PRs that add mappings or classify plugins, verify that all values are slugs before merging.

---

### main_topics vocabulary is "open" (no vocabulary.json)

`main_topics`, `literary_themes`, `literary_tropes`, and `moods` are open types — they have `mappings.json` but no controlled `vocabulary.json`. This means:

- `test_values_reference_valid_slugs` is not run for these types (no vocabulary to check against)
- Mapping values are only checked for slug format (`test_all_values_are_slugs`), not for semantic correctness
- New mapping entries can introduce misspellings or inconsistencies without a test catching them

**No immediate fix planned** — these types are intentionally open-ended. The data contract test for slug format is the guard.

---

## Architectural Limitations

### SubjectClassifier and TagType.classify() are separate codepaths

`scripts/migrate_subjects.py::SubjectClassifier` and `tags/__init__.py::load_all() + TagType.classify()` overlap in purpose but are not wired together. The script was written before the plugin architecture matured.

**Impact:** Improvements to a type's `classify.py` plugin don't automatically improve the migration script — `SubjectClassifier` has its own hardcoded logic. The two should eventually be unified.

**Near-term workaround:** Keep `SubjectClassifier` in sync manually. The backfill script (`scripts/backfill_genre_tags.py`) uses `SubjectClassifier` — make sure its mappings match what's in `tag_types/`.

---

### No classify.py plugins in most types

As of June 2026, only two types have `classify.py` plugins:

| Type | Plugin covers |
|---|---|
| `audience` | Grade-band patterns, LCSH juvenile suffix |
| `literary_form` | LCSH `--` suffix, conflict resolution (PR #33, pending) |

All other types (genres, subgenres, content_formats, literary_themes, etc.) rely on exact mapping lookups only. Complex LCSH subject strings with topic subdivisions (e.g. `"Dragons--Fiction"` → genres:fantasy) are not yet handled.

---

### Contributor PR #4 (modi02) used old architecture

modi02's `raj/literary-form-pack` PR (still open) implements a `LiteraryFormPack` using an older `RulePack` / `SubjectClassifier` architecture that predates the `tag_types/` layout. It cannot be merged as-is. The valuable LCSH suffix and conflict resolution logic was ported to PR #33.

**Action for Mek:** close PR #4 with a thank-you note pointing to PR #33.

---

## CI / Workflow

### Workflow file must be on main to trigger

GitHub only discovers `.github/workflows/` from the default branch. A workflow file added only to a feature branch will never fire. This is why CI was silent on early PRs — the workflow file (PR #17) had to merge to main before CI became active on subsequent PRs.

---

## Open Questions

| Question | Context |
|---|---|
| Should `literary_form` mappings include `"juvenile literature"` → `fiction`? | Currently excluded — juvenile literature is a format not a literary form. But it appears commonly in LCSH. |
| Process genres and subgenres in one backfill pass or separately? | Issue #14. One pass is simpler; separate passes allow piloting by type. |
| What batch size for `save_many()` during backfill? | Issue #14. Needs load testing against staging before production run. |
| Should `TagMatch.value` ever be a display name? | No — always a slug. The `default_classify` path and all `classify.py` plugins must return slugs. |
