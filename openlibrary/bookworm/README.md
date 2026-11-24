# BookWorm feed harvest — operator guide

Harvests OPDS 2.0 feeds from book providers into Open Library's import queue.

```
provider feed ──► cli harvest ──► import_item ──► ImportBot ──► catalog ──► acquisitions
                        │                              (manage-imports)
                   feed_registry
                  (url + cursor)
```

The harvester only *stages* records. `manage-imports` loads them, and the
catalog writes the `acquisitions` rows — so nothing appears in `acquisitions`
until ImportBot has run.

## Layout

| File | Role |
|---|---|
| `openlibrary/bookworm/registry.py` | `feed_registry` rows: url, cursor, connector config |
| `openlibrary/bookworm/opds.py` | OPDS 2.0 → import record (with `acquisitions[]`) |
| `openlibrary/bookworm/harvest.py` | fetch, parse, submit, advance the cursor |
| `openlibrary/bookworm/cli.py` | the command line: `harvest` (the cron entrypoint), `register` (the feed list, in git), `preview` (what would match, writing nothing) |

## Prerequisites

**Tables.** `openlibrary/core/schema.sql` carries the DDL, so fresh instances get
them automatically. An existing database needs them applied by hand — check
before creating, `acquisitions` may already exist:

```sql
\dt acquisitions
\dt feed_registry
```

The authoritative DDL is in `openlibrary/core/schema.sql` (search for
`CREATE TABLE feed_registry` and `CREATE TABLE acquisitions`); copy it from
there rather than from any ticket, so the two cannot drift.

**Proxy.** Hosts that egress through a proxy need `http_proxy` and
`no_proxy_addresses` in `openlibrary.yml`. The runner calls `setup_requests()`,
which exports them into the environment; `requests` reads them from there. An
environment already populated externally works too.

> `no_proxy_addresses` must cover internal hosts. `setup_requests()` sets the
> proxy process-wide, so anything the harvest process talks to — including
> internal services — routes through the proxy unless it is on that list.

## Rolling out a feed

Feeds register as **`pending`** and scheduled runs skip them, so registering is
safe. Validate, then activate.

```bash
CFG=/olsystem/etc/openlibrary.yml

# 1. what is registered now
python -m openlibrary.bookworm.cli register --ol-config $CFG --show

# 2. register (pending — cron will not touch it yet; idempotent, and it never
#    rewinds a cursor that has already progressed)
python -m openlibrary.bookworm.cli register --ol-config $CFG --provider lenny

# 3. validate: fetches and parses, writes nothing, leaves the cursor alone
python -m openlibrary.bookworm.cli harvest --ol-config $CFG --provider lenny --dry-run

# 4. one real pass by name (still pending, so cron stays out of the way)
python -m openlibrary.bookworm.cli harvest --ol-config $CFG --provider lenny

# 5. happy with what landed? hand it to cron
python -m openlibrary.bookworm.cli register --ol-config $CFG --provider lenny --activate
```

```sql
SELECT b.name, count(*) FROM import_item i
  JOIN import_batch b ON b.id = i.batch_id
 WHERE b.name LIKE '%-opds' GROUP BY b.name;
```

### Sizing the first run

An unseeded feed backfills its whole history — for Gutenberg that is ~78k items
at 25 per page, roughly 3,100 sequential fetches. That is the intended v1
behaviour: harvest Gutenberg from the beginning.

Records are staged to `import_item` in chunks of `SUBMIT_BATCH_SIZE` (1,000) as
the crawl pages, so neither memory nor any single SQL statement scales with the
size of the backfill. A failure partway through does not advance the cursor, so
the next run resumes and re-stages only what is missing.

To bound a backfill instead, seed the cursor at registration:

```bash
python -m openlibrary.bookworm.cli register --ol-config $CFG \
    --provider project_gutenberg --since 2026-08-28
```

`--since` applies **only on first registration**, so a routine re-run can never
replay history. To move the cursor of a feed that is already registered, add
`--reseed`.

### Batches

Each feed has one stable batch, `{provider}-opds` — a predictable namespace, so
a feed's whole queue is one query:

```sql
SELECT i.status, count(*) FROM import_item i
  JOIN import_batch b ON b.id = i.batch_id
 WHERE b.name = 'lenny-opds' GROUP BY i.status;
```

