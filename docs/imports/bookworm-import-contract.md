# BookWorm import contract — reconciliation before freeze

> **Status:** working draft — unit 2 of the #12655 decomposition
> **Sources:** `openlibrary/core/schema.sql` and `schema.py` at `origin/master`; #12655 proposed DDL; #13206 (open draft)
> **Last ingested:** 2026-09-20

Wave 1 of the BookWorm decomposition cannot start until the schema and API
contract are frozen, because every unit in it binds to those shapes. This page
is the reconciliation that has to happen first.

**This is ratification, not authoring.** #12655 carries a *proposed* schema;
#13206 and subsequent merges carry *built* tables. Nobody has compared them.
Writing the contract from the proposal alone would inherit conflicts that the
built code has already resolved differently — which is the same failure as
planning from the epic's stale checkboxes, one level down.

## What is actually built (`origin/master`)

Two tables exist that postdate #12655 and are unmentioned by it:

```sql
CREATE TABLE feed_registry (
    id serial primary key,
    provider_name text not null,
    feed_type text not null default 'opds',
    url text not null,
    last_updated timestamp without time zone default null,  -- harvest cursor
    data jsonb not null default '{}'::jsonb,
    created timestamp without time zone default (current_timestamp at time zone 'utc'),
    updated timestamp without time zone default (current_timestamp at time zone 'utc'),
    UNIQUE (provider_name, url)
);

CREATE TABLE acquisitions (
    id serial primary key,
    work_id integer not null,
    edition_id integer not null,
    provider_name text not null,
    local_id text not null,
    data jsonb not null,
    created timestamp ... , updated timestamp ...,
    UNIQUE (local_id, provider_name)
);
```

Note `feed_registry` — **not** `tbp_feed_registry`, which is what #13206's
description still calls it. The name drifted between prototype and merge and
the draft PR was never updated. That is the drift this page exists to catch.

## Proposal vs. built — the deltas a freeze must settle

| # | #12655 proposes | Built convention | Decision needed |
|---|---|---|---|
| 1 | `import_item.data` is `jsonb` | today `text`; both new tables use `jsonb` | Direction is settled — `jsonb`. Ratify. |
| 2 | `import_item.id` is `bigserial` | both new tables use `serial` | Genuine conflict. `import_item` is the table that grows to millions; `bigserial` is right *there* and inconsistent with its neighbours. |
| 3 | `ia_id` renamed to `source_id` | still `ia_id` everywhere | Rename touches every producer and `Batch.add_items`. Worth it, but it is a migration, not a field rename. |
| 4 | `timestamp default now()` | `timestamp without time zone default (current_timestamp at time zone 'utc')` | **Take the built convention** — but for the reason measured below, not the one first written here. |
| 5 | `created` / `updated` pair | built tables carry both | Proposal has only `added_time` / `import_time`. Adopt the pair. |
| 6 | `import_item_history`, `import_source` | do not exist | Genuinely new. |

### Delta 4, measured rather than reasoned

An earlier revision of this page said `now()` is "timezone-aware local time"
and that mixing it with the built convention is "a bug factory." **That was
asserted, not measured, and it is half wrong.** Run against the live
`acqtest-db-1`:

```
SHOW timezone                              -> Etc/UTC
now()                                      -> 2026-09-21 07:00:17.728743+00
current_timestamp AT TIME ZONE 'utc'       -> 2026-09-21 07:00:17.728743
pg_typeof, respectively                    -> timestamptz | timestamp
```

**Same instant, same digits. The values do not diverge.** What diverges is the
**type**: `now()` yields `timestamptz`, the built convention yields
`timestamp`.

So the real hazard is narrower and more durable than "wrong times":

1. **Type divergence across tables in one schema.** Following the epic gives
   `import_item` a `timestamptz` column while `acquisitions` and
   `feed_registry` use `timestamp`. Comparisons and joins between the two
   apply session-timezone conversion — that is where a bug would actually
   live, not in the stored value.
2. **The agreement today depends on the server being UTC**, which is a
   deployment property and not a schema guarantee. Under a non-UTC session
   the rendering diverges and the mixed-type comparison shifts.

Still take the built convention — but because it keeps one type across the
schema and does not rely on a deployment setting, not because the epic's
version stores the wrong time. It does not.

**Why this correction exists:** the contract was specified and unexercised.
One query against a running database corrected its headline claim. A frozen
contract that has never been run against a real engine is a specification with
an untested assumption in it, and this one had an overstatement in the delta
it called most important.

## Exercising the DDL — four more findings, one of which reverses delta 4

