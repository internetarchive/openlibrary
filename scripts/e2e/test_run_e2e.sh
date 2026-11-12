#!/usr/bin/env bash
#
# Unit tests for scripts/e2e/run-e2e.sh — the deterministic e2e entrypoint.
#
# These exercise the DETERMINISTIC mechanics (idempotency, the pending post, the
# terminal-status EXIT trap, label-clear, sha-pinning) with NO real GitHub and NO
# real docker:
#
#   * `gh` is replaced by a mock on PATH that records every call to a log file and
#     emits canned commit-status output (controlled by $MOCK_STATUSES).
#   * the heavy e2e step (docker up + playwright) is replaced via the script's
#     $E2E_CMD seam, so a test can make the run pass, fail, or kill itself mid-run.
#   * the worktree add is replaced via the $WORKTREE_ADD_CMD seam.
#
# Run: bash scripts/e2e/test_run_e2e.sh
# Exit 0 = all pass. No arguments.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_E2E="$SCRIPT_DIR/run-e2e.sh"

PASS=0
FAIL=0
FAILED_NAMES=()

# --- tiny assertion helpers -------------------------------------------------
_ok()   { PASS=$((PASS + 1)); printf '  ok   %s\n' "$1"; }
_fail() { FAIL=$((FAIL + 1)); FAILED_NAMES+=("$1"); printf '  FAIL %s\n     %s\n' "$1" "${2:-}"; }

assert_eq() { # name expected actual
  if [[ "$2" == "$3" ]]; then _ok "$1"; else _fail "$1" "expected [$2] got [$3]"; fi
}
assert_contains() { # name haystack-file needle
  if grep -Fq -e "$3" "$2"; then _ok "$1"; else _fail "$1" "expected to find [$3] in $2"; fi
}
assert_not_contains() { # name haystack-file needle
  if grep -Fq -e "$3" "$2"; then _fail "$1" "did NOT expect [$3] in $2"; else _ok "$1"; fi
}

# --- per-test sandbox -------------------------------------------------------
# Builds a throwaway dir with a mock `gh` on PATH and returns env for a run.
# Sets globals: TESTDIR, GH_CALLS, and prepends the mock to PATH.
new_sandbox() {
  TESTDIR="$(mktemp -d)"
  GH_CALLS="$TESTDIR/gh_calls.log"
  : > "$GH_CALLS"
  mkdir -p "$TESTDIR/bin"
  cat > "$TESTDIR/bin/gh" <<'MOCK'
#!/usr/bin/env bash
# Mock gh: record the call, emit canned status contexts for the idempotency GET.
echo "$*" >> "$GH_CALLS"
# The idempotency check asks for commit statuses and filters with --jq
# '.[].context'; emit one context per line from $MOCK_STATUSES (space/newline
# separated). The script does the exact-match itself, so a dumb echo is enough.
case "$*" in
  *state=pending*)
    # Simulate an orchestrator SIGTERM landing WHILE the pending POST is the
    # running foreground gh child (the window finding #1 is about). We've
    # already logged the call above; now deliver the signal to the script.
    if [[ "${MOCK_KILL_ON_PENDING:-}" == "1" ]]; then
      kill -TERM "$PPID" 2>/dev/null
    fi
    ;;
  *state=success*|*state=failure*)
    # Simulate a HUNG terminal gh post: finalize ignores TERM/INT, so without a
    # hard bound this would wedge the script at pending forever.
    if [[ -n "${MOCK_HANG_TERMINAL:-}" ]]; then
      sleep "${MOCK_HANG_TERMINAL}"
    fi
    ;;
  *"/statuses"*)
    # idempotency GET (commit statuses history): emit canned contexts
    if [[ -n "${MOCK_STATUSES:-}" ]]; then
      printf '%s\n' $MOCK_STATUSES
    fi
    ;;
  *"/status"*)
    # combined-status GET for the code-review precondition: emit the review
    # state. Default success so existing tests proceed; override to "" (absent)
    # or "failure" to exercise the stale-trigger no-op.
    printf '%s\n' "${MOCK_REVIEW_STATE-success}"
    ;;
esac
exit "${MOCK_GH_EXIT:-0}"
MOCK
  chmod +x "$TESTDIR/bin/gh"
  export GH_CALLS
  export PATH="$TESTDIR/bin:$PATH"
}

drop_sandbox() {
  [[ -n "${TESTDIR:-}" && -d "$TESTDIR" ]] && rm -rf "$TESTDIR"
  # restore PATH (strip the one entry we prepended)
  export PATH="${PATH#"$TESTDIR/bin:"}"
}

# Run the entrypoint with a given env; capture exit code into RC.
# Usage: run_entry VAR=val VAR2=val2 ...
run_entry() {
  local env=()
  for kv in "$@"; do env+=("$kv"); done
  env \
    PR_NUMBER="${PR_NUMBER:-4242}" \
    REPO="${REPO:-internetarchive/openlibrary}" \
    HEAD_SHA="${HEAD_SHA:-deadbeefdeadbeefdeadbeefdeadbeefdeadbeef}" \
    STATUS_CONTEXT="${STATUS_CONTEXT:-check/tested-e2e}" \
    LABEL="${LABEL:-Needs: e2e testing}" \
    GH_CALLS="$GH_CALLS" \
    "${env[@]}" \
    bash "$RUN_E2E" >"$TESTDIR/out.log" 2>&1
  RC=$?
}

