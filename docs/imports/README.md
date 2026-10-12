# Imports

> **Status:** partial
> **Sources:** `raw/openlibrary-docs-ai/imports/` (7 files: index.md, api.md, marc-encoding.md, validation.md, adding-sources.md, add-book-internals.md, debugging.md)
> **Last ingested:** 2026-06-27

The import pipeline ingests book records from external sources — Internet Archive items, partner catalogs, bulk JSONL feeds, MARC binary files — and creates or updates Editions and Works in the OL database. Every import path terminates at the same function: `catalog/add_book.py::load()`.

---

## How It Works

Three flows share one final step:

```
External source (JSONL/API/IA)
        │
        ▼
DataProvider / DataProviderRecord        ← openlibrary-client repo
(JSONLProvider, PaginatedAPIProvider)
        │
        ▼
OLImportRecord  ──────────────────────── POST /api/import
                                          POST /api/import/ia
                                          POST /import/batch/new
        │
        ▼
    add_book.load()                       ← catalog/add_book/__init__.py
        │
        ▼
    OL database (Work + Edition)

IA bulk MARC file:
  POST /api/import?bulk_marc=true&identifier=ocaid/file:offset:len
        │
        ▼
  get_from_archive_bulk() → MarcBinary → read_edition() → add_book.load()
```

**Multi-repo layout:**

| Repo | Role |
|------|------|
| `internetarchive/openlibrary-client` | `DataProvider`, `DataProviderRecord`, `OLImportRecord` — the abstract import framework |
| `internetarchive/openlibrary-bots` | `sources/<slug>/` — concrete source adapters (ITAN, BWB, etc.) |
| `internetarchive/openlibrary` | `plugins/importapi/` HTTP endpoints; `core/batch_imports.py`; `catalog/add_book.py` record creation |

### add_book.load() internals

All paths end here. Phases in order:

1. `normalize_import_record(rec)` — ISBN normalization, author dedup, HTML entity unescape, source_records cleanup
2. `validate_record(rec)` — required fields check. **Exception:** if `source_records` starts with `"ia:"`, validation is skipped entirely (IA records predate the JSON schema)
3. `build_pool(rec)` — collect candidate existing editions by ISBN, LCCN, OCLC, source_records
4. `find_match(rec, pool)` — run `threshold_match()` against each candidate; return first match or None
5. If match found: `update_edition_with_rec_data(edition, rec)` — merge new fields into existing
6. If no match: `import_record_to_edition(rec)` — create new Edition + Work

### Matching algorithm

**Quick match** (identifier-based, runs first): ocaid → source_records prefix, ISBN-13, ISBN-10, non-ISBN ASIN, OCLC/LCCN. Returns immediately if any hit.

**Threshold match** (score ≥ 875 to confirm):
- Level 1 (fast): short title ±450, LCCN ±200, publish date ±200/-800, ISBN ±85
- Level 2 (full): adds page count, publisher, author comparison, full title keyword scoring
- A publish-date mismatch scores −800 — two editions with different years almost never match

### Status lifecycle

```
pending → processing (atomic claim by import_first_staged)
         → found     (matched existing edition)
         → created   (new edition created)
         → modified  (existing edition updated)
         → failed    (error_code set)
```

`processing` is the race guard — atomic `UPDATE ... RETURNING *` prevents two ImportBot workers from claiming the same item.

---

## Why It Exists

Open Library's catalog is built primarily from external sources: IA scanning partners, MARC bulk files, and partner publishers. Without a pipeline that deduplicates and normalizes these records, the same book would accumulate dozens of distinct Edition records. The import pipeline enforces a canonical merge path: same ISBN or source_records → update existing; new record → create new Edition and link to an existing or new Work.

---

## How It Is Used

### Adding a new import source

Define two classes in `openlibrary-bots/sources/<slug>/`:

```python
# sources/<slug>/record.py
class MyRecord(DataProviderRecord):
    title: str
    authors: list[dict]
    # ...
    def to_ol_import(self) -> OLImportRecord | None:
        # Map source fields → OLImportRecord; return None to skip this record
        ...

# sources/<slug>/provider.py
class MyProvider(JSONLProvider):
    SOURCE_SLUG = "myslug"          # prefix for source_records: "myslug:ID123"
    SOURCE_URL = "https://..."      # JSONL feed URL
    RECORD_CLASS = MyRecord
```