Deliberately not date-scoped, unlike `bwb_opds_imports.py`. That convention
exists for append-only importers, where a date is the only way to ask what a run
brought in. A feed re-offering a record updates its existing row rather than
adding one, so a date would segment nothing and would fragment the per-feed
view. Batch size is bounded by the feed's corpus rather than by uptime, and
`import_item.batch_id` is indexed. For recency, use `import_item.import_time`,
which is per record and more precise than a batch date.

Dedup is independent of batching: `Batch.dedupe_items` filters on `ia_id` across
the whole `import_item` table, so a record staged last month is not re-added
today.

### How acquisitions are stored

One row per `(provider_name, local_id)`, whose `data` is

```json
{"acquisitions": [{"access": "buy", "price": {...}, "url": "..."}, {"access": "open-access", "format": "application/epub+zip", ...}]}
```

— **every** link the publication offers, not just one. Price, epub and html
coexist.

**The feed is authoritative, so each save replaces that blob rather than
merging into it.** A link the provider has withdrawn disappears instead of
lingering forever. Replacement is scoped to `(provider_name, local_id)`, so one
provider's harvest can never clobber another's: an edition carrying both a BWB
price and a Gutenberg epub has two rows, each replaced independently by its own
feed.

> **A queued row is not refreshed.** Only rows at a terminal status
> (`created`/`modified`/`found`/`failed`) are updated in place. `manage-imports`
> never claims a row — it stays `pending` while being processed — so overwriting
> a queued row would race a worker holding the old copy and the update would be
> silently discarded. A change arriving while a row is queued is applied on a
> later run instead.

> **Re-harvesting only re-stages what actually changed.** A record whose
> acquisitions are byte-identical to the stored row is dropped, so a provider
> that bumps every `modified` timestamp during a reindex does not re-queue its
> whole catalogue. That comparison is against the `acquisitions` table, not
> `import_item.data` — `ImportItem.set_status` NULLs `data` on every terminal
> status, so for the oldest records there is nothing left there to compare.
>
> A consequence worth knowing before debugging: a parsing fix that changes the
> shape of a record but not its acquisitions will **not** re-stage anything.
> Delete the affected rows to force a re-import.

## Cron

Single pass per tick, so cron can see the exit status:

```cron
17 * * * * cd /openlibrary && python -m openlibrary.bookworm.cli harvest --ol-config /olsystem/etc/openlibrary.yml >> /var/log/bookworm-harvest.log 2>&1
```

The runner exits non-zero if **any** feed errored, and logs one line per feed.
Alerting should read those lines: a single provider failing while the others
work is the failure mode that otherwise goes unnoticed for weeks.

`--continuous --interval 3600` harvests in a loop instead. That is for a
supervised process or a soak test — under cron, prefer the default so a failure
is visible as a non-zero exit.

## Traps

**`--max-pages` is for testing only.** Truncating a crawl still advances the
cursor past the pages it did not fetch, permanently skipping them. Reset that
feed's `last_updated` afterwards.

**Only active feeds are harvested on a schedule.** A `pending` feed is skipped
by `harvest_all` but can still be run by name with `--provider`, which is what
makes the validate-then-activate sequence above possible. Rows written before
status gating existed carry no status and are treated as active.

**A feed can serve an empty catalogue at HTTP 200.** Lenny builds its OPDS feed
from Open Library's own search API, so an OL outage makes Lenny return 0
publications successfully (ArchiveLabs/lenny#208 — during the 2026-09-04
outage a library holding 96 items served `numberOfItems: 0`). Advancing the
cursor past that window loses it permanently. `_check_page_is_credible` rejects
a page serving zero publications that either carries a `rel=next` link or claims
a non-zero `numberOfItems`; the feed is reported as failed and the cursor stays
put. Any feed assembled from another service can fail this way.

**`modified` does not mean what you would assume, at least for Lenny.**
`metadata.modified` is Lenny's own `Item.updated_at`, bumped only when its
`items` row is UPDATEd. It does **not** move for:

- borrow or return — `Item.borrow()` inserts into `loans` without touching the
  item, so availability changes are invisible to the cursor;
- acquisition/borrow link changes — those are computed at feed-build time from
  the live loan count and never persisted;
- bibliographic metadata — that comes from Open Library live, so fixing a
  record in OL will not cause Lenny to re-offer it.

