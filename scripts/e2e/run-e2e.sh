#!/usr/bin/env bash
#
# run-e2e.sh — the deterministic entrypoint a forge-dispatched e2e agent invokes
# to produce the `ada/e2e` commit status on a PR.
#
# It is a SCRIPT, not a prompt, for one reason: a stuck `pending` on a required
# check blocks a branch-protection merge forever, so the terminal-status post has
# to be UNCONDITIONAL. An EXIT trap guarantees `success` or `failure` is posted
# even if the e2e run crashes, is aborted, or is killed with SIGTERM.
#
# Division of labor (honor it): this SCRIPT owns the deterministic mechanics and
# the authoritative GitHub writes (commit status + label). The AGENT that wraps
# it owns orchestration and a richer human-readable failure comment. The script
# must guarantee a terminal status even if everything around it crashes.
#
# ----------------------------------------------------------------------------
# Inputs (env vars, or positional args in this order):
#   PR_NUMBER       (required)  the PR to label/report on
#   REPO            default internetarchive/openlibrary
#   HEAD_SHA        (required)  the exact commit to pin, status, and test
#   STATUS_CONTEXT  default ada/e2e
#   LABEL           default "Needs: e2e testing"
#
# Behaviour, in order:
#   1. IDEMPOTENCY  — GET statuses for HEAD_SHA; if STATUS_CONTEXT already
#      present (pending OR terminal) exit 0 as a no-op. (guards races/restarts)
#   2. POST STATUS_CONTEXT=pending on HEAD_SHA.
#   3. git worktree add --detach at the exact HEAD_SHA (pin the sha).
#   4. Run the OL e2e target in docker (stack up + Playwright suite).
#   5. TERMINAL STATUS via an EXIT trap — success/failure, NEVER pending.
#   6. Clear LABEL on the PR.
#   7. Clean up the worktree. Exit code mirrors pass/fail.
#
# Identity: the script hardcodes no account. It inherits the `gh` identity from
# the environment. It only sets a *default* GH_CONFIG_DIR (the fleet bot config)
# when the environment has not already chosen one — so identity stays fully
# env-overridable (an injected GH_TOKEN or GH_CONFIG_DIR wins). It never reads
# anything inside that config dir; the path is all `gh` needs.
#
# Scope (v1): SAME-REPO PRs only. Fork PRs are skipped upstream by the forge
# (docker e2e on fork code = executing untrusted code locally) and routed to a
# separate sandboxed phase. This script assumes trusted same-repo code, but
# still pins the sha and runs only the defined e2e target.
#
# ----------------------------------------------------------------------------
# Test seams (used ONLY by scripts/e2e/test_run_e2e.sh; unset in production):
#   E2E_CMD         if set, run this instead of the real docker+playwright step.
#   WORKTREE_ADD_CMD if set, run this instead of the real `git worktree add`.
#   gh              intercepted by a mock on PATH in the unit tests.
# ----------------------------------------------------------------------------

# No `set -e`: a trap-guaranteed terminal status must not be preempted by an
# incidental non-zero exit before the trap is armed. We handle errors explicitly.
set -uo pipefail

# --- identity default (env-overridable; never hardcoded, never read) ---------
# local openlibrary-bot gh config dir; override via GH_CONFIG_DIR (or GH_TOKEN).
: "${GH_CONFIG_DIR:=$HOME/.config/gh-ol-bot}"
export GH_CONFIG_DIR

# --- inputs: positional args override env; env overrides defaults ------------
PR_NUMBER="${1:-${PR_NUMBER:-}}"
REPO="${2:-${REPO:-internetarchive/openlibrary}}"
HEAD_SHA="${3:-${HEAD_SHA:-}}"
STATUS_CONTEXT="${4:-${STATUS_CONTEXT:-ada/e2e}}"
LABEL="${5:-${LABEL:-Needs: e2e testing}}"
# The review gate that must be green on HEAD_SHA for e2e to run. Set empty to
# disable the precondition.
REVIEW_STATUS_CONTEXT="${6-${REVIEW_STATUS_CONTEXT-ada/code-review}}"

E2E_TIMEOUT="${E2E_TIMEOUT:-1800}"          # hard cap on the e2e run (step 4)
E2E_STATUS_TIMEOUT="${E2E_STATUS_TIMEOUT:-60}"  # hard cap on each terminal gh write