`source_records` format: `["myslug:ID123"]` — this is the deduplication key. Submitting the same value twice is idempotent.

For paginated APIs or OPDS feeds, subclass `PaginatedAPIProvider` or `OPDSProvider` instead. Reference implementation: `sources/itan/record.py` + `sources/itan/provider.py`.

**Identifier registration:** If the source uses a proprietary ID (not ISBN/OCLC/LCCN), add it to `openlibrary/plugins/openlibrary/config/edition/identifiers.yml` BEFORE batch submission. OL silently drops unknown identifier keys — no error, no warning. The identifier PR must merge AND deploy (weekly cycle) before any records with that identifier are submitted. See [[Known Limitations]].

### Submitting a batch

```bash
# POST a JSONL file to the batch queue (logged in required)
curl -X POST "http://localhost:8080/import/batch/new" \
  --cookie "session=..." \
  -F 'batch=@records.jsonl' \
  -F 'batchName=myslug-2026-q1'

# Preview one record without writing
curl -X POST "http://localhost:8080/api/import?preview=true" \
  -H "Content-Type: application/json" \
  -d @record.json | python3 -m json.tool
```

**Preferred path for new sources**: batch import (`/import/batch/new`). The direct single-record path (`/api/import`) writes immediately and is planned for deprecation in BookWorm Phase 3.

**Trust levels:**
- Non-admin users: batch lands at `status=needs_review`, waits for manual admin approval
- Admin accounts: `status=pending`, processed immediately by ImportBot

### Running ImportBot locally

```bash
COMPOSE_FILE="compose.yaml:compose.override.yaml:compose.near-prod.yaml" \
  docker compose up -d web infobase db memcached home importbot

docker compose logs -f importbot
```

The `importbot` service in `compose.near-prod.yaml` sets `LOCAL_DEV=true` (logs in as `openlibrary@example.com`/`admin123`), polls every 15 seconds, single worker.

---

## Subcomponents and Architecture

### DataProvider framework (`openlibrary-client`)

| Class | Role |
|---|---|
| `DataProvider` | Abstract base; owns `iter_ol_records()` (traversal + mapping chain) |
| `DataProviderRecord` | Abstract; `extra="allow"` — absorbs source-specific fields |
| `OLImportRecord` | Concrete; `extra="forbid"` — only fields in `import.schema.json` survive |
| `JSONLProvider` | Reads a JSONL URL; yields records |
| `PaginatedAPIProvider` | Override `iter_records()` for paginated REST APIs |

### importapi plugin (`plugins/importapi/`)

| File | Role |
|---|---|
| `code.py` | HTTP handlers for `/api/import`, `/api/import/ia` |
| `import_edition_builder.py` | Converts parsed data → edition dict for add_book |
| `import_validator.py` | Quality gate: tries `CompleteBook` then `StrongIdentifierBook` Pydantic models |

See [[public-apis]] for endpoint contracts.

### Validation gate

`import_validator.py` runs only on the MARC-less IA path (`require_marc=false`). Two models tried in order:

1. **`CompleteBook`** — requires `title + source_records + authors + publishers + publish_date`
2. **`StrongIdentifierBook`** — requires `title + source_records + (isbn_10 | isbn_13 | lccn)`

Both fail → `BookImportError("not-differentiable")`. Common for pre-ISBN public domain IA items with title + author + date but no publisher or ISBN. **MARC paths bypass the validator entirely.**

### MARC encoding pipeline

`catalog/marc/marc_binary.py::BinaryDataField.translate()` handles both encodings:

- **MARC8** (leader byte 9 = space): `mnemonics.read()` → `marc8.translate()` → `NFC normalize`
- **UTF-8** (leader byte 9 = "a"): `bytes.decode("utf-8")` → `NFC normalize`

`mnemonics.py` expands mnemonic escapes (`{eacute}` → MARC8 bytes) — output is still MARC8 bytes, not Unicode. `marc8.translate()` is `pymarc.MARC8ToUnicode`. PR #13017 adds explicit NFC normalization to the MARC8 branch (pymarc 5.3.1 already outputs NFC, so this is defensive).

`parse.py::read_edition()` maps MARC fields to OL edition dicts: field 008 → `publish_country`/`publish_date`, field 020 → ISBNs, fields 700/710 → `contribs`.

### Batch processing

