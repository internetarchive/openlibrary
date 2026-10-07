# Imports / BookWorm — plan, 2026-09-27

> **Status:** current
> **Verified:** every "true today" claim below was re-derived on 2026-09-27,
> not carried from last week's notes
> **Scope:** research and sequence. No implementation.

## 1. The outcome

Ada's phrasing is **"a partner's books arrive without anyone running
anything."** That is right and I would add four words: **and arrive complete.**

The reason is not pedantry. Bookdash's 814 works arrived. Their covers did
not — *zero* out of 814, measured against the live API. By Ada's phrasing that
import succeeded. So the outcome needs the completeness clause, or the metric
rewards a pipeline that delivers husks.

**Restated:** *a partner's books arrive, complete, without anyone running
anything, and we can tell when they didn't.*

## 2. What is actually true today

| | State | Checked |
|---|---|---|
| `opds_acquisitions` in `search.json` | **Deployed.** All three provenance markers confirmed in production across two editions, incl. the multi-link case | today |
| Harvest scheduling | **Nothing schedules a harvest** in deployed config — `grep -il 'bookworm\|harvest'` across `olsystem` → **0**. But the line is *written*: **olsystem#458**, draft, `17 */6 * * *`. Unmerged, not unwritten | today |
| ImportBot | Scheduled and draining. The back half is live; the front half never fires | today |
| BookWorm service | **Does not exist.** `openlibrary/bookworm/` is a harvester library + argparse CLI. No routes, no DB, no ASGI mount, no compose service | 09-20 |
| Frozen import contract | Written, exercised in five venues, own fixes verified | 09-21 |
| Deploy path | **Three unowned steps**: provision the DB, apply DDL, add the nginx route. None exist in any repo | 09-20 |
| Bot access demand | **8 open requests**, 3 of them in the last six weeks — #12887 #13136 #13191 #13222 #13285 #13403 #13614 #13659 | today |
| Epics | **Two.** #12655 has the vision; #12844 has every merged PR | today |

**The single most valuable fact:** feeds are registered, the runner is merged,
ImportBot is waiting — and **one crontab line in `olsystem` is the only thing
missing** for partner books to arrive without anyone running anything. That is
configuration, not a project, and it is the outcome in item 1 almost in full.

## 3. Sequence

**S1 — Land the harvest cron.** *Unblocks the entire outcome.* One line in
`olsystem`, **already written as draft PR olsystem#458** (`17 */6 * * *`,
single pass so cron sees a non-zero exit when a feed fails, `--ol-config` so
proxy credentials stay out of the crontab). Everything downstream already
works. **Prerequisite:** the unbounded row-fetch follow-up — `get_by_editions`
has no SQL `LIMIT` and runs on the one shared synchronous connection, safe at
today's ~96 rows and not at harvest scale. **S1 is gated on S2 and on the
activation order below.**

**S2 — The per-edition window function.** `ROW_NUMBER() OVER (PARTITION BY
edition_id …)`; a global `LIMIT` is wrong and was already tried and reverted.
Small, isolated, and it is the thing standing between us and S1.

**S3 — Decide the canonical epic.** One sentence. Until then work lands under
#12844 while the plan lives in #12655, which is *mechanically* why #12655's
checkboxes rot. Cheapest item here. **See the audit below — the epic is not
merely stale, it understates how far along this is, in every direction.**

**S4 — Bot Request triage.** 8 requests, 3 in six weeks, and the epic's whole
answer is `trust_level text default 'review'`. That is a column, not a trust
model: it says nothing about who approves, what a submitter can see, or what
rate limit attaches to a tier. **This is the demand actually driving BookWorm**
and it is unspecified.

```bash
gh issue list --repo internetarchive/openlibrary --search 'is:open "bot account"' --limit 100
```