Consequences: `properties.availability.state` in a stored acquisition is a
snapshot from fetch time and can be up to a harvest interval stale — treat it as
advisory and re-check at click time, never display it as authoritative. And
anything OL-sourced (a missing author, say) needs a periodic full pass or a
re-derive on our side; the cursor will not deliver it.

**Cursor direction.** `modified_since` feeds advance to the *run start* time
(conservative: may re-fetch, never skips). Full-crawl feeds advance to the
newest `modified` seen, or to now when nothing was newer — so an idle
full-crawl feed's cursor moves forward on an empty run.

## Lenny specifics

Confirmed with the Lenny maintainer, 2026-09-06:

- **96 held, 95 published, 94 importable — three numbers, two unrelated
  causes.** Keep them apart or the accounting stops making sense.
  - **96 → 95.** One item Lenny holds never becomes a publication: an item whose
    `openlibrary_edition` does not resolve in OL search drops out of
    `_enrich_items` while `Item.count()` still counts it. Localized from outside
    by bisecting `modified_since` (`numberOfItems` respects the same filter, so
    the count-vs-publications gap is a probe): inserted ~04:28:48–52Z on
    2026-08-28, sorting alphabetically between "Moonbit" and "Multispecies
    Storytelling", the one 7.11s interval in an otherwise 1.67s-median bulk
    import. Consistent with #214 rather than with any cover filter, so treat it
    as a data-entry error on their side, not as pending a fix
    (ArchiveLabs/lenny#203, ArchiveLabs/lenny#214).
  - **95 → 94.** "LAMMA" (OL52247138M) *is* in the feed and *does* resolve; it
    is separately unimportable because it has no author in Open Library, which
    our validator requires. Different record, different cause.
  - So plan for 94, and expect `numberOfItems` to read one higher than the
    publications we actually get. Harmless today: `_check_page_is_credible`
    rejects a page only when it has **zero** publications alongside a non-zero
    `numberOfItems`, so a persistent gap of one does not trip it. Do not
    "tighten" that check into an equality comparison.
- **Their edition ids are not validated on entry.** `LennyAPI.add()` checks only
  `Item.exists(openlibrary_edition)` — a local duplicate check — and the route
  takes the edition number as a bare form field, so a typo'd, deleted or simply
  wrong id is accepted and served (ArchiveLabs/lenny#214). We rely on that id to
  pick the edition, so the catalog verifies it resolves before trusting it
  (`resolve_edition_ref`) and falls back to ordinary matching when it does not.
  Step 6b is where a bad id shows up, as a `would CREATE`. One such row is
  already predicted (see above), so `would CREATE: 1` at step 6b is the expected
  reading, not a surprise — but confirm it is *that* record before proceeding,
  and report anything beyond it to Lenny.
- **Never raise the page size.** We follow `rel=next` and never send a `limit`,
  inheriting their 50. A single `?limit=200` request returns HTTP 504; large
  single requests are the failure mode, not frequency. A 504 is safe for us:
  `raise_for_status()` runs before `resp.json()`, so it raises rather than
  parsing a partial body, and the cursor stays put.
- **`lenny_id` is assigned positionally** by zipping two separately-filtered
  queries. Verified sound today (all 95 `self` ids resolve to the right book),
  but if those lists ever diverge, publications inherit the next book's id --
  wrong borrow href, and a patron borrows the wrong book. We cannot detect a
  shift, only a collision, which `_warn_on_duplicate_ids` logs at ERROR.
- **Auth flow is in motion.** `properties.authenticate` points at the OPDS
  Authentication Document and is correct, but the flow behind it is being
  reworked (PKCE). Re-read the document; never hardcode anything inferred from
  the current version.

## Current feeds

| Provider | Cursor | Notes |
|---|---|---|
| `lenny` | `modified_since` | ~94 records. See the notes below before rolling out. |
| `project_gutenberg` | `modified_since` | ~78k items; seed the cursor |
| `betterworldbooks` | `client` (full crawl) | **not registered by default** — Cloudflare 403s our proxy egress. Register with `--provider betterworldbooks` once allowlisted. |

---

## Deploying Lenny to ol-home0

End-to-end runbook for the first live feed. Every step is reversible until step 7,
and nothing is harvested until step 6.

Prerequisites: PR #13565 merged or patch-deployed, and `feed_registry` present.

### 1. Patch deploy the code (skip if merged and released)

`patchdeploy.sh` applies a PR diff inside a container. The cron container is the
`cron-jobs` service on `ol-home0`:

```bash
# from a checkout on your workstation
SERVERS=ol-home0 SERVICE=cron-jobs ./scripts/deployment/patchdeploy.sh 13565
```

Undo with `APPLY_OPTIONS=-R` and the same command. Note the script's own warning:
patch deploys cannot rebuild js/css — irrelevant here, this PR is Python only.

Verify inside the container:

```bash
ssh ol-home0.us.archive.org
docker exec -it openlibrary-cron-jobs-1 bash
python -m openlibrary.bookworm.cli register --help   # should list --activate and --reseed
```

### 2. Confirm proxy egress works

The harvester reaches provider feeds only through Squid, authenticated. This must
return `200`, not `407` or a timeout:

```bash
curl -s -o /dev/null -m 20 -w "%{http_code}\n" https://lennyforlibraries.org/v1/api/opds
```

`407` means the container's proxy env carries no credentials. `000` with an empty
`remote_ip` on an HTTPS URL is a *masked* `407` — check with plain HTTP through
the proxy before concluding it is a network problem.

### 3. Create the tables

`acquisitions` may already exist from #12851 — check before creating:

```sql
\dt acquisitions
\dt feed_registry
```

Copy the DDL from `openlibrary/core/schema.sql` (`CREATE TABLE feed_registry`,
`CREATE TABLE acquisitions`, plus their indexes). Use the schema, not a ticket.

### 4. Register Lenny — it will NOT harvest yet

```bash
CFG=/olsystem/etc/openlibrary.yml
python -m openlibrary.bookworm.cli register --ol-config $CFG --show          # expect empty
python -m openlibrary.bookworm.cli register --ol-config $CFG --provider lenny
python -m openlibrary.bookworm.cli register --ol-config $CFG --show          # expect [pending]
```

A `pending` feed is skipped by scheduled runs, so this is safe even if a cron
entry already exists.

### 5. Validate against production without writing

```bash
python -m openlibrary.bookworm.cli harvest --ol-config $CFG --provider lenny --dry-run
```

Expect roughly `feed lenny: 94 records (dry run, nothing written)`. Confirm it
really wrote nothing:

```sql
SELECT count(*) FROM import_item;                                  -- 0
SELECT last_updated FROM feed_registry WHERE provider_name='lenny'; -- NULL
```

### 6. One real pass, by name

Still outside cron, because the feed is `pending`:

```bash
python -m openlibrary.bookworm.cli harvest --ol-config $CFG --provider lenny
```

```sql
SELECT b.name, i.status, count(*) FROM import_item i
  JOIN import_batch b ON b.id = i.batch_id
 GROUP BY b.name, i.status;
```

Expect ~94 rows in `lenny-opds` at `pending`.

### 6b. Optional: preview the match, without writing

**Not a gate.** We trust a feed's OLID.

Lenny's `self` link id IS the Open Library edition number, the feed is registered
with `local_id_is_ol_edition: true`, and `build_pool` therefore narrows the pool
to exactly that edition. So there is nothing to second-guess per record, and the
old "do not import until wrong-edition is zero" instruction that lived here was
circular anyway: it checked the match against the same id the matcher was told
to use, so it could only ever pass.

The trust decision is about the **instance**, not the record. If a Lenny
instance's ids turn out to be unreliable, the answer is to stop trusting that
instance — deactivate the feed — not to verify each of its records forever. The
signal to watch is the per-pass count of ids that do not resolve, which
`add_book` logs with the offending `source_records` value:

```bash
grep "does not resolve to an edition" /var/log/import-bot.log | grep lenny: | wc -l
```

A handful is data entry (ArchiveLabs/lenny#214: their `add()` checks only for a
local duplicate and never validates that `OL<id>M` exists, so a typo'd or
deleted id is accepted, stored and served). A large or growing share means the
instance's ids are not trustworthy — deactivate and talk to the operator.

The preview script is still useful as a diagnostic when something looks wrong,
because it reports the catalog's decision with **zero** writes (`load(rec,
save=False)` makes the full match/merge decision but never reaches
`_save_acquisitions`, and both `add_cover` call sites are gated on `save`):

```bash
python -m openlibrary.bookworm.cli preview --ol-config $CFG --provider lenny
```

Read it as: `would CREATE` means the named edition does not resolve — a bad id
at the source, and the catalog deliberately falls back to ordinary matching
rather than saving against a key that is not there. `matched a DIFFERENT
edition` on a flagged feed means the id is not reaching the catalog at all —
check the registered row actually carries `local_id_is_ol_edition` (`--show`),
because config added to `FEEDS` after a feed was first registered is **not**
applied to the existing row.

Why any of this matters for feeds that *don't* name an edition: `build_pool`
matches on title/ISBN/LCCN/OCLC/ocaid and ignores `identifiers.*`, and these
collections are the most duplicated records in the catalog — Frankenstein spans
2,538 works, Alice's Adventures in Wonderland 3,547 editions in its top work
alone. Title matching finds a large pool for essentially every record and picks
one, and a wrong pick reports no error. That gap is tracked separately, because
fixing `build_pool` in general changes matching for every import path in Open
Library.

### 7. Let ImportBot drain, then read the status split

For Lenny this can be measured **exactly**, not statistically: its `self` link id
IS the Open Library edition number (`/opds/51008637` -> `OL51008637M`, verified
against the live feed). So we know which edition every record should have
matched, and any other outcome is definitely wrong rather than merely suspicious:

```sql
SELECT
  CASE
    WHEN i.ol_key = '/books/OL' || replace(i.ia_id, 'lenny:', '') || 'M'
      THEN 'matched the self-link edition (correct)'
    WHEN i.ol_key IS NOT NULL
      THEN 'matched a DIFFERENT edition (wrong)'
    ELSE 'no ol_key'
  END AS outcome,
  i.status,
  count(*)
FROM import_item i JOIN import_batch b ON b.id = i.batch_id
WHERE b.name = 'lenny-opds'
GROUP BY 1, 2 ORDER BY 3 DESC;
```

- `matched the self-link edition` + `found`/`modified` → correct. Proceed.
- **`created`** → we made a NEW edition for a book Lenny already references by
  OL id. Lenny keeps pointing at the old edition while our acquisition hangs off
  the new one, and the two permanently disagree about which record is the book.
  **Stop.** This is worse than a no-match.
- **`matched a DIFFERENT edition`** → the acquisition is attached to the wrong
  book. Stop.

Also confirm the provider id persisted on the edition, because without it
nothing on our side records which Lenny holding an acquisition came from and
re-harvesting cannot reconcile:

```bash
curl -s https://openlibrary.org/books/OL51008637M.json | python3 -c \
  "import json,sys; print(json.load(sys.stdin).get('identifiers', {}))"
```



`build_pool` matches on title/ISBN/LCCN/OCLC/ocaid and ignores
`identifiers.*`, so matching here is heuristic even though the record carries an
exact edition id. That gap is the thing this step measures.

Then confirm acquisitions actually landed:

```sql
SELECT provider_name, count(*) FROM acquisitions GROUP BY provider_name;
SELECT data FROM acquisitions LIMIT 1;   -- {"acquisitions": [...]}
```

### 8. Hand it to cron

```bash
python -m openlibrary.bookworm.cli register --ol-config $CFG --provider lenny --activate
```

Then the crontab entry on the cron container:

```cron
17 * * * * cd /openlibrary && python -m openlibrary.bookworm.cli harvest --ol-config /olsystem/etc/openlibrary.yml >> /var/log/bookworm-harvest.log 2>&1
```

Single pass per tick so cron sees the exit status. It exits non-zero if **any**
feed errored, and logs one line per feed.

### 9. Confirm steady state after two ticks

```
feed lenny: 0 records
```
or a small `unchanged` count. If you see a large `refreshed` count on every tick,
change detection is not working — that is the signal something regressed, and it
means the import queue is churning.

### Rolling back

- Stop harvesting without losing anything: set the feed back to pending —
  `UPDATE feed_registry SET data = jsonb_set(data, '{status}', '"pending"') WHERE provider_name='lenny';`
- Un-apply the code: `APPLY_OPTIONS=-R SERVERS=ol-home0 SERVICE=cron-jobs ./scripts/deployment/patchdeploy.sh 13565`
- Re-harvest from scratch: `DELETE FROM import_item WHERE batch_id = (SELECT id FROM import_batch WHERE name='lenny-opds');`
  then `UPDATE feed_registry SET last_updated = NULL WHERE provider_name='lenny';`
