#!/usr/bin/env bash
#
# test_run_e2e.sh — unit tests for scripts/e2e/run-e2e.sh, the RUN execution core.
#
# The RUN job holds no GitHub token: its only observable is the RESULT ARTIFACT
# it writes. These tests assert on that artifact (via jq), with no real GitHub,
# docker, or git — the e2e step, the sha check, and the changed-paths source are
# all driven through seams.
#
# Covers wally's prove-the-test-fails requirements:
#   (a) a crash / external kill mid-run still yields a `failure` artifact.
#   (c) the unsafe-path denylist yields `failure` WITHOUT executing the harness.

# SC2015: `[[ cond ]] && ok || bad` is intentional — ok/bad always return 0, so
# the `bad` branch never runs when the condition holds. SC1090: the guard test
# sources the script by a computed path on purpose.
# shellcheck disable=SC2015,SC1090
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN="$HERE/run-e2e.sh"
GOODSHA="abcdef0123456789abcdef0123456789abcdef01"
TESTDIR=""

pass=0; fail=0
ok()  { printf '  ok   %s\n' "$1"; pass=$((pass+1)); }
bad() { printf '  FAIL %s\n     %s\n' "$1" "${2:-}"; fail=$((fail+1)); }

setup() { TESTDIR="$(mktemp -d)"; }
teardown() { [[ -n "$TESTDIR" && -d "$TESTDIR" ]] && rm -rf "$TESTDIR"; }

# Field from the result artifact, or "" if the file is missing. No `// empty`:
# that would turn a boolean `false` (e.g. .ran) into "" since `//` treats false
# as empty. An absent field prints "null", which simply won't match assertions.
rf() { [[ -f "$TESTDIR/result.json" ]] && jq -r "$1" "$TESTDIR/result.json" 2>/dev/null || true; }

# Run the entrypoint with safe defaults; extra VAR=val args override.
# Default: sha check skipped, a trivially-safe changed path, result in TESTDIR.
run_entry() {
  env PR_NUMBER=4242 HEAD_SHA="$GOODSHA" \
      RESULT_FILE="$TESTDIR/result.json" \
      SKIP_SHA_VERIFY=1 CHANGED_PATHS="openlibrary/app.py" \
      "$@" bash "$RUN" >"$TESTDIR/out.log" 2>&1
  RC=$?
}

echo "test_run_e2e.sh"

# --- 1. happy path: safe diff + e2e passes => success artifact ---------------
setup
run_entry E2E_CMD="true"
[[ $RC -eq 0 ]] && ok "pass: exit 0" || bad "pass: exit 0" "rc=$RC"
[[ "$(rf .result)" == success ]] && ok "pass: result=success" || bad "pass: result=success" "$(cat "$TESTDIR/result.json" 2>/dev/null)"
[[ "$(rf .ran)" == true ]] && ok "pass: ran=true" || bad "pass: ran=true"
[[ "$(rf .pr)" == 4242 ]] && ok "pass: pr recorded" || bad "pass: pr"
[[ "$(rf .head_sha)" == "$GOODSHA" ]] && ok "pass: head_sha recorded" || bad "pass: head_sha"
teardown

# --- 2. failure path: e2e exits non-zero => failure artifact, exit mirrors ---
setup
run_entry E2E_CMD="exit 7"
[[ $RC -ne 0 ]] && ok "fail: non-zero exit" || bad "fail: non-zero exit" "rc=$RC"
[[ "$(rf .result)" == failure ]] && ok "fail: result=failure" || bad "fail: result=failure"
[[ "$(rf .ran)" == true ]] && ok "fail: ran=true" || bad "fail: ran=true"
teardown

# --- 3. (a) killed mid-run (SIGTERM) => trap STILL writes failure ------------
#        The whole reason this is a script. Launch it with an e2e step that
#        signals it has started then blocks; once started, deliver an external
#        SIGTERM; the EXIT trap must still write a `failure` artifact.
setup
STARTED="$TESTDIR/started"
env PR_NUMBER=4242 HEAD_SHA="$GOODSHA" RESULT_FILE="$TESTDIR/result.json" \
    SKIP_SHA_VERIFY=1 CHANGED_PATHS="openlibrary/app.py" \
    E2E_CMD="touch '$STARTED'; while true; do sleep 0.2; done" \
    bash "$RUN" >"$TESTDIR/out.log" 2>&1 &
kpid=$!
for _ in $(seq 1 100); do [[ -f "$STARTED" ]] && break; sleep 0.1; done
kill -TERM "$kpid" 2>/dev/null
wait "$kpid" 2>/dev/null; krc=$?
[[ -f "$TESTDIR/result.json" ]] && ok "sigterm: artifact written" || bad "sigterm: artifact written"
[[ "$(rf .result)" == failure ]] && ok "sigterm: result=failure (never absent)" || bad "sigterm: result=failure"
[[ "$(rf .reason)" == *abort* || "$(rf .reason)" == *SIG* ]] && ok "sigterm: reason notes the abort" || bad "sigterm: reason" "$(rf .reason)"
[[ $krc -gt 128 ]] && ok "sigterm: exit code reflects the signal" || bad "sigterm: exit code" "krc=$krc"
teardown