Returns 10 today; two are not access requests (#9726 is a 2024 batch-import
ask, #13656 a duplicate-edition bug that merely mentions the phrase), leaving
the 8 above. Re-run it rather than trusting the number.

**S5 — BookWorm service.** Contract is frozen and exercised. Needs an
implementer *and* the three deploy steps owned. Largest item; least urgent,
because S1 delivers the outcome without it.

**S6 — Covers.** Blocked on Drini's ruling (#13682), and #13633 is rewriting
the code that issue cites.

## 4. Mek / not-Mek

**Needs him:** which epic is canonical (S3); who owns production-side writes —
provisioning, DDL, nginx (S5); the trust-tier policy behind S4; Drini's
security ruling (S6); and whether a lead may spawn.

**Does not need him, and I should stop implying otherwise:** every ruling
inside the contract; the sequence above; the covers seam ownership below;
anything I can verify from public surfaces.

## 5. What I would delegate

Named, with deliverables, even though I cannot currently spawn.

| Agent | Produces | Rough cost |
|---|---|---|
| **A1 · window-function** | S2: the `ROW_NUMBER()` fetch + a test that fails against unfixed source | small, one file |
| **A2 · harvest-cron** | S1: the `olsystem` line, plus evidence a run fires and lands records | small, blocked on A1 |
| **A3 · bookworm-service** | S5 against the frozen DDL; owns the two invariants DDL cannot express | large |
| **A4 · bot-triage** | S4: a written trust-tier proposal from the 8 live requests, not a schema column | medium, research |
| **A5 · bots-CI** | The two verified lines in `lint_python.yml` | tiny |

**A1 and A5 are each an hour and unblock disproportionately.** A5 in
particular unjams a repo whose *only* maintainer is automation that cannot
merge because CI is red.

## 6. What would make this plan wrong

**The assumption I am least sure of: that installing the harvest cron is
safe once S2 lands.** I have verified nothing schedules a harvest, and that
ImportBot drains. I have **not** verified what happens when a real feed
delivers at volume into a queue that has only ever seen 94 hand-run records.
The one datum I have points the wrong way: **79 of 94 Lenny records returned
`internal-error` and every one succeeded on serial retry.** Nobody established
whether that is concurrency or write rate. If it is write rate, S1 turns a
dormant pipeline into a failing one, and the symptom — records silently not
arriving — is the exact thing the outcome measures.

**So S1 should be gated on a load question, not only on S2**, and I would put
that in front of A2 as its first task rather than its last.

### What the load question actually is — and how to settle it read-only

ada-f7 raised the same gate from the other side: *a registered feed whose
cursor is NULL does a full crawl on first fire.* It judged this needed a
production DB query it had no access to. It does not. Both halves are printed
by a read-only command that exits before writing:

```bash
python -m openlibrary.bookworm.cli register \
    --ol-config /olsystem/etc/openlibrary.yml --show
```

It prints `#id provider [status] … last_updated=<cursor> data=…` per row
(`cli.py:273-279`) — status *and* cursor, no SQL, no credentials beyond the
config the app already reads. This is the same lesson as
[[README]]'s second trap, one layer in: **before escalating for database
access, ask what the application's own read-only commands already print.**

Two facts make the blast radius precise rather than alarming:

**Registered is not harvested.** Feeds register as `pending`, and `harvest_all`
skips anything not active (`harvest.py:500-509`). So merging #458 while
everything is pending is a **no-op** — the cron fires, finds nothing active,
exits 0. The risk is not in the cron. It is in the activation.

**But there is a back door, and it is the thing to check.**
`registry.py:179` — `.get("status", STATUS_ACTIVE)` — means **rows written
before the status field existed carry no status and are treated as active.**
Status landed in `2cd225e94` (2026-09-07, Mek). *Any feed registered before
2026-09-07 is active right now and nobody flipped a switch to make it so.*

Combine that with the feed sizes in `cli.py:204-227`:

| Feed | Size | Unseeded first crawl |
|---|---|---|
| `lenny` | 96 items, honours `?modified_since` | trivial |
| `project_gutenberg` | **~78k items** | thousands of paged fetches |
| `betterworldbooks` | not registered — 403 from Cloudflare | n/a |

**The single dangerous combination is: `project_gutenberg`, registered before
2026-09-07, cursor still NULL.** That is ~78k items into a queue that showed
~84% failure under 8-way concurrency. Nothing else on the list can hurt.

**Which makes the ordering the gate, not the query.** Merge #458 (no-op while
pending) → confirm with `--show` → activate `lenny` alone and watch one tick
→ seed gutenberg with `register --since <recent> --reseed` *before* activating
it. `--reseed` exists precisely for "registered it, then realised the backfill
is too large" (`cli.py:264-267`), so the recovery path is built and needs no
hand-written SQL.

A crawl truncated by `--max-pages` advances the cursor past pages it never
fetched, permanently skipping them (`harvest.py:381`, `cli.py:148`). #458
correctly warns never to add it. **`--since` is the safe knob; `--max-pages`
is not.**

---

## Does the epic describe the endstate? No — and it errs toward *understating*

Checked 2026-09-27 against `origin/master` and production, not against memory.

