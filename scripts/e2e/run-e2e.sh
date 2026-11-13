#!/usr/bin/env bash
#
# run-e2e.sh — the RUN half of the two-workflow e2e GitHub Action (epic #14461).
#
# ============================================================================
# ARCHITECTURE (read before editing — the split is the whole security design):
#
#   RUN  (.github/workflows/e2e_run.yml, `on: pull_request`)
#        executes the PR's code (docker compose up + Playwright @smoke).
#        It runs in a SANDBOX: a read-only GITHUB_TOKEN and NO secrets, on an
#        ephemeral runner. If the PR's code owns the runner there is nothing to
#        steal and no credential to write with. THIS SCRIPT is that job's core.
#        Its only output is a RESULT ARTIFACT (e2e-result.json) — it makes no
#        GitHub API writes, because it holds no token that could.
#
#   POST (.github/workflows/e2e_post.yml, `on: workflow_run`)
#        runs AFTER, in the trusted base-repo context, never checks out fork
#        code, reads the artifact as PURE DATA, and posts the commit status +
#        removes the label + comments on failure. See scripts/e2e/e2e-post.sh.
#
# ----------------------------------------------------------------------------
# THREE NON-NEGOTIABLES (do not weaken without reading epic #14461):
#
#   1. The denylist safety check below is DEFENSE-IN-DEPTH, NOT the primary
#      control. The primary isolation is no-secrets + read-only token +
#      ephemeral runner (enforced by the workflow + the platform). Never remove
#      a sandbox control trusting the denylist to catch what it misses.
#
#   2. This script never posts to GitHub and must never be given a token that
#      can. All authoritative writes live in POST, which treats this script's
#      artifact as data it re-validates — it never executes it.
#
#   3. The status context is POST's concern and sits behind a single swappable
#      constant there (CHECK_PREFIX). This script carries no status context.
#
# ----------------------------------------------------------------------------
# THE RESULT GUARANTEE (the reason this is a script, not a workflow step):
#   An EXIT trap writes a terminal result artifact on EVERY exit path — normal
#   end, error, SIGTERM, SIGINT, or a crash mid-run. The default is `failure`,
#   so a killed or crashed run still yields `failure`, never a missing/ambiguous
#   result. (Belt and suspenders: the workflow uploads the artifact with
#   `if: always()`, and POST fail-safes to `failure` if the artifact is missing
#   or malformed — so a stuck/absent e2e state is structurally impossible.)
#
# ----------------------------------------------------------------------------
# Inputs (env vars, or positional args in this order):
#   PR_NUMBER    (required)  the PR this run is for (recorded in the artifact)
#   HEAD_SHA     (required)  the exact commit under test (sha-pin; recorded)
#   RESULT_FILE  default ./e2e-result.json — where the result artifact is written
#   REPO         default internetarchive/openlibrary — for the compose project name
#   BASE_SHA     the PR base sha; used to compute the changed-paths denylist diff
#                when CHANGED_PATHS / CHANGED_PATHS_CMD are not provided.
#
# Behaviour, in order:
#   1. Validate inputs; arm the result-guarantee trap.
#   2. SAFETY DENYLIST (defense-in-depth): if the diff touches a sandbox/CI-
#      sensitive path, write `failure` and exit WITHOUT executing the PR's
#      (possibly rewritten) harness.
#   3. SHA-PIN: verify the workspace HEAD is exactly HEAD_SHA (the checkout
#      pinned it; this asserts the pin held). Mismatch => failure, no run.
#   4. Run the OL e2e target (docker stack + Playwright @smoke).
#   5. The EXIT trap writes the terminal result artifact. Exit mirrors pass/fail.
#
# ----------------------------------------------------------------------------
# Test seams (used ONLY by scripts/e2e/test_run_e2e.sh; unset in production):
#   E2E_CMD            run this instead of the real docker+playwright step.
#   SHA_VERIFY_CMD     run this instead of `git rev-parse HEAD`.
#   SKIP_SHA_VERIFY    if set, skip the sha-pin check entirely.
#   CHANGED_PATHS      newline-separated changed paths for the denylist.
#   CHANGED_PATHS_CMD  run this to produce the changed paths instead of git diff.
# ----------------------------------------------------------------------------

