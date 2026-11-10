# Open Library — Development Process (State Model)

**Status:** draft · **Owner:** Ada program lead · **This file is the home** for the
canonical, objectively-queryable state model that every Open Library work item moves
through. Per-class processes (security, dependencies, contributor review) are
*specializations* of this spine and reference it rather than redefining it.

---

## Why this exists

"Where is this work?" must have **one right answer, computed from primary sources** —
not inferred from an agent's narrative, not read like tea leaves. This document defines
the states, the objective query that places an item in **exactly one** of them, the rule
to leave each state, and what (if anything) each state communicates to the operator.

If an item's state cannot be computed from GitHub plus the PR's `ada-status` block, that
is a defect in this model to fix here — not a judgment call to make per item.

## First principle: state is a function of primary sources

Every state below is defined by a query over authorities **other processes cannot
silently change**:

- **PR state** — `gh pr view <N> --json state,isDraft`  → `draft｜open｜merged｜closed`
- **Labels** — `Needs: Staff Decision`, `Needs: Response`, `Needs: Changes`
- **CI** — `gh pr checks <N>`
- **The `ada-status` block** in the PR body — `State`, `Updated`, and
  `Adversarial-review <reviewer> <head-sha> <PASS｜FAIL>`
- **Issue / advisory** existence and number

The `ada-status` schema (states, the RAN/READ split, the sha-pinned adversarial-review
line) is defined in `.claude/agents/CONTRIBUTING.md` and is the machine anchor for the
states below.

## The graph

The funnel is a **graph, not a line** — items move *backward* on any failure. Every
backward edge is itself queryable (a `FAIL` review line, a red check, a removed label).

| # | State | Objective definition (the query that proves it) | Exit gate (to advance) | → Operator |
|---|-------|--------------------------------------------------|------------------------|-----------|
| 0 | Idea | nothing numbered exists | become a numbered issue/advisory | — |
| 1 | Created | open issue/advisory, numbered, no agent | an Ada is dispatched | — |
| 2 | Dispatched | `pr-{N}` agent registered (`--meta pr=N`) or `openlibrary-bot` assigned | plan posted | — |
| 3 | Planned (/Gated) | draft PR open; plan is the first PR comment (checkboxes). **Gated** iff `Needs: Staff Decision` present | gate cleared (if any); development begins | **only if gated** — one line, operator's decision |
| 4 | In development | PR `isDraft=true`; `ada-status State=investigating` | code complete | — |
| 5 | Review requested | review requested on the current head-sha | review returns a verdict | — |
| 6 | Review satisfied | `Adversarial-review` line is `PASS` **and its head-sha == current head**; for contributor PRs, `Needs: Changes` absent | end-to-end verification | — |
| 7 | e2e tested | CI green in Docker **and** `ada-status` RAN column populated at current head-sha | lead greenlight | — |
| 8 | Lead greenlit | division/security lead sign-off recorded at current head-sha | out of draft | — |
| 9 | **Ready for review** | PR `state=open` **and not draft**, `ada-status State=ready-for-review`, adversarial head-sha matches | operator merges | **YES** — on the operator's queue |
| 10 | Merged | `gh pr view` `state=MERGED` | deploy / cleanup | recorded, not announced |
| 11 | Deployed / Done | commit on master + deploy verified; worktree cleaned | — | recorded |

**Backward edges:** 6→4 (review not satisfied), 7→4 (e2e red), 8→4 (lead rejects),
9→4 (operator requests changes). A `ready-for-review` item whose adversarial head-sha no
longer matches the head has silently fallen back to state 6 and is **not** ready; the
sha match is what makes that falsifiable (PAM #56).

## What reaches the operator — exactly three things

1. **Ready (state 9)** — on the queue, one line each: `URL · type · severity · whose-move`.
2. **Blocked-on-operator** — an item stuck because *only the operator* holds the decision
   or the access: a merge, a disclosure, a permission/scope grant. One line: what the
   operator must do, and confirmation that nothing else is blocked behind it.
3. **Harm / unsafe** — immediately, in plain words.

Everything in states 1–8 is in-flight and **silent by design**. Silence means
"progressing, our move," and is itself verifiable (the item computes to a non-9,
non-blocked state). No war-room briefs; no status-of-the-universe.

## Class specializations (same spine, extra stops)

Each class maps onto the spine and adds **only** the stops its domain requires. The
authoritative per-class state table lives with each lead and **must reference this file
as the spine**.

- **Security advisories — Locke.** Adds admin-gated stops between 8 and 10: create the
  temporary private fork (admin-only, batchable), merge from the advisory panel, verify
  on master, publish/disclose. Keystone: the fix is proven green on a real branch
  **before** it touches the advisory fork, so the fork is landing-only and needs no CI.
  → `.claude/agents/locke.md` + Locke's pipeline doc.
- **Dependencies (Renovate) — Reno** (charter held by Locke until Reno is live). Specializes
  4–7: batch by ecosystem → test each upgrade against real Docker with a **minimum-test-count
  floor** (a green suite that ran zero tests is not green) → bisect on red (an
  upstream-capped upgrade is **blocked, not red**) → emit one per-upgrade PR, out of draft,
  carrying its Docker evidence (test count, pass count, image digests). Runner = the
  forge-local engine.
- **Contributor PR review — Wally.** Specializes 5–6: an agentic first-round review plus a
  `Needs: Changes` triage label so staff skip non-green / non-clean PRs. Detection must run
  **where resolution happens**, not only at the repo surface (a dependency cloned at a
  pinned SHA inside a Dockerfile is invisible to repo-level scanners).

## Computing "where are we"

The state of the whole funnel is the union of each open item's computed state. This is
**mechanizable**: PAM #56 already reads the `ada-status` block and fires on the state-9
gate. Extending that predicate to emit, for every open item, its
`(number, type, severity, computed-state)` *is* the diagram the operator can request at
any instant — exactly which issues sit at each stage, by severity and type.

Until that emitter is built, the states above are still computed the same way by hand;
the per-state queries in the table are the contract either way. The automation is an
optimization of the query, never a redefinition of the state.