**There are four epics, not two.** #12844 names this itself, on 2026-07-23:

> *"how this relates to #5792 … and #12655 … Worth a scope conversation before
> further subtask PRs land, so effort doesn't split across three epics
> tracking overlapping ground."*

| Epic | Last updated | |
|---|---|---|
| #5792 Trusted Book Providers | **2025-07-24** | cdrini's, 14 months idle |
| #10251 Simplify TBP integration | **2025-09-16** | 12 months idle |
| #11264 Solr acquisitions field | 2026-04-08 | superseded by the query-time weave |
| #12655 BookWorm | 2026-09-21 | the vision |
| #12844 Feed Registry | 2026-09-06 | where every merged PR lands |

That scope conversation was requested and never happened. Further subtask PRs
landed anyway — #13395 merged and deployed. So the condition #12844 set for
itself was not met, and the work proceeded regardless.

**#12844's four checkboxes, against reality:**

| Box | Says | Actually |
|---|---|---|
| 1. `feed_registry` table | ☐ *"closed, unmerged, conflicting — needs a fresh PR"* | **Done.** `CREATE TABLE feed_registry` is in `openlibrary/core/schema.sql` on master, with `FeedRegistry` in `bookworm/registry.py` and feeds registered |
| 2. `acquisitions` table | ☑ *"not yet wired into live flow"* | Done **and wired** — caveat is two months stale |
| 3. ingestion cron | ☐ *"PR #12852 draft, not integrated"* | Harvester **merged**; the cron is olsystem#458, draft. #12852 is superseded and the box points at the wrong PR |
| 4. solr acquisitions | ☐ **"not started"** | **Deployed to production.** Query-time weave, all three provenance markers verified live — exactly the revised plan the epic describes one paragraph above the box |

**Three of four boxes are wrong, and all three err the same way: they
understate progress.** Read cold, the epic says one of four subtasks is done.
Three and a half are. The one box marked done carries a caveat that stopped
being true in September.

This is the [[METHODOLOGY]] status-table failure at epic scale — *a status
table is a cache with no invalidation* — with an extra rot vector: #12844 was
**auto-closed** on 2026-06-21 by a `Closes #12844` in a PR covering one of
its four subtasks, and had to be manually reopened.

**Two specific gaps in the endstate description, beyond staleness:**

- **No completeness clause.** Neither epic states that a book arriving without
  its cover is a failed import. Bookdash passed every criterion either epic
  lists, with zero covers on 814 works.
- **Bot trust is priced as a schema column.** #12655 answers the access
  question with `trust_level text default 'review'`. Eight open requests are
  waiting on a *policy* — who approves, what a tier permits, what rate limit
  attaches — and a column is not one.

**Recommendation.** #12844 is canonical: it is where the work lands, it
already frames registry → acquisitions → ingestion → Solr, and it survived
being auto-closed because someone judged it the integrated end-state. #12655
becomes the BookWorm *service* epic only. #5792 and #10251 close or fold in —
both have been idle over a year. That is one sentence from Mek, not a
discussion.

Note that #12655's "Background" section documents `import_item` with `ia_id`
and `data text`. [[bookworm-import-contract]] deliberately deviates —
`source_id` and `jsonb` — so #12655 cannot be handed to an implementer as the
spec without amending it first.

---

## The covers ↔ imports seam

Ada thinks it is its own. **It is mine**, and the rule is worth naming: *the
seam belongs to whoever owns the outcome, not to whoever owns the code.*

Coverstore owns "does the cover service work" — and it does; the allowlist
behaves exactly as documented. Imports owns "does a partner's book arrive
complete," and 814 bookdash works arriving with zero covers is a failure of
that, not of coverstore. It presented as an effort-1 symptom and went unowned
for a year precisely because everyone looked at the layer rather than the
outcome.

## Pricing the duplication tax

I nearly rewrote a staging-database schema that already existed, complete, on
`12844/feed-registry-acquisitions`. Found by accident. Across seven efforts
that is a guaranteed recurring cost, and it is cheap to remove:

**Before any agent starts, enumerate `git ls-remote --heads` for the epic's
branch prefix and report each branch's ahead/behind and whether its files are
on master.** That is mechanical, takes seconds, and would have surfaced the
prototype on day one. It is the same shape as the index-coverage check: the
convention "search for prior work" is a document nobody reads; the check runs.

I will build it into `imports-dept-status.sh` for this division rather than
propose it as fleet policy.