# ===========================================================================
echo "test_run_e2e.sh"

# --- 1. idempotency: context already present => no-op exit 0, no new writes --
new_sandbox
run_entry MOCK_STATUSES="check/tested-e2e" \
          E2E_CMD="echo SHOULD_NOT_RUN" \
          WORKTREE_ADD_CMD="echo SHOULD_NOT_RUN"
assert_eq   "idempotent: exits 0 when status present" 0 "$RC"
assert_not_contains "idempotent: does not re-post pending" "$GH_CALLS" "state=pending"
assert_not_contains "idempotent: does not run e2e"         "$TESTDIR/out.log" "SHOULD_NOT_RUN"
drop_sandbox

# --- 2. happy path: no status yet, e2e passes => pending then success --------
new_sandbox
run_entry MOCK_STATUSES="" \
          E2E_CMD="true" \
          WORKTREE_ADD_CMD="true"
assert_eq   "pass: exit code mirrors success" 0 "$RC"
assert_contains "pass: posts pending"   "$GH_CALLS" "state=pending"
assert_contains "pass: posts success"   "$GH_CALLS" "state=success"
assert_not_contains "pass: never posts failure" "$GH_CALLS" "state=failure"
assert_contains "pass: clears the label" "$GH_CALLS" "--remove-label"
drop_sandbox

# --- 3. failure path: e2e exits non-zero => pending then failure -------------
new_sandbox
run_entry MOCK_STATUSES="" \
          E2E_CMD="exit 7" \
          WORKTREE_ADD_CMD="true"
assert_eq   "fail: exit code is non-zero" 1 "$RC"
assert_contains "fail: posts pending" "$GH_CALLS" "state=pending"
assert_contains "fail: posts failure" "$GH_CALLS" "state=failure"
assert_not_contains "fail: never posts success" "$GH_CALLS" "state=success"
assert_contains "fail: still clears the label" "$GH_CALLS" "--remove-label"
drop_sandbox

# --- 4. THE HARD ONE: killed mid-run (SIGTERM) => trap still posts failure ---
#        Never leaves pending. This is the whole reason it is a script.
#        Faithful simulation: launch the entrypoint in the background with an
#        e2e step that blocks, wait until it has posted `pending`, then deliver
#        an EXTERNAL SIGTERM mid-run (not a self-kill, which would race the
#        RESULT=success assignment). The EXIT trap must still post `failure`.
new_sandbox
env PR_NUMBER=4242 REPO=internetarchive/openlibrary \
    HEAD_SHA=deadbeefdeadbeefdeadbeefdeadbeefdeadbeef \
    STATUS_CONTEXT=check/tested-e2e LABEL="Needs: e2e testing" \
    GH_CALLS="$GH_CALLS" \
    MOCK_STATUSES="" \
    E2E_CMD='while true; do sleep 0.2; done' \
    WORKTREE_ADD_CMD="true" \
    bash "$RUN_E2E" >"$TESTDIR/out.log" 2>&1 &
kpid=$!
for _ in $(seq 1 100); do grep -Fq "state=pending" "$GH_CALLS" && break; sleep 0.1; done
kill -TERM "$kpid" 2>/dev/null
wait "$kpid"; RC=$?
assert_contains "sigterm: posted pending before dying" "$GH_CALLS" "state=pending"
assert_contains "sigterm: EXIT trap posts failure"     "$GH_CALLS" "state=failure"
assert_not_contains "sigterm: never leaves it at success" "$GH_CALLS" "state=success"
# A terminal status must exist — the commit must never be left only-pending.
if grep -Fq "state=failure" "$GH_CALLS"; then
  _ok "sigterm: a terminal status was posted (not left pending)"
else
  _fail "sigterm: a terminal status was posted (not left pending)" "only pending in $GH_CALLS"
fi
if (( RC != 0 )); then _ok "sigterm: exit code is non-zero"; else _fail "sigterm: exit code is non-zero" "got 0"; fi
drop_sandbox

# --- 4b. THE EVEN-HARDER ONE: SIGTERM lands DURING the pending POST ----------
#        (the window where PENDING_POSTED may not be set yet). The mock gh kills
#        the script the instant it posts `pending`. A terminal status must still
#        be posted — the commit must never be left only-pending.
new_sandbox
run_entry MOCK_STATUSES="" \
          MOCK_KILL_ON_PENDING="1" \
          E2E_CMD="true" \
          WORKTREE_ADD_CMD="true"
assert_contains "kill-during-pending-post: pending was posted" "$GH_CALLS" "state=pending"
assert_contains "kill-during-pending-post: terminal status STILL posted (not left pending)" "$GH_CALLS" "state=failure"
drop_sandbox

