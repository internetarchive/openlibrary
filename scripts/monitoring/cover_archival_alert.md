# Cover archival: stall alert (design)

**Status:** design only (#13763). Nothing here is scheduled, deployed, or wired to a channel.

Cover archival failed silently for two years (#9836, #13287), and data dumps did the same (#5402).
**This job already had a dead-man's switch:** its cron ran under a Sentry cron monitor, and the
silence still went unnoticed for 20 months (§4). So this design watches the **outcome** (zips on
archive.org), not the job, and names a **reader** for every alert. It covers how three public
signals become an alert that someone reads, and how we find out when that alert itself stops
working.

Every claim about current state is labelled **RAN** (a command was executed, and it is given) or
**READ** (from code, config or docs; not executed). Measurements are as of 2026-09-29.

## The signals

| | Signal | Instrument |
|---|---|---|
| **S1** | Invariant: no cover points into a zip that lacks it | The #13762 checker. It emits one JSON line per batch, `{batch, listing_count, missing_count, sampled, verdict, evidence_ids}` plus `serves` on `partial` rows, then a summary line with no `batch` key. Exit codes: 0 clean, 1 `LOSS`, 2 control failed, 3 indeterminate, 4 request cap hit. |
| **S2** | Heartbeat: when a bulk zip last reached archive.org | The newest `mtime` among `covers_NNNN_NN.zip` files in `https://archive.org/metadata/covers_NNNN`, for the newest item **and the next one** (the next is created by its first upload). |
| **S3** | Backlog: closed batches with no zip on archive.org | `newest_id // 10_000` is the open batch. Every lower batch without a full-size zip is backlog. The newest ID is found by binary search with `HEAD /b/id/<id>-S.jpg?default=false`: 200 or 302 means present, 404 means absent. |

**S2 must not use `publicdate`.** RAN: advancedsearch sorted by `publicdate` returns
`covers_0014` at 2023-10-14, the item's creation. But its newest zip, `covers_0014_68.zip`, has
`mtime` 2024-08-26. Uploads into an existing item don't move `publicdate`, so an alert on it would
have been red from late 2023 while uploads were still landing. `item_last_updated` is no better,
because metadata edits and derive tasks write it too.

**S3 must pass `?default=false`.** RAN: without it, a nonexistent ID (99,999,999) returns 200, a
placeholder image. The search then finds no upper bound and reports a wrong newest ID. `HEAD` on the
image, rather than `GET` on `/b/id/<id>.json`, also keeps the search to status codes (data
minimisation). Controls on every run: 99,999,999 must return 404 and 14,624,072 must return 302.

### Today's values (RAN, 2026-09-29, 35 requests with 1 s between them)

- **Newest cover: 15,260,230.** Found in 29 `HEAD` requests, and the next 10 IDs all return 404. This is a
  lower bound: a run of deleted IDs longer than 10 would hide newer covers.
- **Open batch `0015_26`.** Closed batches run from `0014_00` to `0015_25`, 126 in all.
- **`covers_0014` holds 69 zips, `_00`–`_68`, contiguous. The newest `mtime` is 2024-08-26.**
  `covers_0015`, `s_covers_0015` and `l_covers_0015` don't exist.
- **Backlog: 57 closed batches (`0014_69`–`0015_25`), at most 570,000 covers.** The lead's figure of 56
  on 2026-09-28 agrees: `0015_25` has closed since. #13287's 242k counted only IDs above 15M.
- **Batch rate: about one every 13 days** (57 batches over the 25 months since 2024-08-26). The
  thresholds below use this figure.

## 1. Where it runs

**The code goes in `scripts/monitoring/`; the schedule goes in a GitHub Actions workflow, not in
`monitor.py`.**

`scripts/monitoring/` fits the code: it holds the repo's other health checks, has a test directory,
and is reviewed like the rest of the repo. `monitor.py`'s scheduler doesn't fit the job (READ):

- It runs on OL hosts, and jobs are pinned to them with `limit_server`. The archival cron ran on
  `ol-home0`. A watcher on that host shares fate with the thing it watches.
- It reports to Graphite, which charts numbers. Nothing in the repo turns a Graphite series into a
  message to a person.
- Its state lives in the process and is lost on every deploy. "Did this change since last run" needs
  state that survives.

Every signal is public HTTP, so nothing forces the watcher onto a host. A scheduled workflow is
off-host, needs no credentials for its reads, and leaves a visible record of every run.

Costs, stated plainly:

- **`schedule:` runs only from the default branch.** A PR can't exercise its own schedule. Before
  merge, test it with `workflow_dispatch` on a fork, and after merge with one manual dispatch.
- **GitHub delays or drops scheduled runs under load** (READ, GitHub docs). The dead-man's switch in
  §4 has a margin for this.
- **Per-slot baselines are a checked-in file, not a workflow artifact.** An artifact lasts at most
  90 days on a public repo (READ, GitHub docs). A rotated slot comes round again about every 28
  weeks, so an artifact baseline would always have expired, and every change rule on an old slot
  would be permanently indeterminate. The file holds each (item, tier) slot's `listing_count` and
  short-batch classes, next to the known-loss allowlist. **The workflow only reads it.** Every
  difference against it is already an alert, so the person who acknowledges the alert updates the
  file by PR. The workflow needs no write access to the repo, and each baseline change is
  reviewed. A slot with no entry reports **indeterminate**, never "no change".

Cadence:

- S2 and S3 run **daily**, at about 35 requests.
- S1 runs **weekly, in its own workflow**, so that §4 can watch it on its own (a daily S2/S3 success
  must not make a failed S1 look fresh). It stays within the checker's request cap, which #13765
  hasn't settled yet: 100 in its body, 150 as relayed to me. The rotation interval below assumes 150,
  and scales with the cap.
- S1 also runs the day after S2 sees a new upload. The danger window is between a partial upload and
  the next archival run.
- **Controls run on every S1 run, outside the rotation:** batch 62 (positive) and a full batch-61 ID
  (negative). Today they happen to be covered anyway, because `covers_0014` is the newest item and is
  scanned every run. Once `covers_0015` exists, batch 62 would be in rotation and absent 27 weeks
  in 28, and "known loss missing = control failure" would fire most weeks.

## 2. Who reads it, and through what

An alert nobody reads is the failure we're guarding against, so every alert has a named reader.

| Class | Channel | Reader |
|---|---|---|
| **Page**: a loss is happening | Slack, in a channel that carries **no recurring automated alert** (Mek chooses it; see open question 3), **and** a GitHub issue | The cover-service owner, same day |
| **Stall**: archival isn't making progress | A comment on the existing #13287, already the record of this stall, **only when the backlog count changes**. If #13287 is closed, a new issue. Closed by a human, never by the bot. | The cover-service owner, weekly |
| **Watcher health**: the checker can't produce a verdict | GitHub issue plus the §4 dead-man's switch | Whoever owns the workflow |

**Why a GitHub issue.** It persists, it's assignable, and nobody has to be online when it fires.
It's also where #9836 and #13287 already live. A page needs Slack as well, because an issue only
notifies whoever watches the repo.

**What someone with access has to create (nothing here creates it):**

1. A Slack incoming webhook for the chosen channel, stored as a repository secret. By a Slack admin, then
   Mek for the secret. The existing cron alerts use host-side credentials, which Actions can't reach
   and shouldn't.
2. The §4 host cron and its Sentry monitor. A change to the private cron config plus a Sentry
   admin; Mek.
3. `issues: write` on the workflow's `GITHUB_TOKEN`, granted in the workflow file. Reviewed with the
   PR. It needs no `contents: write`, because baselines change only by human PR (§1).

## 3. Thresholds

**Page, same day:**

- **Any `LOSS` row not already recorded as a known loss.** Zero tolerance: a cover redirected into a
  zip that lacks it can't be recovered from archive.org. Known losses live in a checked-in allowlist.
  Each entry records its batch, `missing_count` and evidence IDs. Today the only entry is
  `covers_0014_62`, and without it every run would exit 1. A page that is always firing gets ignored.
  - **A known loss missing from the output is a control failure** (watcher health, below).
  - **A change in a known loss's `missing_count` also pages.** Growth is new loss. Shrinkage means
    someone repaired it, and should be confirmed before the entry is updated.
  - **`covers_0014_62` is the only live positive control.** If #13725's runbook restores it, the
    checker's recorded fixture becomes the only positive control, and the checker's summary line must
    say so. A control that quietly disappears reads the same as one that passes.
- **A `partial` row that changes to `serves: false`**, meaning it served last run, or its batch
  wasn't in the baseline. The row points local, the local file is gone, and the zip lacks it, so
  nothing public holds that cover. Host disk and backups are unknown (§5). Rows that were already
  `serves: false` are most likely the long-standing failed-cover class. They're reported weekly as
  a known-loss count, not paged. Paging on them would fire every week, and people learn to route
  around an alert like that.

**Stall (issue):**

- **No new zip for 21 days while at least one closed batch waits.** A batch closes about every
  13 days, so 21 days is one missed batch plus a week of slack for a slow or retried upload. The
  "while one waits" clause keeps the alert quiet when there is nothing to archive.
  **Armed at launch, as an issue comment, never a page.** It fires on day one, and it should: that is
  the true state. Leaving it unarmed would mean the watcher knows and says nothing, which is the
  two-year failure again. What gets an alert routed around is repetition, not being red, so it
  comments on #13287 only when the backlog count changes, about once per closed batch. It never posts
  the same number twice. The comment carries the count, the newest zip date and the method, so each
  one can be checked.
- **Backlog not smaller than it was 28 days earlier; armed only when the archival cron ships (plan
  step 5).** This catches a cron that runs and uploads but falls behind: two batch intervals of no
  net progress. Before the cron exists, the backlog can't shrink, so this rule would only repeat the
  one above.

**Change, not presence (issue):**

- **A new `partial` or `short_no_record` batch, or a rise in any batch's `missing_count`.** Today's
  small shortfalls are a stable class (probably failed covers, inferred from code), so presence
  alone isn't news. The baseline is the checker's own classes and counts, not the 2026-09-24 census.
  READ (from the census and the covers lead, not re-run here): 8 of `covers_0014`'s 69 zips are
  short, including 62, and 31 of the 669 zip batches in `0008`–`0014` are. **Each (item, tier) slot's
  baseline is set the first time that slot runs,** so with rotation the baseline fills in over
  weeks. Until a slot has one, its change rules report **indeterminate** for that slot.
- **Any `listing_count` that shrinks between two runs of the same slot.** That would be loss on
  archive.org's side, which S1's pointer check can't see.

**Watcher health (issue, and the §4 switch):**

- Exit 2 (control failed) or 4 (request cap hit) **on two consecutive runs.** One run can hit a bad
  moment; two is a broken checker.
- Exit 3 (indeterminate) on **the same batch in two consecutive runs.**

## 4. When the alert itself goes dark

**This has already happened on this job.** READ: the archival cron ran under a Sentry cron monitor
for the job, through `scripts/cron_wrapper.py`. In the production cron config it has been commented
out since 2025-01-12. Whether that monitor then fired and went unread, or was muted, is
**unverified**; answering it needs Sentry access.

It shows two limits. A job-liveness monitor can't see an outcome stall: a run that exits 0 without
uploading checks in green. And a dead-man's switch helps only if its alert reaches someone.

So the watcher proves it ran *and did its job*, through two paths whose failures don't correlate:

**A. On GitHub.** The job fails and opens a watcher-health issue unless its output passes these
checks. GitHub's own failure email goes only to the person who last edited the workflow's
schedule (READ, GitHub docs), so the issue, not the email, is the alert.

- The summary line is present.
- The row count is at least the batch count it planned.
- Both S3 controls hold.
- The rotated (item, tier) slot is the one this ISO week implies. That needs no stored state, and a
  stuck rotation fails it.

The last check exists because the checker rotates slots by ISO week, and "it ran" doesn't prove it
looked anywhere new.

**B. On IA infrastructure.** A small host cron, under `cron_wrapper.py` with a new monitor slug,
reads **the S1 workflow's** latest scheduled run from the public GitHub API.
It exits non-zero if that workflow's latest successful run is older than **8 days**: the weekly S1 cadence plus a
day for a delayed or dropped scheduled run. `cron_wrapper` reports that to Sentry as an error. If
the host or the cron dies, Sentry sees a missed check-in.

The two watch each other. If GitHub Actions stops, B notices. If IA infrastructure or Sentry
stops, A still opens its issues. If both stop, nobody is alerted, and the lead's weekly check in
`ol-kb` stays as the backstop.

**Why not check in to Sentry from Actions directly.** RAN, 2026-09-29, from one macOS host:
`sentry.archive.org` resolves but times out after 15 s, while `archive.org` answers 200 as a
control. If runners can't reach it either, the check-ins can't happen. **Unverified from a GitHub
runner.** If a runner can reach it, B can be replaced by a direct check-in, provided Sentry doesn't
share a failure with what it watches.

**A fire drill before it counts.** The alert isn't considered live until one of each class has
been triggered on purpose and acknowledged by its reader: a dispatch with a mutated allowlist
(page), and a disabled schedule (dead-man). Until then, the lead's weekly check stays.

## 5. What it can't see, and what covers each gap

| Blind spot | Why it's invisible | What covers it |
|---|---|---|
| Whether the archival cron is scheduled on the host | The live crontab isn't public. READ: the cron config has had it commented out since 2025-01-12. | Nothing sees intent. S2 and S3 see the effect within a batch interval, and the §3 stall rule reports it on #13287. Mek checks the live crontab once (plan step 0). |
| Local disk on `ol-covers0`: surviving files, space filling | No host access | Surviving files: plan step 0, once. Space: READ, a daily `ol-covers0` disk check exists and posts to Slack at 80%. But it measures the filesystem holding the nginx logs, while its message names the data volume. **Whether it covers the coverstore data volume is open.** |
| Database flags (`failed` / `uploaded` NULL defaults) | No DB access | Plan step 0. A NULL-flag row is skipped silently, and it shows up only indirectly, as a `partial` gap after its batch uploads. |
| **The unzipped backlog, 57 batches, a single copy** | S1 only produces rows for zipped batches. A cover that was never zipped can't become `partial` or `serves: false`. | A weekly sample: 20 non-zipped IDs, **one per local day-directory**, rotating through the backlog's days, each of which must return 200. Specified here as an S1 check, with the S1 thresholds and the §4 did-its-job checks. **It detects total or large loss only.** Local files are stored by day, and one lost day is about 770 covers. A uniform 20-ID sample would hit that in about 2.7% of weeks (arithmetic). The day-rotated sample reaches each day about once every 38 weeks. Day-level loss needs a host-side check (Mek). |
| **Rolled-back or lost DB rows in full batches** | READ: S1 examines only the missing IDs of short batches. If the DB were restored from an older backup, finalized rows would revert to local filenames whose files are gone. Those covers 404 while the zip still holds all 10,000. | Nothing in this design. It's recoverable from the zip, but nobody would know to repair it. The day-rotated sample above could be extended to zipped batches, and would then catch it at the same weak rate. |
| **Covers 0–7,139,999 (`olcovers1`–`olcovers713`)** | Different item and file shape (`olcoversN-{S,M,L}.zip`), outside S1–S3. Reviewer READ (`code.py`): S/M sizes below 6M are served from local tars. | Their data is on archive.org, so a local disk loss is an outage, not an archival loss. Still, nothing here fires on it. |
| **Covers 7,140,000–7,999,999** | Reviewer RAN a 7-ID sample: some are in local `covers_0007_NN.tar` files with no archive.org item, and the rest are unarchived local files. #13725's `MIN_ARCHIVABLE_ID` of 8,000,000 means archival never picks them up. | **Zero coverage, and a single copy: up to about 860k IDs** (density not measured). Recorded as a known gap (#476, 2017), not a watch to build here. |
| Old slots between rotations | 150-request cap. There are about 28 (item, tier) slots (items `0008`–`0014`, 4 tiers). | Each old slot is re-checked about every half-year. That is acceptable only because old zips don't change unless something re-uploads them, and a re-upload moves S2. |
| An archive.org item going missing or dark | RAN: a nonexistent item's `/metadata` returns **HTTP 200 with the body `{}`** (`covers_0007`; the `covers_0008` control returns 64 KB). A naive count would read that as 0 files. | An empty metadata object is its own state, **missing item**: indeterminate for S1 and S2, never a count of 0 and never "not uploaded". For an item that already has a baseline entry, it pages as a possible loss on archive.org's side. The shape of an item that exists but is dark is **not measured**. |

## Open questions

1. Whether the archival job's Sentry monitor fired after 2025-01-12, and who received it. This
   decides whether §4's Sentry path is read at all. Needs Sentry access.
2. Whether GitHub runners can reach `sentry.archive.org`. This decides whether path B is needed.
3. Where the page goes: which Slack channel, and who the cover-service owner is by name. Mek's call,
   with one condition: **the page channel must not already carry an always-firing alert.** The
   channel the existing host alerts use is suspect for exactly that reason, since an unrelated
   disk-space alert there has been firing falsely every day (reproduced by the covers lead; whether
   the alerts reached Slack isn't checked).