# --- state the trap reads ----------------------------------------------------
RESULT="failure"        # default failure: a crash before success => failure
PENDING_POSTED=0        # only finalize a terminal status if WE posted pending
TERMINAL_POSTED=0       # post the terminal status exactly once
WORKTREE_DIR=""         # set by add_worktree; cleaned up by finalize
E2E_PID=""              # pid of the backgrounded e2e child, for the signal trap

log()  { printf '[run-e2e] %s\n' "$*"; }
warn() { printf '[run-e2e] WARN: %s\n' "$*" >&2; }
die()  { printf '[run-e2e] ERROR: %s\n' "$*" >&2; exit "${2:-1}"; }

# --- GitHub writes (all via plain `gh`, identity inherited from env) ---------

# 0 = STATUS_CONTEXT already on HEAD_SHA; 1 = absent; 2 = the gh read failed.
check_existing_status() {
  local out
  if ! out="$(gh api "repos/$REPO/commits/$HEAD_SHA/statuses" --jq '.[].context' 2>/dev/null)"; then
    return 2
  fi
  grep -Fxq "$STATUS_CONTEXT" <<<"$out"
}

# 0 = REVIEW_STATUS_CONTEXT is green (state=success) on HEAD_SHA; 1 = not green
# (absent or any non-success latest state); 2 = the gh read failed.
review_is_green() {
  local out
  if ! out="$(gh api "repos/$REPO/commits/$HEAD_SHA/status" \
      --jq ".statuses[]? | select(.context == \"$REVIEW_STATUS_CONTEXT\") | .state" 2>/dev/null)"; then
    return 2
  fi
  grep -Fxq "success" <<<"$out"
}

post_status() {
  local state="$1" desc="${2:-}"
  gh api -X POST "repos/$REPO/statuses/$HEAD_SHA" \
    -f state="$state" \
    -f context="$STATUS_CONTEXT" \
    -f description="$desc" >/dev/null
}

clear_label() {
  gh pr edit "$PR_NUMBER" --repo "$REPO" --remove-label "$LABEL" >/dev/null 2>&1
}

# A compose project / worktree key unique to this (PR, sha). Including the sha
# keeps a force-push re-dispatch (same PR, new HEAD_SHA) from colliding on the
# docker project name — so one run's teardown can't rip down the other's stack.
COMPOSE_PROJECT="ol-e2e-${PR_NUMBER}-${HEAD_SHA:0:12}"
WORKTREE_PARENT=""      # throwaway mktemp dir holding the worktree; cleaned up

# --- worktree (step 3) -------------------------------------------------------
add_worktree() {
  WORKTREE_PARENT="$(mktemp -d)"
  WORKTREE_DIR="${WORKTREE_PARENT}/ol-e2e-${PR_NUMBER}-${HEAD_SHA:0:12}"
  if [[ -n "${WORKTREE_ADD_CMD:-}" ]]; then
    # Test seam: hand the seam the exact args we'd give git, so a test can
    # assert on `--detach` and the pinned sha without touching the repo.
    set -- --detach "$WORKTREE_DIR" "$HEAD_SHA"
    eval "$WORKTREE_ADD_CMD"
    return $?
  fi
  git worktree add --detach "$WORKTREE_DIR" "$HEAD_SHA"
}