# No `set -e`: the trap-guaranteed result artifact must not be preempted by an
# incidental non-zero exit before the trap is armed. Errors are handled explicitly.
set -uo pipefail

# --- inputs: positional args override env; env overrides defaults -------------
PR_NUMBER="${1:-${PR_NUMBER:-}}"
HEAD_SHA="${2:-${HEAD_SHA:-}}"
RESULT_FILE="${3:-${RESULT_FILE:-./e2e-result.json}}"
REPO="${4:-${REPO:-internetarchive/openlibrary}}"

E2E_TIMEOUT="${E2E_TIMEOUT:-1800}"          # hard cap on the e2e run (step 4)

# --- state the trap reads ----------------------------------------------------
RESULT="failure"        # default failure: a crash before success => failure
REASON="e2e did not complete"
RAN="false"             # becomes "true" only once the e2e step is entered
RESULT_WRITTEN=0        # write the artifact exactly once
E2E_PID=""              # pid of the backgrounded e2e child, for the signal trap
UNSAFE_PATH=""          # set by safety_check when a denied path is found

log()  { printf '[run-e2e] %s\n' "$*"; }
warn() { printf '[run-e2e] WARN: %s\n' "$*" >&2; }
die()  { printf '[run-e2e] ERROR: %s\n' "$*" >&2; exit "${2:-1}"; }

# Minimal JSON string escaper (reason text is script-controlled, but be safe).
json_str() {
  local s="$1"
  s="${s//\\/\\\\}"; s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"; s="${s//$'\t'/\\t}"; s="${s//$'\r'/\\r}"
  # Strip any remaining raw C0 control bytes (an attacker-chosen path can reach
  # REASON via UNSAFE_PATH): a stray control byte would otherwise make the JSON
  # invalid. No field injection is possible — quotes/backslashes are escaped
  # above — so this only keeps the artifact parseable.
  s="$(printf '%s' "$s" | LC_ALL=C tr -d '\000-\010\013\014\016-\037')"
  printf '"%s"' "$s"
}

# --- the result guarantee ----------------------------------------------------
# Writes the terminal artifact exactly once, atomically. Called by finalize on
# every exit path, so a crash/kill still yields a `failure` result.
write_result() {
  [[ "$RESULT_WRITTEN" == "1" ]] && return 0
  RESULT_WRITTEN=1
  local tmp="${RESULT_FILE}.tmp.$$"
  if printf '{"schema":"ol-e2e-result/1","pr":%s,"head_sha":"%s","result":"%s","reason":%s,"ran":%s}\n' \
      "$PR_NUMBER" "$HEAD_SHA" "$RESULT" "$(json_str "$REASON")" "$RAN" > "$tmp" 2>/dev/null; then
    mv -f "$tmp" "$RESULT_FILE" 2>/dev/null \
      || warn "could not move result artifact into place ($RESULT_FILE)"
  else
    warn "could not write result artifact ($RESULT_FILE)"
    rm -f "$tmp" 2>/dev/null || true
  fi
}

# --- safety denylist (DEFENSE-IN-DEPTH, not the primary control) --------------
# A PR that edits how e2e runs (CI, docker, the harness, install scripts) must
# not have that edited machinery auto-executed in the sandbox; it needs manual
# review. This is a deterministic, auditable path denylist — one array, easy to
# read. It is a second layer behind the no-secrets/read-only/ephemeral sandbox.
is_unsafe_path() {
  case "$1" in
    # CI / container / build machinery, anywhere.
    .github/*|docker/*|scripts/*) return 0 ;;
    Dockerfile|Dockerfile.*|Makefile|package.json|package-lock.json) return 0 ;;
    compose*.yml|compose*.yaml|docker-compose*.yml|docker-compose*.yaml) return 0 ;;
    */Dockerfile|*/Dockerfile.*|*/Makefile|*/package.json) return 0 ;;
    */compose.yml|*/compose.yaml|*/docker-compose.yml|*/docker-compose.yaml) return 0 ;;
    # Files that run arbitrary code during install / test, or redirect a registry.
    .npmrc|*/.npmrc|playwright.config.*|*/playwright.config.*) return 0 ;;
    requirements*.txt|*/requirements*.txt|pyproject.toml|setup.py|setup.cfg) return 0 ;;
  esac
  return 1
}

