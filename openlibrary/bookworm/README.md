# BookWorm feed harvest — operator guide

Harvests OPDS 2.0 feeds from book providers into Open Library's import queue.

```
provider feed ──► bookworm_harvest ──► import_item ──► ImportBot ──► catalog ──► acquisitions
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
| `scripts/bookworm_harvest.py` | the cron entrypoint |
| `scripts/bookworm_register.py` | register feeds (feed definitions live here, in git) |

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
python scripts/bookworm_register.py --ol-config $CFG --show

# 2. register (pending — cron will not touch it yet; idempotent, and it never
#    rewinds a cursor that has already progressed)
python scripts/bookworm_register.py --ol-config $CFG --provider lenny

# 3. validate: fetches and parses, writes nothing, leaves the cursor alone
python scripts/bookworm_harvest.py --ol-config $CFG --provider lenny --dry-run

# 4. one real pass by name (still pending, so cron stays out of the way)
python scripts/bookworm_harvest.py --ol-config $CFG --provider lenny

# 5. happy with what landed? hand it to cron
python scripts/bookworm_register.py --ol-config $CFG --provider lenny --activate
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
python scripts/bookworm_register.py --ol-config $CFG \
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

> **Re-harvesting does not update already-staged rows.** Because dedup is by
> `ia_id` alone, a record whose price, format or acquisition URL changes is
> correctly re-harvested by the cursor and then dropped as "already present".
> The cursor can only ever add records that have never been seen. If a parsing
> fix needs to reach rows that are already staged, delete them first.

## Cron

Single pass per tick, so cron can see the exit status:

```cron
17 * * * * cd /openlibrary && python scripts/bookworm_harvest.py --ol-config /olsystem/etc/openlibrary.yml >> /var/log/bookworm-harvest.log 2>&1
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

**Cursor direction.** `modified_since` feeds advance to the *run start* time
(conservative: may re-fetch, never skips). Full-crawl feeds advance to the
newest `modified` seen, or to now when nothing was newer — so an idle
full-crawl feed's cursor moves forward on an empty run.

## Current feeds

| Provider | Cursor | Notes |
|---|---|---|
| `lenny` | `modified_since` | verified server-side filtering (96 items unfiltered, 0 since 2026-09-01) |
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
python scripts/bookworm_register.py --help   # should list --activate and --reseed
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
python scripts/bookworm_register.py --ol-config $CFG --show          # expect empty
python scripts/bookworm_register.py --ol-config $CFG --provider lenny
python scripts/bookworm_register.py --ol-config $CFG --show          # expect [pending]
```

A `pending` feed is skipped by scheduled runs, so this is safe even if a cron
entry already exists.

### 5. Validate against production without writing

```bash
python scripts/bookworm_harvest.py --ol-config $CFG --provider lenny --dry-run
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
python scripts/bookworm_harvest.py --ol-config $CFG --provider lenny
```

```sql
SELECT b.name, i.status, count(*) FROM import_item i
  JOIN import_batch b ON b.id = i.batch_id
 GROUP BY b.name, i.status;
```

Expect ~94 rows in `lenny-opds` at `pending`.

### 7. Let ImportBot drain, then read the status split

This is the step that decides whether the rest of the rollout is safe.

```sql
SELECT i.status, count(*) FROM import_item i
  JOIN import_batch b ON b.id = i.batch_id
 WHERE b.name = 'lenny-opds' GROUP BY i.status;
```

- mostly `found` / `modified` → feed records are matching existing editions. Good.
- mostly `created` → the catalog is creating new editions for books Open Library
  already has. **Stop.** `build_pool` matches on title/ISBN/LCCN/OCLC/ocaid and
  ignores `identifiers.lenny`, so provider-specific pooling is needed first (see
  `find_wikisource_src` for the precedent). Continuing would duplicate editions
  at Gutenberg scale.

Then confirm acquisitions actually landed:

```sql
SELECT provider_name, count(*) FROM acquisitions GROUP BY provider_name;
SELECT data FROM acquisitions LIMIT 1;   -- {"acquisitions": [...]}
```

### 8. Hand it to cron

```bash
python scripts/bookworm_register.py --ol-config $CFG --provider lenny --activate
```

Then the crontab entry on the cron container:

```cron
17 * * * * cd /openlibrary && python scripts/bookworm_harvest.py --ol-config /olsystem/etc/openlibrary.yml >> /var/log/bookworm-harvest.log 2>&1
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