The proposed DDL had never been executed. Run against `acqtest-db-1` inside
`BEGIN … ROLLBACK` (persists nothing), plus compared against the **actual**
current DDL in `core/schema.py:89-106` rather than against the epic's prose
description of it. That second part is where the misses were: the earlier
comparison took #12655's word for what `import_item` looks like today.

**1. The DDL is valid.** All four tables and the index create cleanly. The
contract is executable, which was not previously known.

**2. `UNIQUE (batch_id, source_id)` does not dedup when `source_id` is NULL.**
Two rows of `(1, NULL)` both inserted. Standard SQL — NULLs are not equal to
each other. This is **pre-existing** (`ia_id text` is nullable today with the
same constraint shape), not a regression. But the pipeline *advertises*
idempotence — "`source_records[0]` is the deduplication key; submitting the
same value twice is idempotent" — and that guarantee is unenforceable at the
database level while the column is nullable. #12655 even says it is dropping
"`ia_id` uniqueness which we'll enforce differently," then declares the same
constraint shape. **Make `source_id NOT NULL`.**

**3. The proposal silently drops the `comments` column.** Present in the
current table, absent from the epic's DDL, unmentioned in its text.

**4. The proposal drops three of four indexes.** Today:
`import_item_batch_id`, `import_item_import_time`, `import_item_status`,
`import_item_ia_id`. The epic proposes one composite
`(status, added_time)`. Dropping the `ia_id`/`source_id` index is the
alarming one — that is the dedup lookup path, on the table the epic itself
describes as accumulating millions of rows.

**5. Delta 4 is worse than recorded, and in the other direction.**
`core/schema.py:92` shows `import_item.added_time` **already uses**
`timestamp without time zone default (current_timestamp at time zone 'utc')`.
So the epic's `timestamp default now()` is not "diverging from a convention
its siblings adopted later" — it would **regress the very table it is
rewriting**, from the UTC convention to `timestamptz`. The ruling is
unchanged; the reason is now much stronger.

Findings 3, 4 and 5 were all invisible while comparing the epic's proposal
against the epic's own description of current state. They required reading
the DDL that actually ships.

## Running the contract in a throwaway database — two more findings

Stood up a disposable `imports_probe` database in a real Postgres, applied
the frozen DDL with all rulings, and ran the lifecycle the epic describes.
This is the venue test: not SQLite, not a fixture — the engine it ships on.
Database dropped afterwards.

**1. `INSERT INTO import_item_history SELECT * FROM import_item` fails.**
`ERROR: INSERT has more expressions than target columns`. The epic describes
archival as moving completed rows to history, and the obvious implementation
does not work — history deliberately omits `data`, plus `added_time` and
`comments`. Columns must be named explicitly. Loud failure, easily fixed,
but worth knowing before someone writes it.

**2. The archival insert silently corrupts on a column-order mistake.**
This is the one that matters. `import_item_history` has **four consecutive
`text` columns** — `source_id, ol_key, status, error` — and `import_item`
holds them in a different order. Swapping two in the SELECT list:

```sql
-- source_id and ol_key transposed
INSERT INTO import_item_history (id,batch_id,source_id,ol_key,status,error,import_time,submitter)
SELECT id,batch_id,ol_key,source_id,status,error,import_time,submitter FROM import_item ...;
```
```
INSERT 0 1
 id |  source_id  |   ol_key
----+-------------+------------
  3 | /books/OL3M | bookdash:c
```

**No error.** The row is archived with the OL key stored as the source id and
vice versa. `source_id` is the pipeline's deduplication key, so a history
table corrupted this way makes imported records look un-imported — and the
failure is invisible until something queries history for dedup.

**Mitigation the freeze should carry:** a `CHECK` that `ol_key` matches
`^/books/OL` and that `source_id` does not, or reorder `import_item_history`
to match `import_item`'s column order so a positional mistake is impossible
rather than merely unlikely. The first is better — it catches the error at
write time regardless of how the insert is written.

Neither finding is visible from reading the DDL. Both took nine lines of SQL
against a real engine.

## Failure paths — the dedup invariant is not in the schema

Ran the *unhappy* lifecycle in a throwaway Postgres, after the happy one. The
corruption finding came from the happy path; this came from the unhappy one,
and it is the more dangerous of the two because nothing fails.

**The constraint is strictly weaker than the invariant the application
maintains, and BookWorm is exactly the change that exposes the difference.**

| Layer | Dedup scope | Evidence |
|---|---|---|
| Application | **global** across all batches | `core/imports.py:89-97` — `dedupe_items` runs `SELECT ia_id FROM import_item WHERE ia_id IN $ia_ids` with **no `batch_id` filter** |
| Database | **per batch only** | `UNIQUE (batch_id, source_id)` |