# Emit the PR's changed paths, one per line. Prefer an explicit list (honoured
# even when empty — an empty list is a real answer, not a missing source), then a
# seam, then a git diff against BASE_SHA. Only with no source AT ALL do we report
# __NO_DIFF_SOURCE__.
get_changed_paths() {
  if [[ -n "${CHANGED_PATHS+x}" ]]; then printf '%s\n' "$CHANGED_PATHS"; return 0; fi
  if [[ -n "${CHANGED_PATHS_CMD:-}" ]]; then eval "$CHANGED_PATHS_CMD"; return $?; fi
  if [[ -n "${BASE_SHA:-}" ]]; then git diff --name-only "$BASE_SHA" "$HEAD_SHA"; return $?; fi
  printf '__NO_DIFF_SOURCE__\n'
}

# 0 = safe to run; 1 = unsafe (sets UNSAFE_PATH). Fails CLOSED when the diff
# cannot be read, and — when DENYLIST_REQUIRED is set (the workflow sets it) —
# also when no source is configured or the list is empty, so a glitched/empty
# changed-files lookup can never silently skip the gate. Without DENYLIST_REQUIRED
# (host/standalone use) a missing source just skips the denylist.
safety_check() {
  local paths p nonempty=0
  if ! paths="$(get_changed_paths)"; then
    UNSAFE_PATH="(could not read the PR diff)"
    return 1
  fi
  if [[ "$paths" == "__NO_DIFF_SOURCE__" ]]; then
    if [[ -n "${DENYLIST_REQUIRED:-}" ]]; then
      UNSAFE_PATH="(no changed-paths source; denylist required)"
      return 1
    fi
    warn "no changed-paths source configured — safety denylist SKIPPED"
    return 0
  fi
  while IFS= read -r p; do
    [[ -z "$p" ]] && continue
    nonempty=1
    if is_unsafe_path "$p"; then UNSAFE_PATH="$p"; return 1; fi
  done <<<"$paths"
  if [[ "$nonempty" == "0" && -n "${DENYLIST_REQUIRED:-}" ]]; then
    UNSAFE_PATH="(empty changed-paths list; denylist required)"
    return 1
  fi
  return 0
}

# --- sha-pin (step 3) --------------------------------------------------------
# The checkout pinned HEAD to HEAD_SHA; this asserts the pin actually held, so a
# misconfigured checkout can never run a different tree than the one we report on.
verify_sha() {
  [[ -n "${SKIP_SHA_VERIFY:-}" ]] && return 0
  local head
  if [[ -n "${SHA_VERIFY_CMD:-}" ]]; then
    head="$(eval "$SHA_VERIFY_CMD" 2>/dev/null)" || return 1
  else
    head="$(git rev-parse HEAD 2>/dev/null)" || return 1
  fi
  [[ "$head" == "$HEAD_SHA" ]]
}

