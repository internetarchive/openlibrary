# Open Library e2e test plan

> Authored and maintained by `@openlibrary-bot` (epic #14461). This document is
> the persistent, human-readable definition of what the `tested-e2e` gate
> verifies and what "pass" means. Per-run results accumulate natively — in each
> PR's commit-status history and in the retained workflow-run artifacts
> (`e2e-result.json` + the Playwright HTML report) — not in a bespoke ledger.

## What authorises a run (the gate vs. the trigger)

The `Needs: e2e testing` label is only a **trigger**. The **gate** is the
SHA-bound `code-review` commit status: before it brings up docker, RUN
independently re-checks that `code-review` is `success` on the *runtime* head
commit (read via the read-only token — no secret). A stale or mis-applied label
can never, by itself, authorise executing untrusted code: if `code-review` is not
green on this exact commit (absent / pending / failure / error all count), e2e
fail-safes to `failure` and the PR's code is **never executed**. This is the
pipeline's honesty rule applied to e2e, and the belt behind the untrusted→e2e
path. (`code-review` is produced by #14455, so e2e's go-live depends on it.)

## What runs

A label-triggered, code-review-gated GitHub Action runs the Open Library
Playwright end-to-end suite against a from-scratch docker stack, on the PR's
exact head commit.

- **Command (v1):**
  `npx playwright test --project=desktop --grep @smoke --grep-invert "logged in"`
- **Stack:** `docker compose up -d --wait web infobase db memcached home covers mockservices`
- **Browser:** Chromium (headless), installed per-run and cached per-PR.

## What "pass" means (v1 signal = the `@smoke` anonymous subset)

The gate is **green** only when every `@smoke`-tagged anonymous test passes:
server-rendered page loads returning HTTP 200 with the expected headings across
home, search, subjects, work, edition, author, and the login page, plus the
valid-credentials login flow.

### Why the subset, not the full suite

Measured on a clean stack (3 runs, identical results): the full
`npm run test:e2e` suite fails **5 specs deterministically** — the
`ol-carousel` / `ol-shelf-button` component-hydration tests and the logged-in
home account-menu, whose `/partials/ReadingState.json` fetches never resolve
from a from-scratch image (the served bundle is a stale prebuilt one). This is
an e2e-environment gap, not a product regression. A flaky or always-red gate
false-fails every PR, so v1 gates on the reliable subset. The subset was green
3/3 in ~12s.

**Promotion:** flip `E2E_PLAYWRIGHT_CMD` to the full suite once the e2e image
builds the frontend fresh (tracked in #14452).

## How the result is produced and reported

Two workflows, split for fork safety (see the headers of
`.github/workflows/e2e_run.yml` and `e2e_post.yml`):

1. **RUN** (`pull_request`, sandboxed: read-only token, **no secrets**, ephemeral
   runner) executes the PR's code and writes `e2e-result.json`
   (`success`/`failure`, never absent — an EXIT trap guarantees it on crash,
   kill, or timeout). It makes no GitHub writes.
2. **POST** (`workflow_run`, trusted, never checks out fork code) reads that
   artifact as data, validates it, and posts the `tested-e2e` commit status,
   clears the `Needs: e2e testing` label, and comments on failure.

There is **no `pending`** state: anything short of a clean success artifact
resolves to `failure`. e2e is an **optional** check (not required for merge) and
**never auto-runs on untrusted code** — it is triggered by the maintainer-only
label, authorised by the SHA-bound `code-review` gate above, with an auto-run
path on push only for `openlibrary-bot`'s own same-repo PRs.

## Local / CI verification of the harness itself

The deterministic logic is unit-tested with no real GitHub, docker, or git:

```bash
bash scripts/e2e/test_run_e2e.sh    # RUN execution core + result guarantee + denylist
bash scripts/e2e/test_e2e_post.sh   # POST artifact validation + fail-safe decisions
```