# --- 4c. HUNG terminal gh post must NOT wedge finalize (bounded write) -------
#        finalize ignores TERM/INT; a hung terminal `gh` would otherwise block
#        forever. The bounded() SIGKILL watchdog must let the script exit well
#        inside the mock's hang time. E2E_STATUS_TIMEOUT=2, mock hangs 20s.
new_sandbox
start=$(date +%s)
run_entry MOCK_STATUSES="" \
          MOCK_HANG_TERMINAL="20" \
          E2E_STATUS_TIMEOUT="2" \
          E2E_CMD="exit 1" \
          WORKTREE_ADD_CMD="true"
dur=$(( $(date +%s) - start ))
if (( dur < 12 )); then _ok "hung-terminal-post: script exits bounded (${dur}s < 12s), not wedged"; \
  else _fail "hung-terminal-post: script exits bounded" "took ${dur}s (hang not bounded)"; fi
drop_sandbox

# --- 5. sha-pinning: worktree is added at the exact HEAD_SHA, detached -------
new_sandbox
# Capture the real worktree-add invocation by having the seam echo its args.
run_entry MOCK_STATUSES="" \
          HEAD_SHA="cafed00dcafed00dcafed00dcafed00dcafed00d" \
          E2E_CMD="true" \
          WORKTREE_ADD_CMD='echo "WT_ARGS: $*" >> "'"$GH_CALLS"'.wt"'
if [[ -f "$GH_CALLS.wt" ]]; then
  assert_contains "sha-pin: worktree add uses --detach" "$GH_CALLS.wt" "--detach"
  assert_contains "sha-pin: worktree add targets the exact HEAD_SHA" "$GH_CALLS.wt" "cafed00dcafed00dcafed00dcafed00dcafed00d"
else
  _fail "sha-pin: worktree add was invoked via the seam" "no $GH_CALLS.wt written"
fi
drop_sandbox

# --- 6. terminal post is guarded: if we never posted pending (died before),
#        we must not fabricate a terminal status. Simulate the gh GET failing
#        so the script aborts before step 2.
new_sandbox
run_entry MOCK_STATUSES="" \
          MOCK_GH_EXIT="1" \
          E2E_CMD="true" \
          WORKTREE_ADD_CMD="true"
assert_not_contains "guard: no terminal status when pending was never posted (success)" "$GH_CALLS" "state=success"
assert_not_contains "guard: no terminal status when pending was never posted (failure)" "$GH_CALLS" "state=failure"
drop_sandbox

# --- 7. missing required inputs => fails loudly, posts nothing ---------------
new_sandbox
run_entry PR_NUMBER="" HEAD_SHA="" MOCK_STATUSES="" E2E_CMD="true" WORKTREE_ADD_CMD="true"
assert_eq   "validation: non-zero exit on missing inputs" 2 "$RC"
assert_not_contains "validation: posts no pending on bad input" "$GH_CALLS" "state=pending"
drop_sandbox

# --- 8. code-review precondition: review absent => no-op, no pending ---------
new_sandbox
run_entry MOCK_STATUSES="" MOCK_REVIEW_STATE="" \
          E2E_CMD="echo SHOULD_NOT_RUN" WORKTREE_ADD_CMD="echo SHOULD_NOT_RUN"
assert_eq   "review-absent: exits 0 no-op" 0 "$RC"
assert_not_contains "review-absent: posts no pending" "$GH_CALLS" "state=pending"
assert_not_contains "review-absent: runs no e2e" "$TESTDIR/out.log" "SHOULD_NOT_RUN"
drop_sandbox

# --- 9. review present but not success (failure/pending) => no-op ------------
new_sandbox
run_entry MOCK_STATUSES="" MOCK_REVIEW_STATE="failure" \
          E2E_CMD="true" WORKTREE_ADD_CMD="true"
assert_eq   "review-failed: exits 0 no-op" 0 "$RC"
assert_not_contains "review-failed: posts no pending" "$GH_CALLS" "state=pending"
drop_sandbox

# --- 10. review=success => proceeds (pending + terminal posted) --------------
new_sandbox
run_entry MOCK_STATUSES="" MOCK_REVIEW_STATE="success" \
          E2E_CMD="true" WORKTREE_ADD_CMD="true"
assert_eq   "review-green: proceeds and succeeds" 0 "$RC"
assert_contains "review-green: posts pending" "$GH_CALLS" "state=pending"
assert_contains "review-green: posts success" "$GH_CALLS" "state=success"
drop_sandbox

# --- 11. REVIEW_STATUS_CONTEXT empty => precondition skipped (runs anyway) ----
new_sandbox
run_entry MOCK_STATUSES="" MOCK_REVIEW_STATE="" REVIEW_STATUS_CONTEXT="" \
          E2E_CMD="true" WORKTREE_ADD_CMD="true"
assert_eq   "review-disabled: proceeds despite absent review" 0 "$RC"
assert_contains "review-disabled: posts pending" "$GH_CALLS" "state=pending"
drop_sandbox

# ===========================================================================
echo
echo "passed: $PASS   failed: $FAIL"
if (( FAIL > 0 )); then
  printf 'FAILED:\n'; printf '  - %s\n' "${FAILED_NAMES[@]}"
  exit 1
fi
exit 0