# --- the e2e run (step 4) ----------------------------------------------------
# Returns 0 on pass, non-zero on fail. The work runs as a BACKGROUND child that
# we `wait` on, so a SIGTERM to this script interrupts the wait and runs the
# trap immediately (a foreground child would defer the trap until it exited —
# which, for a blocking docker/playwright run, is exactly the stuck-pending
# failure we must avoid). The real run is additionally wrapped in a timeout so
# a hung stack bring-up becomes a FAILURE, never a stuck pending.
run_e2e() {
  local rc
  if [[ -n "${E2E_CMD:-}" ]]; then
    bash -c "$E2E_CMD" &   # child: an `exit N` inside stays contained
    E2E_PID=$!
    wait "$E2E_PID"; rc=$?
    E2E_PID=""
    return "$rc"
  fi

  local timeout_bin
  timeout_bin="$(command -v timeout || command -v gtimeout || true)"

  # The e2e signal (v1). Measured on a clean stack at this PR's tree (== master
  # for every app file): the FULL `npm run test:e2e` suite fails 5 specs
  # deterministically — the ol-carousel / ol-shelf-button component-hydration
  # tests and the logged-in home account-menu, whose `/partials/ReadingState.json`
  # fetches never resolve from a from-scratch stack (3 runs, same 5 red). The
  # `@smoke` anonymous subset (server-rendered page loads + HTTP-200 + headings +
  # the valid-credentials login flow across home/search/subjects/work/edition/
  # author/login/my-books) was green 3/3 in ~12s. A flaky or failing gate false-
  # fails every e2e, so v1 gates on that reliable subset. Promote to the full
  # suite by setting E2E_PLAYWRIGHT_CMD once the hydration failures are resolved.
  local playwright_cmd="${E2E_PLAYWRIGHT_CMD:-npx playwright test --project=desktop --grep @smoke --grep-invert \"logged in\"}"

  local proc="$COMPOSE_PROJECT"
  # shellcheck disable=SC2016
  local body='
    set -euo pipefail
    cd "$1"
    OL_MOUNT_DIR="$1" docker compose -p "$2" up -d --wait \
      web infobase db memcached home covers mockservices
    npm ci
    npx playwright install chromium chromium-headless-shell
    eval "$3"
  '
  if [[ -n "$timeout_bin" ]]; then
    "$timeout_bin" --signal=TERM "$E2E_TIMEOUT" bash -c "$body" _ "$WORKTREE_DIR" "$proc" "$playwright_cmd" &
  else
    warn "no timeout(1) available; running e2e without a hard time cap"
    bash -c "$body" _ "$WORKTREE_DIR" "$proc" "$playwright_cmd" &
  fi
  E2E_PID=$!
  wait "$E2E_PID"; rc=$?
  E2E_PID=""
  return "$rc"
}

# --- cleanup (step 7) --------------------------------------------------------
cleanup_worktree() {
  [[ -n "$WORKTREE_DIR" ]] || return 0
  # In test mode (seams set) no real worktree/stack was created — skip.
  [[ -z "${WORKTREE_ADD_CMD:-}" ]] || return 0
  git worktree remove --force "$WORKTREE_DIR" 2>/dev/null || rm -rf "$WORKTREE_DIR"
  # Remove the throwaway parent mktemp dir too (not just the worktree inside it).
  [[ -n "$WORKTREE_PARENT" ]] && rm -rf "$WORKTREE_PARENT"
  if [[ -z "${E2E_CMD:-}" ]]; then
    docker compose -p "$COMPOSE_PROJECT" down -v 2>/dev/null || true
  fi
}

# --- the terminal guarantee (step 5) ----------------------------------------
# Runs on EVERY exit path once the trap is armed: normal end, error, SIGTERM,
# SIGINT. Posts the terminal status exactly once, but only if WE posted pending
# (so a death before step 2 does not fabricate a status for someone else).
# Run a command with a hard wall-clock bound, SIGKILLing it if it overruns.
# Used for the terminal GitHub writes inside finalize, where TERM/INT are
# ignored: a hung `gh` post would otherwise wedge finalize and effectively leave
# the commit at pending, immune to everything but SIGKILL. SIGKILL can't be
# ignored, so the watchdog can always reap the child. Pure bash — no dependency
# on timeout(1), which isn't present everywhere. Returns the child's exit code,
# or 137 if it was killed on timeout.
bounded() {
  local secs="$1"; shift
  "$@" & local pid=$!
  ( sleep "$secs"; kill -KILL "$pid" 2>/dev/null ) & local watchdog=$!
  local rc=0
  wait "$pid" 2>/dev/null || rc=$?
  kill -KILL "$watchdog" 2>/dev/null
  wait "$watchdog" 2>/dev/null || true
  return "$rc"
}

# Signal handler: kill the running e2e child (if any) so `wait` returns, then
# exit — which runs finalize (the EXIT trap) and posts the terminal status.
on_signal() {
  local sig="$1"
  [[ -n "$E2E_PID" ]] && kill -TERM "$E2E_PID" 2>/dev/null
  warn "received SIG${sig}; aborting e2e and posting terminal status"
  exit $(( 128 + ${2:-15} ))
}

