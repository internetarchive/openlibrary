# Core Vitals

> **Status:** `partial`
> **Sources:** `raw/google-docs/core-vitals.md` (Google Doc — "Open Library Core Vitals", exported 2026-06-28); `raw/google-docs/usefulness-scores-schema.md` (Google Sheet — "Usefulness Scores Schema", direct-paste 2026-07-16); Retention Score section also directly informed by codebase investigation (`openlibrary/accounts/__init__.py`, `openlibrary/admin/vitals.py`, PR #12367, issue #12366) and live production data, not just doc ingestion
> **Last ingested:** 2026-07-16 · **Retention Score section corrected against `origin/master` 2026-07-27** (it previously claimed an implementation was live that had never been committed — see that section)

Open Library's three self-reinforcing product metrics — Content Value, Retention, and Participation — that form a unified, metric-driven **Value Loop** for measuring and improving patron value.

---

## How It Works

The three vitals are causally linked in a cycle:

```
Content Value (record quality)
    → higher-quality records lead to →
Retention (user engagement)
    → engaged users are inspired to →
Participation (community contribution)
    → active contributions directly result in →
Content Value
```

Each vital has a score with a formula. All scores are computed via [[search|Solr]] and emitted to statsd. The goal is to have all three scores growing simultaneously — a system where improving one improves the others.

---

## 2026 Priority: Retention → Participation, not Content Value growth

The three vitals are pursued **sequentially, not in parallel, in 2026** — this is a deliberate priority
call, not an oversight if a given quarter's work looks Retention/Participation-heavy with little visible
Content Value work:

- **Content Value is measured this year, not grown.** Track 0 (Core Vitals) instruments and scores the
  existing catalog as a diagnostic — identifying which records are high-demand/low-usefulness — but
  *actively adding new content value* (catalog growth/augmentation at scale) is explicitly a **2027**
  goal, not a 2026 one.
- **2026's actual push is Retention → Participation.** Per the 2026 planning doc's own guiding policy:
  "Focus on improving access of remaining value" — i.e. work with what's already in the catalog rather
  than growing it this year. Recovering *value available* (undoing takedown losses) takes time and isn't
  fully in Open Library's control; Participation also structurally depends on Retention working first
  (an engaged, returning patron is a prerequisite for a contributing one) — so Retention is the lever
  pulled first, with Participation following once it's shown results.
- **Why this matters when reading any 2026 Core Vitals work**: "Core Vitals needs to land ASAP" (a
  standing ask) means landing the *measurement* infrastructure — funnel instrumentation, the three scores,
  a dashboard — not shipping catalog-growth features. Source:
  `raw/google-docs/openlibrary-planning-2026.md` and `openlibrary-planning-2026-summary.pdf`.

---

## Why It Exists

Without a unified scoring framework, catalog improvement is driven by intuition rather than patron demand. Core Vitals enables:
- **Deciding what to improve** — which records matter most (weighted by demand, not uniformly)
- **Verifying value is being created** — scores either go up or they don't
- **Closing the loop** — participation improves content which retains patrons which drives more participation

---

## The Three Vitals

### 1. Content Value

Measures catalog usefulness, weighted by patron demand.

#### Content Value Score (CVS)

> "How useful is the catalog for the books patrons demand most?"

```
CVS = total_weighted_usefulness / total_demand
    = Σ(Ui/Umax × wi) / Σ(wi)
```

Where:
- `i` = each book with demand activity in a 1-day window
- `Ui` = raw usefulness points for record i (unbounded)
- `Umax` = current maximum possible usefulness points (based on schema)
- `wi` = demand weight for record i

**Implementation:** Computed hourly ⚠️ UNVERIFIED (cadence has `?` in source). Stored in statsd as `ol.stats.content_value_score`. Solr fields: `weekly_demand`, `weighted_usefulness` (computed by Trending code); `total_demand` = sum of `trending_score_weekly_sum`.

**Features:** Prioritizes high-impact records; handles schema evolution (as Umax expands); incentivizes catalog growth.

#### Content Liability Score (CLS)

The fraction of high-demand records falling below the usefulness threshold τ.

```
CLS = Σ(Ui/Umax × wi, for i where Ui/Umax ≤ τ) / total_demand
```

Where `τ` = usefulness percentile threshold between 0 and 1. Implementation: Solr query for all records with `usefulness <= τ` ("under_useful" records).

---

### 2. Demand Score

The demand weight `wi` used in CVS is computed per Edition record:

```
demand(r) = (ε × α)
          + (β × monthly_edition_readinglog_counts(r))
          + (γ × min(w, log(1 + historical_work_readinglog_counts)))
```

| Parameter | Value | Meaning |
|---|---|---|
| `ε` | 1/365 ≈ 0.002 | Base floor — random chance a page is accessed once per year |
| `τ` | 0.2 | Temperature: how much cold records matter vs. hot |
| `α` | min(1, τ × total_demand_hot / total_demand_cold) | Scales cold record floor to 1:5 of hot |
| `β` | 10 | Recency boost for monthly edition reading log counts |
| `w` | 25 | Cap on historical work-level reading log contribution |
| `γ` | 0.2 | Fraction of historical work demand awarded to an edition |

**Key design choices:**
- `ε` ensures every cold edition (0 observed hits) is still counted
- `α` prevents cold records from drowning hot ones (without it, cold ≈ 2× hot)
- `β > γ` — recent edition activity outweighs historical work-level activity
- `γ` and `w` let neighboring editions benefit from a work's history without overpowering recent signals

**Scenario:** A cold edition of a hot work (0 page views, 0 reading logs, work has 20K historical logs):
`demand = (ε × α) + 0 + (0.2 × min(25, log(21000))) ≈ 1.98`

**Implementation:** Daily diff — compute what fell out of the 30-day window and what came in from the last 24h. Partial atomic update on Solr records. `bookshelves_books` table (see [[features]]) is the primary data source.

**Open work:**
- [ ] Endpoint on edition page for computing demand of a record
- [ ] Add `weekly_human_page_views` to demand (requires bot exclusion from nginx logs first)
- [x] GH #9221 → GH #11849 (merged): Moving between shelves lost selected edition — corrupted demand signals

---

### 3. Usefulness Score (BookPageScore)

Measures how well a book record serves patrons' needs. Defined in GH #11724. The standard measurement for record quality.

```
BookPageScore =
  200 × aread_access + 50 × asearch_inside_access + 50 × aexecutive_summary +
   25 × aprogramatic_access + 25 × apurchase_options + 25 × alibrary_options + 25 × asample_access +
   20 × afan_fiction + 20 × awikipedia + 20 × amicro_synopsis +
   10 × aquotes + 10 × aindex + 8 × averso_page +
    5 × atable_of_contents_page + 5 × angrams + 2 × afirst_sentence +

   50 × dtitle + 40 × dauthor_name + 25 × dgenre_tags +
   20 × dseries + 20 × dtable_of_contents +
   15 × dclassifications + 15 × dlanguage + 15 × disbn +
    5 × dlexile + 5 × dstar_ratings +
    3 × don_readinglogs + 2 × don_lists + 1 × dcontributor_names +

   50 × epreview + 40 × ebasic_description + 35 × ecover + 30 × etable_of_contents +
   25 × egenre_tags + 20 × estar_ratings + 15 × eawards +
   10 × erich_description + 10 × ereadinglog_counts +
   10 × elist_count + 10 × epage_count + 10 × eseries +
    5 × eauthor_photo + 5 × efirst_publish_year +
    5 × epublish_year + 5 × econtent_warnings +
    3 × eauthor_bio + 2 × epublisher + 2 × eauthor_links +

   5 × rich_characters   ⚠️ UNVERIFIED — Category is literally "?" in source, unresolved
   - 2 × dbad_publisher - 5 × dfuture_date - 30 × descaped_unicode_title   (penalties, not additive fields)
```

Prefixes: `a` = **Access** (can the reader get the content), `d` = **Discovery** (can the reader find the book via search/browse), `e` = **Evaluation** (can the reader judge whether it's right for them) — these are the real category names from the source schema. (Previously documented here as "availability / work-level data / edition-level data" — that gloss was wrong; corrected 2026-07-16 after ingesting the full schema, see `raw/google-docs/usefulness-scores-schema.md`.)

**Umax = 1013** (sum of positive-point fields only). Three fields are negative-point **penalties** rather than additive criteria — `bad_publisher` (-2), `future_date` (-5), `escaped_unicode_title` (-30) — these subtract from `Ui` when triggered, they are not part of the Umax ceiling.

Several fields share the same name across categories (e.g. `genre_tags` is worth 25 under both Discovery and Evaluation; `table_of_contents` appears at three different weights: 30/Evaluation, 20/Discovery; `series` at 20/Discovery and 10/Evaluation; `star_ratings` at 20/Evaluation and 5/Discovery) — the `a`/`d`/`e` prefix disambiguates these, they are not duplicates.

**Implementation:**
- One Solr field holds the raw sum; recomputed on Edition record update
- A second field holds `BookPageScore / Umax` (the percentage) — use this for sorting/filtering; more resilient to schema changes
- ⚠️ Changing weights or adding criteria requires a full Solr reindex
- ⚠️ After schema changes, aggregate graphs have drift error (combining effectively different units)
- Run a Solr query hourly ⚠️ UNVERIFIED to sum scores across all documents (verified cheap)

**Reference docs:** [Usefulness Scores Schema](https://docs.google.com/spreadsheets/d/1tt9ekWRMVaNiMc3GKMP09W3YmBeMXoTwKJnxuaispRA/) — ingested in full 2026-07-16, see `raw/google-docs/usefulness-scores-schema.md` for the complete per-field table (Criteria/Description/Justification/Notes columns); still a live/evolving spreadsheet upstream. Legacy [Book Page Score doc](https://docs.google.com/document/d/1a8TAFERRxsfvgh8xHHqXjr2yC2-67Svo5TE4Z19B75Q/)

---

### 4. Retention Score

Measures whether returning patrons are receiving value.

Two lenses:
1. **P_τ(t)** — Total unique patrons of class τ active in time window `t` (source: Matomo)
2. **E_τ(t)** — Average weighted engagement per patron of class τ in `t`

Patron classes and weights:

| Class τ | Weight |
|---|---|
| visitors | 0.01 |
| registrants | 0.2 |
| returning | 0.5 |
| retained | 1.0 |

**Overall Retention Score:**
```
RetentionScore = Σ_τ (w_τ × P_τ(t) × E_τ(t))
```

**⚠️ Implementation status — corrected 2026-07-27. Retention Score is NOT live in production.**

This section previously claimed the Retention Score was "live as of 2026-07-16" in
`openlibrary/admin/vitals.py`. **That was false**, and it cost real investigation time to
disprove. What had actually happened: the code was written on 2026-07-16 in a worktree
(`~/Projects/openlibrary-retention-pipeline`) and **never committed or pushed** — the wiki was
updated as though it had shipped. On `origin/master` there was no `gather_retention_scores`, no
`write_retention_to_statsd`, no `openlibrary/core/matomo.py`, and no retention reference in the
hourly cron. Only **participation** scoring was ever merged (PR #13073).

Two lessons worth keeping: verify against `origin/master`, not a local worktree, before writing
"live" here; and note that the real cron wiring point is **`openlibrary/admin/stats.py`**
(inside `main()`, under `if int(ndays) == 1`), which `scripts/store_counts.py` merely invokes —
`store_counts.py` itself contains no scoring logic.

**Current state: [PR #13213](https://github.com/internetarchive/openlibrary/pull/13213) — open, not yet merged.** It supersedes the
uncommitted 2026-07-16 work and adds:
- `openlibrary/core/matomo.py` — read-only Matomo client (method allowlist; POSTs so the auth
  token stays out of query strings and proxy logs).
- `gather_retention_scores()` / `write_retention_to_statsd()` in `openlibrary/admin/vitals.py`.
- `scripts/gather_retention_scores.py` — **on-demand trigger**; computes the score for any window
  right now without waiting for the cron. Prints by default, `--statsd` to record.
- Hourly cron wiring in `admin/stats.py`, wrapped in try/except so a Matomo outage cannot take
  down the rest of the job. A missing `matomo_api` token logs and skips.

Verified live against production Matomo before opening: 2,185 visits in one hour, `R_total`
816.00, `dimension1` populating across all four classes.

**Matomo access without VPN — solved.** `matomo.archive.org` is IP-restricted to IA's network, so
production reaches it directly. From a developer machine it is reachable through a **tinyproxy
developer gateway** on the LAN (`HTTPS_PROXY=http://<gateway>:3128`), locked to
`matomo.archive.org:443` only. Confirmed 2026-07-27: allowlisted host returns 200, non-allowlisted
(`grafana.us.archive.org`) is blocked, direct connection times out. `requests` picks `HTTPS_PROXY`
up from the environment, so **no application code depends on the proxy** — it is a dev convenience
only. Setup instructions: `~/Projects/openlibrary-core-vitals-retention-scores/AGENTS.md`.

**Patron cohort → class mapping:** cohorts come from `get_days_registered()` in `openlibrary/accounts/__init__.py` (⚠️ previously misdocumented here as `get_patron_status` — that name does not exist in the codebase). Buckets are discrete and mutually exclusive, not cumulative: `d1+` means 1-6 days since registration specifically, not "1 or more days". Full bucket list: `visitor`, `d0`, `d1+` (1-6d), `d7+` (7-13d), `d14+` (14-29d), `d30+` (30-89d), `d90+` (90+d, also the fallback on any parsing error).

**Cohort → class mapping (the one judgement call).** The spec fixes the four class weights but
**does not say where the returning/retained line falls** across the seven cohorts. PR #13213 uses:

| Class τ | Weight | Cohorts |
|---|---|---|
| `visitor` | 0.01 | `visitor` |
| `registrant` | 0.20 | `d0` |
| `returning` | 0.50 | `d1+`, `d7+`, `d14+`, `d30+` |
| `retained` | 1.00 | `d90+` |

i.e. "retained" means the account survived 90+ days. This is a defensible reading, not a
specified one — flagged for review on the PR. It is isolated in one constant (`PATRON_CLASSES` in
`vitals.py`) and, because all seven raw cohorts are emitted separately, **the boundary can be
re-cut later without losing history**.

Note an earlier sandbox prototype used only **3** classes, collapsing returning+retained into one
at weight 1.0 — that inflates `R_total` and does not match the spec. The 4-class table above is
authoritative (source: the Core Vitals Google Doc, `raw/google-docs/core-vitals.md` line 229).

**Design decision — keep every bucket as its own primitive, don't pre-aggregate.** The 4-class
rollup produces the single north-star number, but the implementation computes and emits P_τ/E_τ
for **all 7 raw buckets** individually before rolling them up. Reasoning: OL's actual north-star
metric (`NOW.md`: *"D7 return rate among registrants who completed a D0 borrow"*) needs the
D0→D1→D7→D30 curve to stay visible; merging them at the storage layer would make that diagnosis
impossible retroactively, for no computational savings (Matomo returns the fine-grained bucket
per visit for free).

**Actual statsd keys emitted** (note cohorts and classes are namespaced apart — `visitor` is the
name of both and would otherwise collide; and `+` is escaped to `_plus` since it isn't safe in a
Graphite metric path):

```
stats.ol.retention.cohort.{visitor|d0|d1_plus|d7_plus|d14_plus|d30_plus|d90_plus}.patrons.hourly.total
stats.ol.retention.cohort.{...}.engagement.hourly
stats.ol.retention.class.{visitor|registrant|returning|retained}.patrons.hourly.total
stats.ol.retention.class.{...}.engagement.hourly
stats.ol.retention.total_score.hourly
stats.ol.retention.per_patron.hourly
```

**P_τ counts unique patrons, not visits** — keyed on `userId` when present, `visitorId` otherwise.
An earlier draft counted visits, which inflates P_τ for anyone with multiple sessions in the hour.

**⚠️ Important distinction — this is a snapshot metric, not a cohort metric.** `RetentionScore` answers "how much engaged activity happened this hour, broken down by how long patrons have had accounts" — a cross-sectional view. It does NOT answer "of everyone who registered on day X, what fraction came back by day X+7" — a cohort view, which is what the stated north-star metric actually is. True cohort tracking would require Matomo's `setUserId` (a feature meant exactly for tracking known/authenticated users, distinct from anonymous-visitor tracking) to be wired for logged-in patrons — confirmed via the codebase (`setUserId`/`setUserID` does not appear anywhere) and empirically (0 of 50 sampled real visits had `userId` populated) that this is not currently done. Anonymous visitors intentionally cannot be tracked across days (IP rotates daily) — that's correct privacy behavior, not a gap to close. Registered patrons *could* be cohort-tracked (they have a stable account ID + `created` date already), just aren't yet.

**Known gaps.** These are real limits on the score's *accuracy*, not just missing plumbing. The
score is useful and directional today, but do not describe it as finished while these stand:

- **Bot exclusion — still open.** `visitor` counts are not filtered for bot/scraper traffic. Given
  `visitor`'s sheer volume (~25-50x other classes in real samples), its 0.01 weight does not fully
  suppress its contribution (~4,163 of a ~26,523 total in one real 24h sample — comparable to
  `registrant`'s entire contribution). Same underlying problem as the Demand Score's "Add
  `weekly_human_page_views`... requires bot exclusion" item above.
- **`list_create` — still open.** The only remaining unwired event from #12366 (the add-to-list
  action has no tracking attribute anywhere), worth 50pts and currently contributing 0. The
  on-demand script prints this in its output so it can't be silently forgotten.
- **Snapshot ≠ cohort — still open, and the biggest one.** See the distinction below. Needs Matomo
  `setUserId`, which is still absent from the codebase.
- **Zero-value sanity check — DONE** in PR #13213. `gather_retention_scores()` returns a
  `warnings` list, flagging a window with no visits at all, or any class with active patrons but
  zero scored engagement. The cron logs these; the script prints them to stderr. This exists
  because both bugs below presented as a *silent zero* rather than an error.

**Bugs found and fixed 2026-07-16** (in the sandbox `~/Projects/openlibrary-core-vitals-retention-scores`), **both now carried into PR #13213 with regression tests pinning them:**

1. `extract_patron_status()` looked for Custom Dimension 1 under a `customDimensions` dict/list
   structure that `Live.getLastVisitsDetails` **never returns** (it's a flat `dimension1` field).
   Every visit silently defaulted to `visitor` from the sandbox's first commit onward,
   undercounting `RetentionScore` by **~5.85x**.
2. `follow`/`readlog_*` events were wired app-side by PR #12367 (merged 2026-05-06) but the
   scorer's event table was never updated to recognize them — so they scored 0 for months.

Both presented as *plausible-looking numbers*, not errors. That is why the zero-value sanity check
above exists, and why "the numbers look reasonable" is not evidence that this pipeline is correct.

---

### 5. Engagement Score

```
E_τ(t) = Σ_e (w_e × C(e, τ, t)) / P_τ(t)
```

Where:
- `e` = event type ∈ {Read, Edit, ReadingLog, Follow, Pageview}
- `C(e, τ, t)` = count of event `e` by patron class τ in time window `t`
- `w_e` = weight (relative importance) of event `e`
- `P_τ(t)` = number of patrons of class τ in time `t`

**Statsd metrics:** `stats.ol.engagement.(all|returning).(read|edit|readinglog|follow|list|pageview)`
**Matomo metric:** `stats.ol.matomo.bounce_rate`

---

### 6. Participation Score

Measures useful value contributed by patrons to the platform (not to oneself — that's retention).

Unit: **ω-value** — useful, weighted value (either Content or Retention).

**Three metrics (all should be growing):**

| Metric | Formula | Goal |
|---|---|---|
| Quantity | `Count(Participants, t)` | Number of contributors increasing |
| TotalParticipationValueAdded | `Σ_event (w_event × Count(event, t))` | **North star** — total ω-value growing |
| ParticipationValuePerCapita | `TotalValueAdded / Quantity` | Avg contribution per participant growing |

**Participation events** (by humans):
- Book Edit, Author Edit (needs field-level granularity in future phase)
- Work Merge, Author Merge
- Cover uploads
- Series: book added, series created
- Star Ratings
- Total Books Imported
- Reading Log velocity
- Adding books to lists
- Following? ⚠️ UNVERIFIED (flagged with `?` in source)

Full event weights defined in [Open Library Scores Schema](https://docs.google.com/spreadsheets/d/1tt9ekWRMVaNiMc3GKMP09W3YmBeMXoTwKJnxuaispRA/).

**Note:** Community Tags are in limbo — focus on Typed Tags instead (see [[tags]]).

---

## Implementation

### Solr Fields (per Edition record)
- `weekly_demand` — computed by Trending code
- `weighted_usefulness` — demand × usefulness
- `usefulness` (raw score) and `usefulness_pct` (% of Umax)
- `trending_score_weekly_sum` — used to compute `total_demand`

### statsd Keys
- `ol.stats.content_value_score` — CVS
- `stats.ol.engagement.(all|returning).(read|edit|readinglog|follow|list|pageview)`
- `stats.ol.matomo.bounce_rate`

### Engagement Tracking — resolved 2026-07-27: Matomo, not the DB table

The source doc described two candidate approaches without saying which was live. Confirmed against
the codebase:

**Approach 1: Matomo — this is the one that exists.** Custom dimension 1 ("Days Since
Registration") is set per visit by `get_days_registered()` in `openlibrary/accounts/__init__.py`
(merged via #12144), and read back out via `Live.getLastVisitsDetails`. All Retention Score work
builds on this.

**Approach 2: `account_activity` DB table — never built.** No such table, model, or migration
exists anywhere in the repo (`grep -r account_activity` returns nothing). Treat it as a discarded
design option, not a parallel system someone forgot to document.

### Participation — Infogami Transaction Table
Implementation extends the Infogami `transaction` table to join with `transaction_details`. (Source doc ends here — details not yet specified.)

---

## What's Broken / Fragile / Unimplemented

- **Usefulness weight changes = full reindex** — no way to update weights without reindexing all editions in Solr
- **Demand cadence unconfirmed** — source says "every hour?" with a literal `?` ⚠️ UNVERIFIED
- **Engagement implementation ambiguous** — Matomo vs `account_activity` DB table; source describes both without stating which is live ⚠️ UNVERIFIED
- **"Returning Patrons" section empty** — the source document has this section with no content; definition of "returning" for Engagement purposes not fully specified
- **Participation formula draft only** — `100-points * ocaid-edit + …` is described as a "1st draft"; weights not finalized
- **Field-level edit granularity deferred** — participation events track "book edit" not which fields changed; planned for a later phase
- **Matomo code in source doc has copy-paste corruption** — the `<script>` block has duplicated lines; implementation should be verified against actual code
- **GH #9221** (closed via #11849) — moving a book between shelves previously lost the selected edition, corrupting demand signals. Merged fix.

---

## Common Confusion

- **CVS is not a system health metric** — it measures catalog usefulness for patrons, not infrastructure uptime or error rates. See [[infrastructure]] for system health.
- **Demand ≠ page views** — demand is a formula combining reading log activity, historical work counts, and a base floor. Raw page views are not (yet) included.
- **Usefulness raw score vs. percentage** — always use the percentage field (`usefulness_pct`) for sorting/filtering; the raw sum changes meaning when weights change.
- **Participation ≠ Retention** — participation is value contributed to others; retention is value received by oneself. Adding a book to your own reading log is retention; editing a record for others is participation.

---

## Dependencies

**This system depends on:**
- [[search|Solr]] — all scores stored and queried here; CVS requires Trending code for demand computation
- [[features|Reading Log / Bookshelves]] — `bookshelves_books` is the primary demand signal
- Matomo — patron class counts (P_τ) for Retention Score
- statsd — score emission

**What depends on this system:**
- Any dashboard or reporting that tracks OL's health as a product (not infrastructure health)
- Librarian prioritization — CVS/CLS identify which records most need improvement
- [[librarianship]] — participation events include librarian actions (merges, edits)

---

## Related Documents (future ingest candidates)

- [Open Library - Audience Segments](https://docs.google.com/document/d/1aS4jUcPt-qWa5mU4n4Jx1WhYom407rLsKujnjIbE_cI/) — the 3 patron segments that Usefulness Score serves
- [Open Library Scores Schema](https://docs.google.com/spreadsheets/d/1tt9ekWRMVaNiMc3GKMP09W3YmBeMXoTwKJnxuaispRA/edit?gid=303689883) — participation event definitions (different tab/gid from Usefulness Scores Schema below — not yet ingested)

**Ingested:**
- [Usefulness Scores Schema](https://docs.google.com/spreadsheets/d/1tt9ekWRMVaNiMc3GKMP09W3YmBeMXoTwKJnxuaispRA/) — field weights and event definitions. Ingested in full 2026-07-16 as `raw/google-docs/usefulness-scores-schema.md`; folded into the Usefulness Score / BookPageScore formula above.

---

*See [[README]] · [[METHODOLOGY]] for ingest rules*