# --- the e2e run (step 4) ----------------------------------------------------
# Returns 0 on pass, non-zero on fail. The work runs as a BACKGROUND child that
# we `wait` on, so a SIGTERM to this script interrupts the wait and runs the trap
# immediately (a foreground child would defer the trap until it exited — for a
# blocking docker/playwright run that could be minutes, during which a timed-out
# CI step's SIGTERM would be swallowed and no result written). The real run is
# additionally wrapped in a timeout so a hung stack bring-up becomes a FAILURE.
COMPOSE_PROJECT="ol-e2e-${PR_NUMBER}-${HEAD_SHA:0:12}"

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

  # The e2e signal (v1): the reliable @smoke anonymous subset. The full
  # `npm run test:e2e` suite has 5 deterministic hydration failures from a
  # from-scratch stack (ol-carousel / ol-shelf-button + logged-in home;
  # `/partials/ReadingState.json` never resolves) — tracked for promotion in
  # #14452. Flip E2E_PLAYWRIGHT_CMD to the full suite once those are resolved.
  local playwright_cmd="${E2E_PLAYWRIGHT_CMD:-npx playwright test --project=desktop --grep @smoke --grep-invert \"logged in\"}"

  # shellcheck disable=SC2016
  local body='
    set -euo pipefail
    docker compose -p "$1" up -d --wait web infobase db memcached home covers mockservices
    npm ci
    npx playwright install chromium chromium-headless-shell
    eval "$2"
  '
  if [[ -n "$timeout_bin" ]]; then
    "$timeout_bin" --signal=TERM "$E2E_TIMEOUT" bash -c "$body" _ "$COMPOSE_PROJECT" "$playwright_cmd" &
  else
    warn "no timeout(1) available; running e2e without a hard time cap"
    bash -c "$body" _ "$COMPOSE_PROJECT" "$playwright_cmd" &
  fi
  E2E_PID=$!
  wait "$E2E_PID"; rc=$?
  E2E_PID=""
  return "$rc"
}

# --- cleanup -----------------------------------------------------------------
cleanup() {
  # In test mode (E2E_CMD seam) no real stack was created — skip the teardown.
  [[ -z "${E2E_CMD:-}" ]] || return 0
  docker compose -p "$COMPOSE_PROJECT" down -v 2>/dev/null || true
}

# --- signal handling ---------------------------------------------------------
# Kill the running e2e child so `wait` returns, record the abort, then exit —
# which runs finalize (the EXIT trap) and writes a `failure` result artifact.
on_signal() {
  local sig="$1"
  [[ -n "$E2E_PID" ]] && kill -TERM "$E2E_PID" 2>/dev/null
  RESULT="failure"
  REASON="aborted by SIG${sig} mid-run"
  warn "received SIG${sig}; aborting e2e and writing a failure result"
  exit $(( 128 + ${2:-15} ))
}

# --- the result-guarantee trap (step 5) --------------------------------------
finalize() {
  local rc=$?
  # Clear EXIT so we don't re-enter; IGNORE (not default) TERM/INT across the
  # write so a second signal can't interrupt it and leave no artifact.
  trap - EXIT
  trap '' TERM INT
  write_result
  cleanup || true
  exit "$rc"
}

main() {
  # --- validate -------------------------------------------------------------
  [[ "$PR_NUMBER" =~ ^[0-9]+$ ]]    || die "PR_NUMBER must be a positive integer" 2
  [[ "$HEAD_SHA" =~ ^[0-9a-f]{40}$ ]] || die "HEAD_SHA must be a 40-char lowercase hex sha" 2
  [[ -n "$RESULT_FILE" ]]          || die "RESULT_FILE is required" 2

  # Arm the result guarantee BEFORE any work, so even a crash writes an artifact.
  trap finalize EXIT
  trap 'on_signal TERM 15' TERM
  trap 'on_signal INT 2' INT

  # --- step 2: safety denylist (defense-in-depth, NOT the primary control) ---
  if ! safety_check; then
    RESULT="failure"; RAN="false"
    REASON="unsafe to auto-run: changes ${UNSAFE_PATH:-a sandbox/CI-sensitive path}; needs manual review"
    log "$REASON"
    exit 1   # -> finalize writes failure, ran=false; the e2e step never runs
  fi

  # --- step 3: sha-pin ------------------------------------------------------
  if ! verify_sha; then
    RESULT="failure"; RAN="false"
    REASON="sha-pin mismatch: workspace HEAD is not $HEAD_SHA"
    warn "$REASON"
    exit 1   # -> finalize writes failure
  fi

  # --- step 4: run the e2e target -------------------------------------------
  RAN="true"
  if run_e2e; then
    RESULT="success"; REASON="e2e passed (@smoke)"
  else
    RESULT="failure"; REASON="e2e failed (@smoke)"
  fi
  log "e2e result: $RESULT"

  # --- step 5 happens in finalize; exit code mirrors pass/fail --------------
  [[ "$RESULT" == "success" ]] && exit 0 || exit 1
}

# Only run when executed, not when sourced (keeps functions unit-testable).
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
