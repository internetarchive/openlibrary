# Tags System

Domain reference for Open Library's tag system. Covers the two-tier tag architecture (legacy subjects + Tag objects), how they relate, how Tag objects are created, Solr implications, and community tags.

**Status as of June 2026:** The Tag object infrastructure (created by Jayden, GSoC 2023) is live in production. The controlled vocabulary project (`Open-Book-Genome-Project/tags`) is in Phase 1-2. OL integration (Phase 3) has not started.

---

## Background: Two Tag Systems in Production

OL has two tag systems running in parallel — the legacy subject system and the new Tag object system:

| System | Where stored | Schema | Created by |
|--------|-------------|--------|-----------|
| **Legacy subjects** | `works.subjects` (flat string list) | Plain strings | Anyone editing a work |
| **Tag objects** | Infogami: `/tags/OL123T` | Typed JSON documents | Curators and admins only |

They are linked by name lookup — a subject string `"cooking"` can map to a Tag document whose `slugs` field contains `"cooking"`. But most subjects have no corresponding Tag document yet.

---

## Legacy Subject System

Works store subjects as flat string arrays:

```json
{
  "key": "/works/OL82563W",
  "subjects": ["Wizards", "Magic", "Fantasy fiction"],
  "subject_people": ["Harry Potter", "Hermione Granger"],
  "subject_places": ["Hogwarts", "England"],
  "subject_times": ["20th century"]
}
```

- `subjects` — the catch-all; everything from genres to LC call numbers to noise
- `subject_people`, `subject_places`, `subject_times` — semi-typed variants added years ago
- Prefix convention (partially adopted): `people:`, `place:`, `collection:` — subject strings with a prefix denoting type

**The problem:** `"new-york"`, `"newyork"`, and `"place:new_york"` all coexist. There's no deduplication, no controlled vocabulary, no i18n, no hierarchy.

---

## Tag Objects (Infogami `/type/tag`)

Tag objects are first-class Infogami documents at `/tags/OL123T`. They were introduced by Jayden's GSoC 2023 project ("Supercharging Subject Pages").

### Schema

```json
{
  "key": "/tags/OL32T",
  "type": {"key": "/type/tag"},
  "name": "cooking",
  "tag_type": "subject",
  "tag_description": "Works substantially about cooking.",
  "body": "<description of the cooking tag>",
  "slugs": ["cooking", "cook", "cookery"],
  "deputy": "/people/somelibrarian"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Display name (used in URL suffix) |
| `tag_type` | string | Yes | One of the controlled types (see below) |
| `tag_description` | string | Yes | One-sentence description |
| `body` | string | Yes | Rich text content for the subject page |
| `slugs` | string[] | Yes | Normalized lookup keys (see subject→Tag lookup below) |
| `deputy` | string | No | Key of a librarian with edit permission |

### Tag Types

Defined in `openlibrary/plugins/upstream/addtag.py`:

```python
SUBJECT_SUB_TYPES = [
    "subject", "person", "place", "time",
    "genre", "subgenre", "content_format", "literary_form", "mood",
]
TAG_TYPES = SUBJECT_SUB_TYPES + ["collection"]
```

- **Subject types** (`SUBJECT_SUB_TYPES`): can be linked to subject pages (`/subjects/genre:horror`)
- **Collection type**: for curated collection pages; not linked to subject strings

### How Subject String → Tag Object Lookup Works

```python
# Tag.find() in openlibrary/core/models.py
q = {"type": "/type/tag", "slugs": Tag.normalize(subject_string)}
if tag_type:
    q["tag_type"] = tag_type