Measured:

```
same source_id, same batch      -> ERROR: duplicate key ... (1, lenny:123)
same source_id, DIFFERENT batch -> INSERT 0 1     <-- accepted
```

So `lenny:123` exists twice, in two harvest runs. Today this is invisible
because everything reaches the table through `Batch.add_items`, which dedups
globally before inserting. **BookWorm's entire purpose is a new service
accepting `POST /v1/imports/batch`.** If that service inserts directly rather
than through `add_items`, the global dedup silently disappears and only the
weaker per-batch constraint remains — so a record re-harvested on a later run
(an overlapping feed cursor, a re-run after a partial failure, two feeds
carrying the same ISBN) produces duplicate import items and duplicate import
attempts. Nothing errors.

**What the freeze must therefore say, and a DDL cannot express:** dedup is
**global on `source_id`** and is the *service's* responsibility. A global
`UNIQUE (source_id)` is the wrong fix — it would block legitimate re-import
after a failure, and #12655 explicitly drops `ia_id` uniqueness intending to
"enforce it differently." This is that enforcement, and it was never
specified.

This is the class of gap that only appears in the unhappy path: the happy
path inserts each record once and everything looks correct.

## The `text` → `jsonb` migration is all-or-nothing and will fail on one bad row

Delta 1 ratified `data jsonb`, which is right. **What that ratification did
not carry is that #12655 also calls for "a migration to copy in-flight
`import_item` rows," and the cast is the migration.** Measured:

```sql
ALTER TABLE import_item ALTER COLUMN data TYPE jsonb USING data::jsonb;
ERROR:  invalid input syntax for type json
DETAIL:  The input string ended unexpectedly.
```

Per-value, tested individually:

| `data` value | `::jsonb` |
|---|---|
| `'{"title":"fine"}'` | ok |
| `NULL` | ok — stays NULL |
| `''` (empty string) | **ERROR** |
| `'  '` (whitespace) | **ERROR** |
| `'not json at all'` | **ERROR** |
| `'null'` (literal text) | **silently becomes JSON `null`** |

Two distinct hazards:

**1. One bad row kills the whole migration.** `ALTER TABLE … USING` is
atomic — on a table the epic itself describes as holding millions of rows, it
scans everything and then rolls the lot back on the first unparsable value.
The likely culprit is not garbage but the **empty string**: `data text`
permits `''` and `data jsonb` does not. Nothing in today's writers obviously
produces `''` — `add_items` writes `json.dumps(...)`, `set_status` writes
NULL — but that is an argument about current writers, not about millions of
historical rows written by several writers over years. **The migration needs
a pre-flight pass** (`SELECT id FROM import_item WHERE data IS NOT NULL AND
data !~ '^\s*[\[{"]'` or an explicit validation query) rather than an
optimistic cast.

**2. `'null'` migrates silently and changes meaning.** The literal four-char
string becomes JSON `null`, which is *not* SQL `NULL`. Any downstream check
of `data IS NULL` — and `set_status` makes that state meaningful — would stop
seeing such a row. This one produces no error at any point.

Neither is visible from the DDL. Both come from running the migration the
epic describes rather than the schema it declares.

## A prior staging schema exists, and it contradicts two of my rulings on purpose

**Found after declaring this contract complete**, by running "who already owns
this?" on the last item I had not checked. My unit-1 reconciliation covered
`12844/bookworm-service` and never looked at
**`12844/feed-registry-acquisitions`** (#13206, open draft, 15 commits, **343
behind master**). That branch carries `docker/staging-db/schema.sql` —
a staging database schema for exactly this contract — plus
`core/{bookworm,feeds,staged,tbp}.py`, `catalog/opds2.py`, and an admin
registry template. None of it is on master.

**One ruling it corroborates independently.** It uses
`timestamp without time zone default (current_timestamp at time zone 'utc')`
throughout — the UTC convention, chosen by a different author for a different
reason. Delta 4 now has two independent sources.

**Two rulings it contradicts, and its reason is better than mine.** Its
`import_item` is `id serial`, `ia_id text`, `data text`, `UNIQUE (batch_id,
ia_id)` — i.e. **a deliberate mirror of the main schema**, with the rationale
in its own header comment:

> *"the bookworm-side import queue; manage-imports drains BOTH these and the
> legacy main-schema tables (dual-source)."*