`core/batch_imports.py::batch_import()` handles `POST /import/batch/new`: validates each JSONL line via Pydantic, accumulates into a named `Batch` (`{username}:{batchName}`). `scripts/manage-imports.py` (ImportBot) runs as a multiprocessing pool, consuming `import_item` rows in `processing` state.

---

## Key Files

| File | Purpose |
|---|---|
| `openlibrary-client/olclient/imports.py` | `DataProvider`, `DataProviderRecord`, `OLImportRecord`, `JSONLProvider` — abstract framework |
| `openlibrary/plugins/importapi/code.py` | HTTP handlers for `/api/import`, `/api/import/ia` |
| `openlibrary/plugins/importapi/import_edition_builder.py` | Converts parsed records → edition dict |
| `openlibrary/plugins/importapi/import_validator.py` | `CompleteBook` / `StrongIdentifierBook` Pydantic quality gate |
| `openlibrary/fastapi/importapi.py` | FastAPI `GET/POST /import/preview.json` |
| `openlibrary/core/batch_imports.py` | JSONL batch endpoint logic |
| `openlibrary/core/imports.py` | `Batch` model — internal batch queue |
| `openlibrary/catalog/add_book/__init__.py` | `load()` — top-level orchestrator: validate → match → create/update |
| `openlibrary/catalog/add_book/load_book.py` | `build_query()`, author resolution, `import_record_to_edition()` |
| `openlibrary/catalog/add_book/match.py` | `threshold_match()`, `level1_match()`, `level2_match()`, `normalize()` |
| `openlibrary/catalog/get_ia.py` | `get_marc_record_from_ia()`, `get_from_archive_bulk()` |
| `openlibrary/catalog/marc/marc_binary.py` | `MarcBinary` — parses binary MARC; `BinaryDataField.translate()` NFC pipeline |
| `openlibrary/catalog/marc/mnemonics.py` | Expands MARC mnemonic escapes (output still MARC8 bytes) |
| `openlibrary/catalog/marc/parse.py` | `read_edition()` — MARC record → OL edition dict |
| `openlibrary/schemata/import.schema.json` | Canonical JSON schema (`additionalProperties: false`) |
| `openlibrary/plugins/openlibrary/config/edition/identifiers.yml` | Registered identifier types |
| `scripts/manage-imports.py` | ImportBot: multiprocessing pool consuming the batch queue |
| `compose.near-prod.yaml` | Adds `importbot` service for local testing |
| `openlibrary-bots/sources/itan/` | Reference source adapter implementation |

---

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `LOCAL_DEV` | (unset) | Set to `true` in compose.near-prod.yaml — logs ImportBot in as dev account |
| `OL_IMPORT_ALL_SLEEP` | 60s (prod) / 15s (local) | Seconds between queue polls when empty |
| `OL_IMPORT_ALL_PROCESSES` | 8 (prod) / 1 (local) | Worker pool size — keep at 1 locally to avoid SQLite lock contention |

Cover URL allowlist (hardcoded in `catalog/add_book/__init__.py`):
```python
ALLOWED_COVER_HOSTS = (
    "archive.org", "books.google.com", "commons.wikimedia.org",
    "covers.openlibrary.org", "m.media-amazon.com"
)
```
Covers from other hosts are silently set to `None` with no error or warning —
**but only on the fresh-create path** (`load_data()`, via `check_cover_url_host()`).
See [[covers]] for the second, stricter gate on the update/merge path, why a
client-side fix does *not* reach the in-repo importer scripts, and the design
options that would.

---

## Testing

```bash
# importapi endpoint tests
docker compose run --rm home python -m pytest openlibrary/plugins/importapi/tests/ -xvs

# batch import tests
docker compose run --rm home python -m pytest openlibrary/tests/core/test_batch_imports.py -xvs

# add_book full suite
docker compose run --rm home python -m pytest openlibrary/catalog/add_book/tests/ -xvs

# matching specifically
docker compose run --rm home python -m pytest openlibrary/catalog/add_book/tests/test_match.py -xvs

# Test a DataProvider locally (from openlibrary-bots)
cd ~/Projects/openlibrary-bots
python3 -c "
from sources.itan.provider import ITANProvider
for i, rec in enumerate(ITANProvider().iter_ol_records()):
    print(rec.model_dump(exclude_none=True))
    if i >= 4: break
"
```

Key fixtures in `test_add_book.py`:
- `test_workshuberthowe00racegoog` — double-import of same MARC record produces exactly one author
- `test_missing_source_records` — Nuremberg war crimes trial record