matches = list(site.get().things(q))
```

The flow:
1. Normalize the subject string: `Tag.normalize("Cooking")` → `"cooking"` (via `normalize_subject_name`)
2. Query Infogami for Tag documents whose `slugs` array contains `"cooking"`
3. Subject pages fetch this Tag and use its `body` / `tag_description` to enrich the page

The `slugs` field is many-to-one: multiple subject strings can map to one Tag. This is how `"cooking"`, `"cook"`, and `"cookery"` all resolve to `/tags/OL32T`.

**Pattern by URL:**
- `/subjects/cooking` — OL resolves via subject string lookup
- `/tags/-/subject:cooking` → redirects to the canonical Tag document if one exists
- `/tags/OL32T` — direct access by key

---

## How to Create a Tag Object

### Via the UI

1. Visit `/tag/add` (requires curator or admin membership)
2. Fill in: name, tag type, description, body, additional slugs
3. On save: OL assigns a new `/tags/OL123T` key and persists the document

Alternatively, visit a subject page and click "Edit" — if no Tag exists, it creates one.

### Programmatically

```python
from openlibrary.plugins.upstream.models import Tag

tag_dict = {
    "name": "horror",
    "tag_type": "genre",
    "tag_description": "Works whose primary intent is to produce fear.",
    "body": "<p>Horror fiction...</p>",
    "slugs": ["horror", "horror-fiction", "gothic-horror"],
}
tag = Tag.create(tag_dict, comment="Creating canonical genre tag")
# Returns the new Tag document; tag.key will be "/tags/OL456T"
```

### Permissions

- **Create:** curator or admin
- **Edit:** curator, admin, or the tag's `deputy` (if subject-type tag)
- **Delete:** curator or admin (via edit form)

---

## How Tags Relate to Works

### Current (June 2026): Subjects only

Works do not reference Tag objects directly. Tags are fetched by name from subject strings. When you view `/subjects/cooking`, OL looks up the Tag document and enriches the page — but the Work record itself only has `"cooking"` as a string in `subjects`.

### Future (Phase 3, gated on GH #11610): Typed fields on Work records

The plan is to add explicit typed fields to Work records:

```json
{
  "key": "/works/OL82563W",
  "subjects": ["...legacy strings..."],
  "genres": ["horror", "thriller"],
  "moods": ["dark", "atmospheric"],
  "content_warnings": ["graphic-violence"]
}
```

Each value in these fields will be a canonical slug from the controlled vocabulary (`Open-Book-Genome-Project/tags`), and each slug will have a corresponding Tag document.

**GH issue:** [internetarchive/openlibrary#11610](https://github.com/internetarchive/openlibrary/issues/11610)

---

## Tags and Solr

### Current Solr fields (from `managed-schema.xml`)

| Field | Source | Purpose |
|-------|--------|---------|
| `subject` | `works.subjects` | FT search on subject strings |
| `subject_facet` | `works.subjects` | Faceting by subject |
| `subject_key` | `works.subjects` | Exact slug lookup |
| `subject_type` | — | Subject type (person/place/etc.) |
| `top_subjects` | — | Top subjects stored for display |

Defined in `openlibrary/solr/updater/work.py:build_subjects()`:

```python
field_map = {
    "subjects": "subject",
    "subject_places": "place",
    "subject_times": "time",
    "subject_people": "person",
}
```

**Tag objects are NOT indexed in Solr.** Solr only knows about subject strings. Tag documents live in Infobase and are fetched on demand for subject page enrichment.

### Future Solr Changes (Phase 3)

When typed fields are added to Work records, the Solr updater and schema will need:
- New fields: `genre`, `genre_facet`, `genre_key`, `mood`, `mood_facet`, etc.
- Schema file: `conf/solr/conf/managed-schema.xml`
- Updater: `openlibrary/solr/updater/work.py` — extend `build_subjects()` or add `build_genres()`
- This requires a **Special Deploy** — new Solr fields must be created on the prod Solr core before the updater code is deployed

---

## Community Tags (Observations)

### What they are

The "observations" or "community reviews" system lets patrons personally tag books with a fixed set of vocabulary. Stored in the `observations` psql table (patron → work → type_id → value_id).

### Why they're underutilized

The vocabulary is hardcoded in `openlibrary/core/observations.py` as a Python dict (OBSERVATIONS). It's a fixed list of ~12 types (Pace, Enjoyability, etc.) with predefined values. Patrons cannot:
- Propose new tag types or values
- Search by community tag
- Create open-ended tags

The UI is buried inside the book review flow. Community tags don't appear in Solr, don't power subject pages, and aren't discoverable.

### Planned migration

The design doc proposes migrating from `observations` (hardcoded strings) to actual Tag objects:

```sql
-- Current (observations table): patron + work + hardcoded type_id + value_id
-- Future (community_tags table): patron + work + tag_id (references /tags/OL123T)
```

This would let librarians define the community tag vocabulary in Tag documents, patrons add any Tag to any work, and community tag counts surface in Solr. Implementation is deferred — no open PR as of June 2026.

---

## Key Files

### `internetarchive/openlibrary`

| File | Purpose |
|------|---------|
| `openlibrary/core/models.py:Tag` | `Tag` base class — `find()`, `create()`, `normalize()` |
| `openlibrary/plugins/upstream/addtag.py` | Routes: `/tag/add`, `/tags/OL*T/edit`, `/tags/-/type:name`, `/tags` index |
| `openlibrary/plugins/upstream/models.py:Tag` | OL-specific `Tag` subclass (currently just passes to parent) |
| `openlibrary/templates/type/tag/` | Templates: `view.html`, `form.html`, `index.html`, `tag_form_inputs.html` |
| `openlibrary/plugins/worksearch/subjects.py` | `subject_name_to_key()` — maps subject strings to `/subjects/*` URLs |
| `openlibrary/solr/updater/work.py:build_subjects()` | Indexes `subjects`, `subject_people`, `subject_places`, `subject_times` into Solr |
| `openlibrary/core/observations.py` | Hardcoded community tag vocabulary; `Observations` CRUD |
| `openlibrary/plugins/openlibrary/bulk_tag.py` | ILE bulk tagger endpoint |
| `conf/solr/conf/managed-schema.xml` | Solr field definitions (subject, subject_facet, subject_key) |

### `Open-Book-Genome-Project/tags`

See `pm/workflows/tag-system.md` for full breakdown.

| File | Purpose |
|------|---------|
| `*/vocabulary.json` | Controlled vocabulary per type (genres, moods, etc.) |
| `api/` | FastAPI autocomplete service (not yet deployed) |
| `scripts/migrate_subjects.py` | Migrate legacy subjects → typed canonical tags |
| `mappings/genres.json` | legacy subject string → canonical genre slug |

---

## Integration Path (Phase 3 Checklist)

When ready to wire the controlled vocabulary into OL:

```markdown
- [ ] Add `genres` field to olclient work schema (GH #11610)
- [ ] Update infogami type registry to accept `genres: List[Tag]`
- [ ] Update Work editing UI — tag input chips + autocomplete from Tags API
- [ ] Add `genre`, `genre_facet`, `genre_key` fields to Solr managed-schema.xml
- [ ] Update `openlibrary/solr/updater/work.py:build_subjects()` to index `genres`
- [ ] Create OL Tag documents for each canonical slug (e.g. `/tags/OL_T` for `genre:horror`)
- [ ] Write migration script: scan works dump → classify genres → batch-write to OL
- [ ] Smoke-test: verify `/subjects/genre:horror` renders Tag-enriched page
- [ ] Solr reindex required (new fields → special deploy needed)
```

---

## Open Questions

1. **Work storage:** Will `genres` be stored as slugs (`"horror"`) or Tag document references (`{"key": "/tags/OL32T"}`)? The design doc shows slugs; consistency with how `subject_people` stores plain strings suggests slugs are simpler for V0.
2. **Search routing:** Will `/subjects/genre:horror` continue to work, or will there be a redirect to `/tags/-/genre:horror`?
3. **Slug stability:** When a tag is renamed, `old_slugs` in vocabulary.json preserves the old slug. Does the OL Tag document's `slugs` field need to be updated too?
4. **Community tags timeline:** No concrete PR or issue for the observations → Tag migration. Deferred.