**That is a design argument I did not have.** If the staging tables are
byte-identical to the main ones, `manage-imports` drains both with one code
path. My rulings — `ia_id` → `source_id`, `text` → `jsonb`, `serial` →
`bigserial` — each make the two schemas diverge, and **every divergence
forces the dual-source drain to branch.** #12655 proposes those renames
without ever mentioning that cost.

This is a genuine tension, not a mistake on either side:

| | Mirror the main schema | Adopt the epic's renames |
|---|---|---|
| dual-source drain | one code path | two, or a translation layer |
| `jsonb` queryability | no | yes |
| `source_id` clarity, `NOT NULL` dedup | no | yes |
| migration of in-flight rows | trivial | needs the cast (and its hazards) |

**Unresolved. It needs whoever owns `manage-imports` to weigh the drain cost**,
and I am not ruling it from one side of the evidence having just discovered
the other side existed.

**And a table I omitted entirely:** `tbp_staged_record` — the raw normalized
feed buffer with `record jsonb`, `acquisition jsonb`, `status staged |
promoted | failed`, `UNIQUE (provider_name, local_id)`. #12655 calls for a
"raw `staged_record` buffer" and my frozen DDL does not have it. The
prototype's version also carries the acquisition metadata *alongside* the
record so a post-import step can attach it once the edition exists — which is
precisely the problem the cover fix could not solve, solved.

### Reconciliation of #13206, completed — what to revive and what to ignore

Verified per module, not inferred from filenames (master relocated things
into `bookworm/`, so a literal path search returns false negatives):

| Prototype (`12844/feed-registry-acquisitions`) | Master | Verdict |
|---|---|---|
| `core/tbp.py::FeedRegistry` | `bookworm/registry.py::FeedRegistry` | **superseded** — same class, same `_utcnow` helper; relocated and evolved |
| `catalog/opds2.py` | `bookworm/opds.py` | **superseded** — OPDS parsing landed |
| `core/staged.py::StagedRecord` | *none* | **not carried forward** |
| `core/bookworm.py` | *none* | **not carried forward** |
| `core/feeds.py` | *none* | **not carried forward** |
| `docker/staging-db/schema.sql` | *none* | **not carried forward** |
| `templates/admin/imports_registry.html` | *none* | **not carried forward** |

**The pattern is exact and consistent with everything else on this page: the
harvest-side landed, the staging-and-service side did not.** Registry and
OPDS parsing are on master under new names. The staging database, the
`staged_record` buffer, the service module and the operator UI are all still
only on a 343-behind draft.

So an implementer should **revive** `core/staged.py`, `docker/staging-db/schema.sql`
and the admin template as starting points — they are prior art for exactly
the unbuilt half — and **ignore** `core/tbp.py` and `catalog/opds2.py`, which
would duplicate master.

**Method note, because it is the lesson.** I declared this contract complete
after five venues and eight findings, then found a prior implementation of the
same thing by asking an ownership question rather than a technical one. The
audit was thorough and looked in the wrong place. *Searching for prior work is
not the same activity as verifying your own* — and the second cannot
substitute for the first no matter how rigorously it is done.

## THE FROZEN DDL

Every finding and ruling on this page, applied. **This is the artifact to
implement** — everything below it is the reasoning that produced it. Differs
from #12655's proposal in nine places, each annotated with why.

> **Executed, not just written.** Run verbatim against a real Postgres: all
> four tables and five indexes create cleanly. The `[7]` CHECK constraints
> were then tested against both cases, because a fix that has never been
> exercised is the exact defect this page catalogues:
>
> - **correct archival insert → succeeds** (`source_id=bookdash:c`,
>   `ol_key=/books/OL3M`)
> - **transposed insert → `ERROR: violates check constraint
>   "history_ol_key_shape"`**, `DETAIL: Failing row contains (101, 1,
>   /books/OL3M, bookdash:c, …)`
>
> Fails the bad case, passes the good one — the same discriminating standard
> applied to #13395's tests, rather than merely "it runs." Probe database
> dropped.