# --- 4. (c) unsafe denylist path => failure WITHOUT executing the harness ----
setup
SENTINEL="$TESTDIR/e2e-ran"
run_entry CHANGED_PATHS=".github/workflows/evil.yml" E2E_CMD="touch '$SENTINEL'"
[[ $RC -ne 0 ]] && ok "unsafe: non-zero exit" || bad "unsafe: non-zero exit" "rc=$RC"
[[ "$(rf .result)" == failure ]] && ok "unsafe: result=failure" || bad "unsafe: result=failure"
[[ "$(rf .ran)" == false ]] && ok "unsafe: ran=false" || bad "unsafe: ran=false"
[[ ! -f "$SENTINEL" ]] && ok "unsafe: harness NEVER executed" || bad "unsafe: harness executed (!)"
[[ "$(rf .reason)" == *unsafe* ]] && ok "unsafe: reason explains" || bad "unsafe: reason" "$(rf .reason)"
teardown

# --- 4b. denylist matches nested Dockerfile / compose ------------------------
setup
run_entry CHANGED_PATHS="docker/ol-nginx/Dockerfile" E2E_CMD="true"
[[ "$(rf .result)" == failure ]] && ok "unsafe: docker/ path caught" || bad "unsafe: docker path"
teardown
setup
run_entry CHANGED_PATHS="some/dir/compose.yaml" E2E_CMD="true"
[[ "$(rf .result)" == failure ]] && ok "unsafe: nested compose.yaml caught" || bad "unsafe: nested compose"
teardown

# --- 5. safe diff with several files => runs ---------------------------------
setup
run_entry CHANGED_PATHS=$'openlibrary/a.py\nstatic/css/b.css\ntests/c.py' E2E_CMD="true"
[[ "$(rf .result)" == success ]] && ok "safe: multi-file safe diff runs" || bad "safe: multi-file" "$(rf .reason)"
teardown

# --- 6. diff source UNREADABLE => fail CLOSED (no run) -----------------------
setup
SENTINEL="$TESTDIR/e2e-ran"
run_entry CHANGED_PATHS="" CHANGED_PATHS_CMD="exit 3" E2E_CMD="touch '$SENTINEL'"
[[ "$(rf .result)" == failure ]] && ok "diff-unreadable: fails closed" || bad "diff-unreadable: failure"
[[ "$(rf .ran)" == false ]] && ok "diff-unreadable: ran=false" || bad "diff-unreadable: ran=false"
[[ ! -f "$SENTINEL" ]] && ok "diff-unreadable: harness not executed" || bad "diff-unreadable: executed"
teardown

# --- 7. sha-pin mismatch => failure, no run ----------------------------------
setup
SENTINEL="$TESTDIR/e2e-ran"
env PR_NUMBER=4242 HEAD_SHA="$GOODSHA" RESULT_FILE="$TESTDIR/result.json" \
    CHANGED_PATHS="openlibrary/app.py" \
    SHA_VERIFY_CMD="echo 1111111111111111111111111111111111111111" \
    E2E_CMD="touch '$SENTINEL'" \
    bash "$RUN" >"$TESTDIR/out.log" 2>&1; RC=$?
[[ "$(rf .result)" == failure ]] && ok "sha-mismatch: result=failure" || bad "sha-mismatch: failure"
[[ "$(rf .ran)" == false ]] && ok "sha-mismatch: ran=false" || bad "sha-mismatch: ran=false"
[[ ! -f "$SENTINEL" ]] && ok "sha-mismatch: harness not executed" || bad "sha-mismatch: executed"
[[ "$(rf .reason)" == *sha-pin* ]] && ok "sha-mismatch: reason explains" || bad "sha-mismatch: reason" "$(rf .reason)"
teardown

# --- 8. sha-pin match => runs ------------------------------------------------
setup
env PR_NUMBER=4242 HEAD_SHA="$GOODSHA" RESULT_FILE="$TESTDIR/result.json" \
    CHANGED_PATHS="openlibrary/app.py" \
    SHA_VERIFY_CMD="echo $GOODSHA" E2E_CMD="true" \
    bash "$RUN" >"$TESTDIR/out.log" 2>&1
[[ "$(rf .result)" == success ]] && ok "sha-match: runs and succeeds" || bad "sha-match: success" "$(rf .reason)"
teardown

# --- 9. validation: missing PR_NUMBER => die before the trap, no artifact ----
setup
env HEAD_SHA="$GOODSHA" RESULT_FILE="$TESTDIR/result.json" SKIP_SHA_VERIFY=1 \
    CHANGED_PATHS="x" E2E_CMD="true" bash "$RUN" >"$TESTDIR/out.log" 2>&1; RC=$?
[[ $RC -eq 2 ]] && ok "validate: missing PR_NUMBER exits 2" || bad "validate: PR_NUMBER exit" "rc=$RC"
[[ ! -f "$TESTDIR/result.json" ]] && ok "validate: no artifact (POST fail-safes)" || bad "validate: artifact present"
teardown

# --- 10. validation: malformed HEAD_SHA => exit 2 ---------------------------
setup
env PR_NUMBER=4242 HEAD_SHA="deadbeef" RESULT_FILE="$TESTDIR/result.json" SKIP_SHA_VERIFY=1 \
    CHANGED_PATHS="x" E2E_CMD="true" bash "$RUN" >"$TESTDIR/out.log" 2>&1; RC=$?
[[ $RC -eq 2 ]] && ok "validate: bad HEAD_SHA exits 2" || bad "validate: HEAD_SHA exit" "rc=$RC"
teardown

# --- 11. guard: sourcing does not run main ----------------------------------
setup
( set +u; source "$RUN" ) >"$TESTDIR/out.log" 2>&1; RC=$?
[[ $RC -eq 0 ]] && ok "guard: sourceable without running main" || bad "guard: source" "rc=$RC"
[[ ! -f "$TESTDIR/result.json" ]] && ok "guard: sourcing writes no artifact" || bad "guard: artifact on source"
teardown

echo ""
echo "passed: $pass   failed: $fail"
[[ $fail -eq 0 ]]
