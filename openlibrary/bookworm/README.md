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

Register only when you are ready for the feed to run: `FeedRegistry.all()` has
no status filter, so **a registered feed is live on the next harvest.** There is
no staged state; `--dry-run` is how you validate first.

```bash
CFG=/olsystem/etc/openlibrary.yml

# 1. what is registered now
python scripts/bookworm_register.py --ol-config $CFG --show

# 2. register one feed (idempotent; never rewinds a cursor that has progressed)
python scripts/bookworm_register.py --ol-config $CFG --provider lenny

# 3. validate before it can write: fetches and parses, writes nothing,
#    leaves the cursor alone
python scripts/bookworm_harvest.py --ol-config $CFG --provider lenny --dry-run

# 4. one real pass, then look at what landed
python scripts/bookworm_harvest.py --ol-config $CFG --provider lenny
```

```sql
SELECT b.name, count(*) FROM import_item i
  JOIN import_batch b ON b.id = i.batch_id
 WHERE b.name LIKE '%-opds' GROUP BY b.name;
```

### Sizing the first run

An unseeded feed backfills its whole history. Gutenberg carries ~78k items at
25 per page — roughly 3,100 sequential fetches. Seed the cursor to bound it;
the feed catches up on its own from there:

```bash
python scripts/bookworm_register.py --ol-config $CFG \
    --provider project_gutenberg --since 2026-08-28
```

`--since` applies **only on first registration**, so it cannot be used to rewind
a feed that is already running. To deliberately rewind one, update
`feed_registry.last_updated` directly.

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

**Registering is going live.** See above.

**`data.status` does nothing.** It is recorded but not enforced; it does not
gate harvesting.

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