```sql
CREATE TABLE import_batch (
    id          serial primary key,
    name        text,
    submitter   text,
    submit_time timestamp without time zone
                default (current_timestamp at time zone 'utc')   -- [1]
);

CREATE TABLE import_item (
    id          bigserial primary key,                            -- [2]
    batch_id    integer references import_batch,
    added_time  timestamp without time zone
                default (current_timestamp at time zone 'utc'),   -- [1]
    import_time timestamp without time zone,
    status      text default 'pending',
    error       text,
    source_id   text NOT NULL,                                    -- [3]
    data        jsonb,                                            -- [4]
    ol_key      text,
    comments    text,                                             -- [5]
    submitter   text,
    UNIQUE (batch_id, source_id)
);
CREATE INDEX import_item_batch_id    ON import_item (batch_id);   -- [6]
CREATE INDEX import_item_import_time ON import_item (import_time);
CREATE INDEX import_item_status      ON import_item (status);
CREATE INDEX import_item_source_id   ON import_item (source_id);
CREATE INDEX import_item_status_added ON import_item (status, added_time);

CREATE TABLE import_item_history (
    id          bigint primary key,
    batch_id    integer,
    source_id   text NOT NULL,
    ol_key      text,
    status      text,
    error       text,
    import_time timestamp without time zone,
    submitter   text,
    CONSTRAINT history_ol_key_shape   CHECK (ol_key IS NULL OR ol_key ~ '^/books/OL'),   -- [7]
    CONSTRAINT history_source_id_shape CHECK (source_id !~ '^/books/OL')                 -- [7]
);

CREATE TABLE import_source (
    id          serial primary key,
    name        text unique,
    ol_account  text,
    trust_level text default 'review',
    created_at  timestamp without time zone
                default (current_timestamp at time zone 'utc')    -- [1]
);
```

**[1] UTC convention, not `now()`.** Measured: values agree on a UTC server
but the *types* differ — `now()` is `timestamptz`, this is `timestamp`. Mixing
them across one schema makes joins apply session-timezone conversion. Also
`import_item.added_time` **already** uses this today, so the epic's `now()`
would regress the table it rewrites.

**[2] `bigserial`** — kept from the proposal. The one place its inconsistency
with `serial` siblings is justified: this is the table that grows to millions.

**[3] `NOT NULL`** — without it `UNIQUE (batch_id, source_id)` does not dedup,
because NULLs are never equal. Demonstrated: two `(1, NULL)` rows both insert.
The pipeline advertises idempotence on this key.

**[4] `jsonb`** — but see the migration hazard above. The cast is atomic and
one `''` or non-JSON row across millions fails the whole thing; `'null'`
migrates silently to JSON `null`, which is not SQL `NULL`. **Requires a
pre-flight validation pass, not an optimistic `USING data::jsonb`.**

**[5] `comments` retained** — present today, silently dropped by the proposal.

**[6] All four existing indexes retained**, plus the proposal's new composite.
The proposal drops three, including `source_id` — the dedup lookup path, on
the table it calls millions of rows.

**[7] CHECK constraints on the history table.** `import_item_history` has four
consecutive `text` columns in a different order from `import_item`, so a
transposed archival insert succeeds **silently** with the OL key stored as
`source_id`. Demonstrated. These catch it at write time regardless of how the
insert is written.

**[8] Not expressible in DDL — the service must enforce it.** Dedup is
**global on `source_id`**, not per batch. `core/imports.py:89-97` dedups
across all batches with no `batch_id` filter; the constraint is per-batch
only. A service inserting directly loses the global guarantee silently. A
global `UNIQUE (source_id)` is the wrong fix — it blocks legitimate re-import
after failure.

**[9] Not expressible in DDL — three unowned deploy steps.** Provision the
database, apply this DDL, add the nginx route. None exist in any repo.

## Rulings

These were first written here as "open questions the freeze must answer,"
which was the same bundling error one level down: they were posed without
asking *who* answers them. Two are domain calls belonging to the imports lead,
not to Mek. Decided below, with the evidence.

### 1. Only the QUEUE tables move. `acquisitions` and `feed_registry` stay in
the main schema. **Ruled** — this narrows #12655's "separate DB" premise
materially, so the evidence matters:

| Table | Read on a request path? | Verdict |
|---|---|---|
| `acquisitions` | **Yes** — `/search.json` weaves `editions.opds_acquisitions` at request time | stays |
| `feed_registry` | **Yes** — `plugins/importapi/import_validator.py:177` calls `FeedRegistry.provider_names()` while validating records; also read by `catalog/add_book/` on ImportBot's path | stays |
| `import_batch`, `import_item` | no — queue only | **moves** |
| `import_item_history`, `import_source` (new) | no | **moves** |

Moving either of the first two to an isolated staging DB puts a
**cross-database call on a request path** — the search path for
`acquisitions`, and every validated import record for `feed_registry`.
`feed_registry` is the less obvious one and the reason this needed checking
rather than reasoning: it looks like harvest-time-only state, and it is not.
`acquisitions` is additionally already on the single shared synchronous
connection, so a cross-DB hop there compounds a known problem.

So BookWorm owns the **queue**, not all import-adjacent data. Three consumers
span the boundary (`bookworm`, `import_validator`, `add_book`), and the split
is drawn so that none of them crosses it on a request.