---

## Performance

ImportBot runs as a configurable multiprocessing pool (default 8 workers in prod, 1 locally). Each worker polls the `import_item` table with atomic `UPDATE ... RETURNING *` for the race-guard. Queue throughput depends on batch size and `add_book.load()` Infobase write latency. No async; all synchronous.

---

## Related Processes

- **ImportBot** (`scripts/manage-imports.py`) — cron daemon consuming the batch queue; see [[infrastructure]]
- **Solr updater** — new Editions from imports propagate to search; see [[search]]
- **openlibrary-bots** — source adapters run independently on their own schedules; submit to `/import/batch/new`
- **Promise items** — IA placeholder editions (revision=1) that get overwritten wholesale when a MARC record arrives (full `load_data()` replace, not merge)

---

## What's Broken / Fragile / Unimplemented

### Confirmed bugs in add_book

**Walrus operator precedence bug** (`load_book.py::find_author()` ~line 243, NOT `__init__.py` — corrected 2026-07-20, verified against source):
```python
# BUGGY — key gets bool, not string
if key := a["key"] in seen:
# FIX:
if a["key"] in seen:
    continue
seen.add(a["key"])
```
Fixed by [PR #13021](https://github.com/internetarchive/openlibrary/pull/13021) (closes #13015), verified 2026-07-20: confirmed the bug reproduces exactly as described (reverting just this line makes the PR's own regression test, plus two additional Ada-authored tests covering a 3-way duplicate and a distinct-authors negative control, all fail; restoring the fix makes all pass). Full `add_book` test suite (157 tests incl. the 2 new ones) green with the fix. Runtime effect confirmed: when `things` contains 2+ entries for the *same* real author key (hit via primary name + alternate name in separate query iterations), dedup silently never collapses them, so `pick_from_matches()` gets invoked with duplicate entries unnecessarily — harmless in the single-duplicate-author case (still resolves to the same key) but wasted work, and a real correctness risk if `pick_from_matches` or downstream logic ever assumed list uniqueness.

**`existing.k` attribute access bug** — **already fixed, remove from this list** (was `load_book.py` ~line 324; verified 2026-07-20 that current `origin/master` no longer contains this code at all). Fixed in two steps, both already on master: [`d74311b03`](https://github.com/internetarchive/openlibrary/commit/d74311b0376be7038eb72ae83d7138350a7f51d1) ("use `_data.pop` to strip infobase metadata from matched author"), then fully removed by [`f33c3b0b5`](https://github.com/internetarchive/openlibrary/commit/f33c3b0b57143abcb965ee9c4d52c0f4d305ce25) closing #13016 ("`id` is not a field on Authors, and the core infogami fields do not need to be stripped... the 'fixed' code from #13016 never ran in the history of the project, with no impact"). Caught this only because PR #13021's branch was cut before those two commits landed, so a naive `git diff origin/master..HEAD` (tip-vs-tip, not merge-base) on that branch surfaces this block as a false-positive "addition" — `git diff $(git merge-base origin/master HEAD)..HEAD` (or `gh pr diff`) shows the true, correctly-scoped 2-line diff. Worth remembering generally: always diff a PR branch against its merge-base, not master's current tip, or unrelated upstream drift reads as part of the PR.

**Dead code: `re_normalize`** (`__init__.py` line 72):
```python
re_normalize = re.compile("[^[:alphanum:] ]", re.UNICODE)
```
Uses POSIX character class syntax invalid in Python `re`. Never called, so no runtime effect. Dead code.

### Import effort lifecycle — the states after the PR merges

A code change is done when it merges. **An import effort is not.** Most of the
expensive failures in this domain happen *after* apparent success, which is
why a PR-shaped checklist misses them entirely.

**Three states where apparent success IS the failure.** These are the ones to
check first, and all three are answerable by unauthenticated public reads
(`openlibrary.org/books/OL…json`, the identifiers config,
`covers.openlibrary.org/b/olid/…json`) — no credentials needed:

| State | The silent failure |
|---|---|
| `identifiers-registered` | A proprietary ID not merged **and deployed** in `identifiers.yml` before submission is **silently dropped** — no error, no warning, import reports success. Records land unfindable by the only ID the provider has. Bit ITAN. Deploy is weekly, so this is a precondition on something outside the repo. |
| `covers-attached` | A record with `cover` imports cleanly and the cover never attaches — dropped by one of two allowlists, one of which sets `cover_url = None` with no error at all. Batch 1516: ~850 bookdash books, clean import, zero covers. See [[covers]]. |
| `records-correct` | Records landed and are wrong in ways no status reports. The recurring one is **duplicate authors** — see below; a role-suffix string check is *not* the right detector. Nothing fails. |

**The ordinary states.** These need the `import_item`/`Batch` tables, which
are **not publicly readable** — so a check that cannot reach the DB must
*escalate*, never silently return nothing:

`batch-submitted` (row count matches what was sent) → `batch-approved`
(non-admin submissions sit at `needs_review` indefinitely, and that looks
identical to slow processing) → `queue-drained` (nothing left `pending` or
`processing`) → `failures-triaged` (every `failed` row's error understood or
escalated — note `not-differentiable` is often *recoverable* via the MARC
path, so a failed row is not a dead one).

**Structural warning that kills the obvious implementation.**
`ImportItem.set_status()` sets `data = NULL` for every non-`failed` status, in
the same call that writes `ol_key`. So the instant a record succeeds, the
submitted record — its `cover` URL, its identifiers — is **erased from the
queue row**. A post-import check cannot recover what was submitted from the
database; it must carry the source record or re-derive it from the provider.
This already killed one cover-fix design.

**The submitted record has no `ol_key`. The join key is `source_records[0]`.**
A record at submission carries `title`, `source_records`, `publishers`,
`authors: [{"name": …}]`, `languages`, `subjects`, `description`, and
optionally `identifiers` and `cover`. That is all. `ol_key` is written onto
the `import_item` row later by `set_status()`, in the same call that NULLs
`data`. `Batch.add_items` keys rows as `ia_id = r["source_records"][0]`, which
is also the pipeline's dedup key.

**Submission → edition is a ONE-hop public lookup. Do not route it through
`import_item`.** An earlier revision of this page said the join was
"necessarily" two-hop via `import_item.ol_key`, which would have dragged every
post-import check behind the credentials wall. It is not:

```bash
curl -A "your-tool/1.0" \
  'https://openlibrary.org/query.json?type=/type/edition&source_records=bwb:9780300248388'
# -> [{"key": "/books/OL28728623M"}]
```

Unauthenticated, verified 2026-09-20. **Solr cannot do this** —
`source_records` is not a searchable field and every query shape returns zero;
it is specifically the infogami `query.json` endpoint. Useful well beyond the
import lifecycle: anything needing submission → edition can do it publicly.

This is why the three post-success states stay the three cheapest.

**Two traps when scripting against openlibrary.org:**

- **OL throttles the default `Python-urllib` user agent**, and the throttle
  presents as a *timeout*, not an error. A check that reads timeout as "no
  edition found" reports healthy imports as broken. Always set a UA naming the
  tool.
- **Transient 503s are routine** — one was hit mid-verification of this very
  paragraph. A check must report "could not determine" and never a confident
  negative. Same principle as the `queue-access` gate below.

**Detecting duplicate authors: do not use a string heuristic.** Duplicates
arrive by at least two unrelated mechanisms:

1. **Source-side name pollution** — role suffixes (`"Megan Andrews
   (Illustrator)"`), but equally initials vs full names, punctuation,
   transliteration. Each flavour would need its own rule, endlessly.
2. **OL-side match failure** — the author exists and dedup fails to collapse
   onto it. Documented in openlibrary#13015 / PR #13021: `things` holds 2+
   entries for the *same real author key*, reached via primary name and
   alternate name in separate query iterations. **Nothing in the incoming
   record is malformed at all**, so no string check can see it.

The detector that covers both, and flavours nobody has thought of: **for each
created edition, do its author keys predate the batch?** An author key created
*by this batch* whose name closely matches a pre-existing one is the signal.
Author keys carry creation timestamps and the batch has a submission time, so
this is derivable rather than guessed. Most imports legitimately create some
authors, so the output is a list to triage, not a boolean — which makes it
ledger-shaped, like `failures-triaged`.

**`internal-error` is weak evidence.** ImportBot fails a large fraction of
records under load — 79 of 94 Lenny records returned `internal-error`, every
one succeeding on serial retry. Triage that treats these as real failures
generates noise; triage that treats them as transient hides real ones.
Whether the cause is concurrency or sustained write rate is **not
established**.

### The Lenny harvest funnel: 96 → 95 → 94, two unrelated causes

Documented on `12844/feed-edition-id-match` (`588dcb3c4`) and worth having
here, because the three numbers get run together and the accounting becomes
unreadable.

| Count | Where it comes from |
|---|---|
| **96** | the feed's `numberOfItems` |
| **95** | one item's `openlibrary_edition` does not resolve in OL search, so it drops out of `_enrich_items` while `Item.count()` still counts it (cf. ArchiveLabs/lenny#214) |
| **94** | LAMMA resolves fine but has no author in OL, so the import validator rejects it |

So **94 is the post-validation import count**, and it is reached by two
independent subtractions, not one. `search.json?q=id_lenny:*` returning
exactly 94 in production (measured 2026-09-21) is therefore *expected* rather
than coincidental — it corroborates the [[features/feed-registry-import-system]]
finding that nothing schedules a harvest, since the count matches one
hand-run harvest and has not grown.

**Caveat that survives:** 94 being unchanged shows no *further* run landed
records; it cannot by itself date the run. The olsystem grep is the
independent evidence for that.

> **Do not tighten `_check_page_is_credible` into an equality comparison.**
> `numberOfItems` will always read **one higher** than the publications
> actually retrieved, for the reason in the 96→95 row above. An equality
> check would reject every page. This is the kind of "obvious cleanup" that
> breaks harvesting silently.

### Infobase indexing is type-agnostic — `identifiers.{key}` works on any type

Verified 2026-09-21 by running the indexer, not by reading it. Recorded here
because it took real work to establish, it applies well beyond the PR that
raised it, and the answer otherwise lives only in a comment on a draft.

`infogami/infobase/_dbstore/indexer.py::compute_index` calls
`common.flatten_dict(doc)` over the **whole document** and indexes every
`str`/`int`/ref value, with one fixed skip list (`id`, `key`, `type.key`,
`revision`, …). **It never branches on type** — it touches `type.key` only to
skip it. Run against three real docs:

```
EDITION identifiers      -> [('str', 'identifiers.wikisource', 'Q42')]
WORK    identifiers      -> [('str', 'identifiers.wikisource', 'Q42')]
WORK    work_identifiers -> [('str', 'work_identifiers.goodreads', '12345')]
```

Work and Edition produce a **byte-identical** index entry for the same key
shape. They cannot be indexed differently, because nothing in the indexer
knows which it is. Any nested property is queryable on any type.

`things()` (`infobase/dbstore.py:225-247`) then uses `type` as a **filter**,
not as a property schema. Its one rule: a type is **required** when any
condition is on a key outside `['key', 'type', 'created', 'last_modified']`,
otherwise `BadData("Type Required")`. It never checks that the property
exists on that type.

**Practical consequence:** `site.things({"type": "/type/work",
"identifiers.goodreads": "123"})` works today, with no schema change. Omit
`type` and it raises. This was flagged as an unanswered "needs Docker
verification" open question on
[#12945](https://github.com/internetarchive/openlibrary/pull/12945) for 96
days; it needs neither Docker nor data, because it is a property of the code
rather than of the database contents.

### Known limitations

- **Cover URL allowlist(s) — two independent gates, not one** — see [[covers]] for
  the full picture. `load_data()` (fresh-create path) silently drops the cover if
  the host fails `check_cover_url_host()`. `update_edition_with_rec_data()`
  (match/merge path) has **no host check at all** — it calls `add_cover()`
  unconditionally, which POSTs to coverstore and gets rejected there by a second,
  independent, regex-based allowlist (`is_allowed_cover_url()` in
  `coverstore/utils.py`). Confirmed via internetarchive/openlibrary#10856
  (bookdash.org, ~850 books) that this is a real, active bug, not just a
  theoretical gap — its host matches neither allowlist. **Still open as of
  2026-09-19** — the fix in `openlibrary-client`
  ([#448](https://github.com/internetarchive/openlibrary-client/pull/448)) does
  *not* reach these providers, because they never call `openlibrary-client` at
  all; see [[covers]] "Which providers are actually affected".
- **`ol import` CLI doesn't exist** — described in `pm/workflows/import_workflow.md` but not implemented in `olclient/cli.py`; batch submission requires a Python script calling `DataProvider.iter_ol_records()` directly
- **Identifier deploy dependency** — new identifier types silently dropped until the identifier PR deploys (weekly cycle)
- **No trusted-partner tier** — batches are either admin (auto-approved) or non-admin (manual review); no middle tier

### Open issues and active PRs

| PR / Issue | Status | What |
|---|---|---|
| [#13017](https://github.com/internetarchive/openlibrary/pull/13017) | Open, CI green | Explicit NFC in `BinaryDataField.translate()` MARC8 branch |
| [#12947](https://github.com/internetarchive/openlibrary/pull/12947) | Ready to merge | `itan_technologies` identifier |
| [#12657](https://github.com/internetarchive/openlibrary/pull/12657) | Open | `batchName` param for `/import/batch/new` |
| [#12953](https://github.com/internetarchive/openlibrary/pull/12953) | Ready to merge | HTML numeric entity unescape in `normalize_import_record` |
| [#12945](https://github.com/internetarchive/openlibrary/pull/12945) | Draft | `work_identifiers` support for work-level matching |
| [#12655](https://github.com/internetarchive/openlibrary/issues/12655) | Open | Epic: BookWorm — modernize import pipeline |
| [#10756](https://github.com/internetarchive/openlibrary/issues/10756) | Open | `not-differentiable` for pre-ISBN IA items; proposed `IABook` third validator |
| [#447 (bots)](https://github.com/internetarchive/openlibrary-bots/pull/447) | CI infra failures | ITAN source adapter (blocked on #12947 deploy) |

---

## Common Confusion

- **IA validation bypass** — `source_records` starting with `"ia:"` skips ALL validation in `add_book.load()`. IA records can have missing `title`, `authors`, etc. that would reject any other source. This is intentional — IA MARC predates the schema.

- **Validator only runs on MARC-less IA path** — `import_validator.py` is called only when using `/api/import/ia` with `require_marc=false` and no MARC file exists. MARC-based imports (`bulk_marc=true`, or item with MARC file) call `add_book.load()` directly — no validator.

- **`not-differentiable` is recoverable** — if the IA item has a MARC file (`{ocaid}_meta.mrc` or `{ocaid}_marc.xml`), the MARC path bypasses the validator entirely. Check for the MARC file before giving up.
  **Verified 2026-09-21** at `plugins/importapi/code.py:288-307`, the only site
  that raises it. `get_marc_record_from_ia()` runs first; when it returns a
  record the code takes `read_edition(marc_record)` and `not-differentiable`
  is unreachable. It is raised **only** in the `else` branch — no MARC record,
  so `get_ia_record(metadata)` runs and its `ValidationError` becomes
  `not-differentiable`. So the failure is strictly "no MARC *and* the IA
  metadata is insufficient," never "the metadata is insufficient" alone.

- **Identifier registration must happen before batch submission** — PR #12947 must merge AND deploy before the ITAN adapter can submit records with `itan_technologies` keys. Until then, those keys are silently dropped with no error.

- **Batch not accumulating** — repeated POSTs to `/import/batch/new` without `batchName` create orphan batches (default is a SHA hash before PR #12657). Pass `batchName` to accumulate into the same batch.

- **`ol import` CLI** — referenced in `pm/workflows/import_workflow.md` but not implemented. Use a Python script instead.

- **Promise item overwrite** — a revision-1 IA edition with a MARC record gets fully overwritten by `load_data()`, not merged. Intentional: MARC is authoritative over a stub.

---

## Dependencies

**Depends on:**
- [[core-operations]] — Infogami object model, plugin routing; importapi is a plugin
- [[ol-client]] — DataProvider/DataProviderRecord/OLImportRecord live in openlibrary-client
- [[infrastructure]] — ImportBot scheduling, Infobase writes, deploy cycle for identifier registration
- [[search]] — Solr must index newly created/updated editions

**Depended on by:**
- openlibrary-bots — all source adapters submit through this pipeline
- [[public-apis]] — `/api/import` endpoints are documented public-facing API

---

## Provisioning / Services

Three repos required for a complete import flow:
1. `openlibrary-client` — installed as a Python package; source of truth for record schema
2. `openlibrary-bots` — run independently (scripts or cron); each adapter handles its own schedule
3. `openlibrary` — hosts the HTTP endpoints and ImportBot daemon

ImportBot runs as a supervised process in production (see [[infrastructure]]). Local dev: `compose.near-prod.yaml`.

---

*Sources: `raw/openlibrary-docs-ai/imports/` (7 files) · See [[README]] · [[METHODOLOGY]]*