finalize() {
  local rc=$?
  # Clear EXIT so we don't re-enter, but IGNORE (not default) TERM/INT across
  # the terminal post: an orchestrator that escalates with a second SIGTERM must
  # not kill us mid-post and leave the commit stuck at pending. (SIGKILL is still
  # untrappable — that edge belongs to the wrapping agent's richer handling.)
  trap - EXIT
  trap '' TERM INT
  if [[ "$PENDING_POSTED" == "1" && "$TERMINAL_POSTED" == "0" ]]; then
    TERMINAL_POSTED=1
    log "posting terminal status: $RESULT"
    # Hard-bound both writes so a hung gh can't wedge finalize at pending.
    bounded "$E2E_STATUS_TIMEOUT" post_status "$RESULT" "e2e ${RESULT}" || warn "terminal status post failed/timed out"
    bounded "$E2E_STATUS_TIMEOUT" clear_label || warn "label clear failed/timed out"
  fi
  cleanup_worktree || true
  exit "$rc"
}

main() {
  # --- validate -------------------------------------------------------------
  [[ -n "$PR_NUMBER" ]] || die "PR_NUMBER is required" 2
  [[ -n "$HEAD_SHA"  ]] || die "HEAD_SHA is required" 2

  # --- step 1: idempotency --------------------------------------------------
  local st=0
  check_existing_status || st=$?
  case "$st" in
    0) log "status '$STATUS_CONTEXT' already present on $HEAD_SHA — no-op"; exit 0 ;;
    2) die "could not read commit statuses for $HEAD_SHA (gh/auth?)" 3 ;;
    *) : ;;  # 1 = absent, proceed
  esac

  # --- step 1.5: code-review precondition -----------------------------------
  # e2e should only run on a head whose review passed. If the review gate isn't
  # green on THIS sha, the forge label that triggered us is stale (a push
  # invalidated the review), so no-op. This is BEFORE we arm the trap or post
  # pending, so the no-op is trivially terminal-safe — no ada/e2e pending is
  # ever left. Skipped when REVIEW_STATUS_CONTEXT is empty.
  if [[ -n "$REVIEW_STATUS_CONTEXT" ]]; then
    local rv=0
    review_is_green || rv=$?
    case "$rv" in
      0) : ;;  # green, proceed
      1) log "review '$REVIEW_STATUS_CONTEXT' not green on $HEAD_SHA — stale trigger; no-op"; exit 0 ;;
      2) die "could not read review status for $HEAD_SHA (gh/auth?)" 3 ;;
    esac
  fi

  # Arm the terminal guarantee BEFORE posting pending. TERM/INT re-exit through
  # the EXIT trap so finalize always runs.
  trap finalize EXIT
  trap 'on_signal TERM 15' TERM
  trap 'on_signal INT 2' INT

  # --- step 2: pending ------------------------------------------------------
  # Claim the pending status OPTIMISTICALLY, *before* the POST. If a SIGTERM
  # lands while the POST is the running foreground child, bash defers the trap
  # until the POST returns, then runs finalize — which must see PENDING_POSTED=1
  # so it posts a terminal status. Setting the flag after the POST loses that
  # race and leaves the commit stuck at pending (the one outcome we forbid).
  # The trade: if the POST never actually reached GitHub, finalize posts a
  # terminal `failure` instead of nothing — but RESULT defaults to failure, a
  # terminal failure is safe and re-dispatchable, and never a stuck pending.
  PENDING_POSTED=1
  if ! post_status "pending" "e2e running"; then
    warn "failed to post pending status for $HEAD_SHA; will still finalize terminal"
    RESULT="failure"
    exit 4   # -> finalize posts a terminal failure (never leaves pending)
  fi
  log "posted pending for PR #$PR_NUMBER @ $HEAD_SHA"

  # --- step 3: pin the sha in a detached worktree ---------------------------
  if ! add_worktree; then
    warn "git worktree add failed; reporting failure"
    RESULT="failure"
    exit 1   # -> finalize posts failure
  fi

  # --- step 4: run the e2e target ------------------------------------------
  if run_e2e; then
    RESULT="success"
  else
    RESULT="failure"
  fi
  log "e2e result: $RESULT"

  # --- steps 5/6/7 happen in finalize; exit code mirrors pass/fail ----------
  [[ "$RESULT" == "success" ]] && exit 0 || exit 1
}

# Only run when executed, not when sourced (keeps functions unit-testable).
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