### 2. Route surface: ratify #12655's MVP list unchanged. **Ruled.**
`/v1/imports/batch`, `/v1/imports/batch/{id}`, `/v1/imports/items/pending`,
`/v1/lookup/isbn/{isbn}`. None are built; none conflict with anything built;
there is no reason to redesign them at freeze time.

### 3. The CLI is a first-class client of the same contract, not a bypass.
**Ruled.** Mek: BookWorm is a service **and** a CLI for manual batch
invocation. Master's `bookworm/cli.py` is the CLI half and it currently
reaches the database directly. Once the queue tables move it must go through
the service like any other client — otherwise the contract has two
implementations and they will drift, which is exactly what
`tbp_feed_registry` → `feed_registry` already demonstrates at the table-name
level.

### Still genuinely Mek's

Nothing in the schema. The one open item is **who runs the freeze into code**
— this page is the specification; turning it into DDL and Pydantic models is
an atomic-agent task and needs the spawn decision.

## The contract says nothing about how any of it reaches production

A reading-column gap in this page, found by asking the question rather than
re-reading the specification. **There is no DDL-migration mechanism in this
repository.** Verified:

- `openlibrary/core/schema.sql` is applied by exactly one thing:
  `docker/ol-db-init.sh:10`, at database **init**.
- `scripts/migrations/` holds five scripts and **zero** contain
  `CREATE TABLE` or `ALTER TABLE` — they are all data migrations.

So a table added to `schema.sql` reaches a *fresh* database and nowhere else.
Production has an existing database. The precedent for a new table is that an
operator runs the DDL by hand, and nothing in the repo records that this is
required.

**This bites harder here than for a single new table, because the contract
specifies a new *database*.** `ol-db-init.sh` creates `openlibrary` and
`coverstore`. Nothing creates `openlibrary_imports`. So the deploy story for
this contract has **three** unowned steps, none written down anywhere:

1. provision the `openlibrary_imports` database
2. apply its DDL to that database
3. add the nginx reverse-proxy location for the service

Step 3 was found by asking the same deployment question one layer up. #12655
says BookWorm is "reverse-proxied at e.g. `/api/bookworm/` by the OL nginx
config (never directly exposed to the public)." That config lives in
**olsystem**, and `grep -ril bookworm --include='*.conf'` there returns
**zero** — consistent with `grep -il "bookworm\|harvest"` returning zero
across the entire olsystem tree.

So the whole production-side surface of this epic is unwritten: no database,
no DDL, no route. Each lives in olsystem or in an operator's hands, and the
application repo gives no hint that any of them is required.

**The route surface itself is fine** — verified, not assumed: no `/v1/` path
exists anywhere in the codebase, and `asgi_app.py` mounts its routers without
prefixes, so #12655's proposed routes collide with nothing. Ratifying them
unchanged (ruling 2) holds. The gap is not the routes; it is that nothing
routes *to* them.

An agent handed this contract builds against SQLite or a fresh docker
Postgres, passes every test, and produces something that has never met a
production database — which is the same shape as the `provider_tokens` case
in the Lenny division, and the fourth instance across two divisions.

**It also strengthens ruling 1 independently.** `acquisitions` and
`feed_registry` demonstrably exist in production — there are rows in
`acquisitions` and feeds are registered — so someone already crossed this gap
by hand for them. Moving either to a new database would mean repeating that
manual step *and* a data migration, on tables that are read on request paths.
They stay.

**What the freeze must therefore carry, and did not:** who provisions the
database, who applies the DDL, and how that is recorded so the next table does
not rediscover this. Until that is answered the contract is specified but
undeployable, and no amount of local testing will reveal it.

## Constraint inherited from #13395

The unbounded row fetch in `acquisitions.get_by_editions` (no SQL `LIMIT`, one
shared synchronous connection) **must be fixed before harvest volume scales**.
Since BookWorm is the work that scales harvest volume, that follow-up is a
prerequisite of this epic rather than a parallel nicety. See
[[pr-13395-state]].

---

## A third design exists, in another org — and it refutes marker [8]

Found 2026-09-27 by ada-8f, at `ArchiveLabs/openlibrary-bookworm` (**public**,
`feat/mvp-batch-import-api`, **PR #1 open and not a draft**). A working FastAPI
service: routes, SQLAlchemy models, Dockerfile, compose, 17 passing tests.

**Why nobody found it, and why it is the duplication tax's second instance.**
Every search anyone would run — worktrees of `openlibrary`, branches matching
`bookworm`, the `12844/*` family — misses it, because it is *a different
repository in a different GitHub organisation*. The first instance was a schema
on an unmerged branch. This is an entire service one org sideways. The
`git ls-remote` check proposed for the import pipeline would **also** have
missed it, which is the more useful half of the finding: **the check has to
enumerate repos, not just branches.**

### Three designs, not two

| | Live master | This contract | ArchiveLabs service |
|---|---|---|---|
| Key column | `ia_id` text | `source_id` text [3] | **`source` + `value`, split** |
| Composite form | `bwb:9780…` | `bwb:9780…` preserved | `better_world_books` / `9780…` |
| Source vocabulary | free text | free text | **validated against vendored `identifiers.yml`** |
| `id` type | `serial` | `bigserial` [2] | `Integer` |
| `comments` | — | present [5] | absent |
| `import_item_history` | — | present, 2 CHECKs | **absent** |
| Dedup | *see below* | global on `source_id` [8] | per-batch only |

The source-vocabulary idea is **better than mine** and worth keeping: rejecting
a source name that is not an OL identifier catches the `gutenberg` /
`project_gutenberg` class of bug at the door, which is the bug that produced a
security regression in this division. It costs a vendored file that can drift
from OL's `identifiers.yml`, which is a real but checkable cost.

### Marker [8] is wrong, and live master says so in prose

I froze *global dedup on `source_id`* as an invariant "not expressible in DDL."
`openlibrary/core/imports.py` on master implements **both** behaviours
deliberately, in two methods, and documents why:

- `dedupe_items` → `add_items`: **global.** `SELECT ia_id FROM import_item
  WHERE ia_id IN $ia_ids`, no batch scope; the docstring says it skips anything
  present *"anywhere, at any status"*, and that this is *"right for firehose
  sources — Amazon price lookups and daily archive.org imports re-offer
  unchanged records constantly, and **re-queuing them is what previously
  overwhelmed the database**."*
- `add_or_refresh_items`: **per-batch**, because *"the same `ia_id` can
  legitimately exist in another importer's batch — an unscoped read collapses
  those non-deterministically, and turning that read into a write would let a
  feed refresh (and effectively steal) another batch's row."*

**So the correct answer is neither of mine nor the service's: it is both,
selected by source type.** Global for a firehose, per-batch for a registered
change-stream feed. Marker [8] as frozen would break legitimate re-imports;
the ArchiveLabs service's per-batch-only would reintroduce the firehose
re-queue that *"previously overwhelmed the database"* — which is the exact
failure BookWorm exists to fix. **Amend [8] to name both paths and the rule for
choosing.**

That is the generalisation from the naming ruling, hit again from the other
side: *when you collapse two values into one, ask what was distinguishing
them.* Here two dedup scopes looked like one invariant. They are not.

### Three names for Better World Books — and two of them are correct

ada-f7 raised this as "the standalone service's name matches nothing." Checked
against `origin/master`, that is not quite it, and the real shape matters more.
**There are three names in three namespaces, and two are legitimately
canonical:**

| Name | Namespace | Authority |
|---|---|---|
| `bwb:` | data slug | `scripts/bwb_opds_imports.py:167` writes `source_records: ["bwb:{isbn_13}"]`, packed into `ia_id`. **What live rows contain.** |
| `betterworldbooks` | **provider / feed** | `book_providers.py:642` `short_name`, and the feed-registry key at `cli.py:221` |
| `better_world_books` | **edition identifier** | `config/edition/identifiers.yml:25` — `name: better_world_books` |

`betterworldbooks` is **not declared as an edition identifier at all** — but
check that with an *anchored* pattern, because a loose one says the opposite:

```bash
F=openlibrary/plugins/openlibrary/config/edition/identifiers.yml
grep -c  betterworldbooks              "$F"   # 1  <- the url: line, misleading
grep -cE '^\s*name:\s*betterworldbooks\s*$'  "$F"   # 0  <- the real answer
grep -cE '^\s*name:\s*better_world_books\s*$' "$F"  # 1  <- control
```

The loose grep matches `url: https://www.betterworldbooks.com/…` on line 27,
so anyone re-deriving this casually concludes it *is* declared. Caught by
ada-f7. That the check for "these strings are confusable" is itself easy to
get wrong by substring is the rule demonstrating itself — **always include the
control**, since a pattern returning 0 proves nothing until you've seen it
return 1 on the name that does exist.

And `better_world_books` follows the
convention every other provider already uses: `project_gutenberg`,
`standard_ebooks`, `project_runeberg` are all snake_case and all match their
`identifiers.yml` name. **So the standalone service's choice is right for the
field it is validating**, and the recommendation to drop it would break
consistency with OL's own identifier list.

**The provider namespace is a security boundary.** `add_book/__init__.py:1114`
gates acquisition writes on `FeedRegistry.provider_names()` membership:

> *"the trust boundary can't be the endpoint — it's feed-registry membership.
> Acquisitions naming an unregistered provider are dropped, so a caller cannot
> mint acquisitions for an arbitrary (unregistered) provider."*

That check compares a `provider_name`, so the string that matters there is
`betterworldbooks`. A record carrying `better_world_books` as its *provider*
silently loses its acquisitions — not an error, a drop.

**So do not pick one canonical name. Keep both fields, and never let one
stand in for the other:**

- `source` / identifier type → `better_world_books` (validate against
  `identifiers.yml`)
- `provider_name` / feed key → `betterworldbooks` (must match
  `feed_registry`, security-load-bearing)
- `bwb:` → read-only legacy prefix, needed to interpret existing `ia_id` rows

**`book_providers.py:644` already conflates them** — `identifier_key =
"betterworldbooks"`, pointing at an identifier OL never declares. It is
latent rather than live-breaking only because `BetterWorldBooksProvider`
overrides `get_identifiers()` to use ISBN and a config map, bypassing the
`identifiers.{identifier_key}` read at `book_providers.py:203`. Every sibling
provider would break on that mismatch; this one is masked by its override.

**This is the third instance of one failure.** *When you collapse two values
into one, ask what was distinguishing them.* First the naming ruling, which
cost a security regression. Then the two dedup scopes above. Now a provider
name and an identifier name, where one of the two is a trust boundary. The
pattern is stable enough to act on: **in this subsystem, two strings that look
like the same name usually are not, and the cost of merging them lands on the
security side.**

### Migration cost nobody has priced

`source` + `value` is a cleaner model, but live rows are `ia_id = 'bwb:9780…'`
and the service's own history shows the seam: commit `09bf53f` chose `bwb`,
then `a74d574` replaced it with `better_world_books` as the canonical OL name.
Live data uses the `bwb:` prefix. **Splitting the column therefore requires a
prefix→identifier mapping for every historical source**, and that mapping does
not exist in any repo. It is not hard; it is simply unowned, like the three
deploy steps above.

### The coverstore precedent answers most of marker [9]

Marker [9] recorded *"three unowned deploy steps: provision the DB, apply the
DDL, add the nginx route — none exist in any repo."* Two of the three have a
working in-repo template, and I did not look for one. `docker/ol-db-init.sh`
on master:

```bash
createdb coverstore
psql --quiet coverstore < openlibrary/coverstore/schema.sql
```

So the pattern for a second database in this repo is: **ship `schema.sql`
inside the package, and add two lines to `ol-db-init.sh`.** The nginx route
has a precedent too — `docker/covers_nginx.conf`. `openlibrary/coverstore/`
is the shape: a package inside `openlibrary/` with its own `code.py`,
`server.py`, `asgi_app.py`, `db.py`, `config.py`, `schema.py`, `schema.sql`,
`README.md` and `tests/`, deployed with the app via `compose.yaml`,
`compose.production.yaml` and `docker/ol-covers-start.sh`.

**Honest limit: `ol-db-init.sh` is the dev/local bootstrap** — it also loads
`scripts/dev-instance/dev_db.pg_dump`. It does not prove how the *production*
coverstore database was provisioned. So marker [9] narrows rather than closes:
the dev path is answered and copyable, and the production question now has a
named precedent whose answer someone holds, instead of being unprecedented.
That is a better question to take to Mek than the original.

**Also relevant to the reconciliation: `openlibrary/bookworm/` already exists
on master** — `registry.py`, `harvest.py`, `cli.py`, `opds.py`, `README.md`,
`tests/`. So bringing the service in is *adding a service layer to an existing
package*, not creating one. The `app/` layout from ArchiveLabs (`app/main.py`,
`app/routes/`, `app/models/`) has to be folded into that package rather than
dropped beside it, and the naming will collide: the service's `app/models/
imports.py` and the existing `registry.py` both describe feed and item state.

### `openlibrary-bot` cannot author there

`gh api repos/ArchiveLabs/openlibrary-bookworm/collaborators/openlibrary-bot/permission`
→ **`read`**. So an atomic PR agent can *see* the repo but cannot push a branch
or open a PR in it. Any plan that routes this work through the bot needs either
a permission change (Mek's call) or a target in `internetarchive/openlibrary`.
Worth knowing before push time, since GitHub reports missing access as
"could not resolve" rather than 403 — which reads as *does not exist*.

---

*See [[features/feed-registry-import-system]] · [[imports]] · [[METHODOLOGY]]*
