#!/usr/bin/env bash
#
# test_e2e_post.sh — unit tests for scripts/e2e/e2e-post.sh, the security-critical
# POST decision core. No real GitHub; the module only reads a local artifact file
# plus a TRUSTED EVENT_PR, and emits a decision JSON, so these tests are hermetic.
#
# Covers:
#   * the cross-PR write break fix (HIGH): the label/comment target is the trusted
#     EVENT_PR, NEVER the artifact's own `pr` — a malicious artifact pr is ignored.
#   * prove-the-test-fails (b): missing OR malformed artifact => failure decision.
#   * the full validation matrix (sha mismatch, unknown result, sanitisation).
#
# SC2015: `[[ cond ]] && ok || bad` is intentional — ok/bad always return 0, so
# the `bad` branch never runs when the condition holds. SC2016: a single-quoted
# glob pattern is matched literally on purpose.
# shellcheck disable=SC2015,SC2016
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POST="$HERE/e2e-post.sh"
GOODSHA="abcdef0123456789abcdef0123456789abcdef01"
TESTDIR=""

pass=0; fail=0
ok()   { printf '  ok   %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  FAIL %s\n     %s\n' "$1" "${2:-}"; fail=$((fail+1)); }

field() { printf '%s' "$1" | jq -r "$2"; }

setup() { TESTDIR="$(mktemp -d)"; }
teardown() { [[ -n "$TESTDIR" && -d "$TESTDIR" ]] && rm -rf "$TESTDIR"; }

# Run the module. EVENT_PR defaults to 4242 (trusted); override with
# EVENT_PR_OVERRIDE (set to "" to simulate no resolvable PR). WORKFLOW_RUN_HEAD_SHA
# defaults to GOODSHA; override with HEAD_OVERRIDE.
run_post() {
  local artifact_file="$1"; shift
  env ARTIFACT_FILE="$artifact_file" \
      WORKFLOW_RUN_HEAD_SHA="${HEAD_OVERRIDE:-$GOODSHA}" \
      EVENT_PR="${EVENT_PR_OVERRIDE-4242}" \
      "$@" bash "$POST" 2>/dev/null
}

# $1 file, $2 result, $3 pr (attacker-controlled!), $4 head, $5 reason
write_artifact() {
  printf '{"schema":"ol-e2e-result/1","pr":%s,"head_sha":"%s","result":"%s","reason":"%s","ran":true}\n' \
    "$3" "$4" "$2" "$5" > "$1"
}

echo "test_e2e_post.sh"

# --- 1. clean success => success, clear label (trusted pr), no comment --------
setup
write_artifact "$TESTDIR/r.json" success 4242 "$GOODSHA" "e2e passed (@smoke)"
d="$(run_post "$TESTDIR/r.json")"; rc=$?
[[ $rc -eq 0 ]] && ok "success: exits 0" || bad "success: exits 0" "rc=$rc"
[[ "$(field "$d" .state)" == success ]] && ok "success: state=success" || bad "success: state" "$d"
[[ "$(field "$d" .pr)" == 4242 ]] && ok "success: targets EVENT_PR" || bad "success: pr" "$d"
[[ "$(field "$d" .head_sha)" == "$GOODSHA" ]] && ok "success: posts on authoritative sha" || bad "success: sha" "$d"
[[ "$(field "$d" .remove_label)" == true ]] && ok "success: clears label" || bad "success: remove_label" "$d"
[[ "$(field "$d" .comment)" == false ]] && ok "success: no comment" || bad "success: comment" "$d"
[[ "$(field "$d" .status_context)" == "tested-e2e" ]] && ok "success: default context (unprefixed)" || bad "success: ctx" "$d"
teardown

# --- 2. clean failure => failure, clear label, comment -----------------------
setup
write_artifact "$TESTDIR/r.json" failure 4242 "$GOODSHA" "e2e failed (@smoke)"
d="$(run_post "$TESTDIR/r.json")"
[[ "$(field "$d" .state)" == failure ]] && ok "failure: state=failure" || bad "failure: state" "$d"
[[ "$(field "$d" .remove_label)" == true ]] && ok "failure: clears label" || bad "failure: remove_label" "$d"
[[ "$(field "$d" .comment)" == true ]] && ok "failure: comments" || bad "failure: comment" "$d"
[[ -n "$(field "$d" .comment_body)" ]] && ok "failure: comment body present" || bad "failure: body" "$d"
teardown

# --- 3. (HIGH FIX) malicious artifact pr is IGNORED; EVENT_PR is the target ---
setup
write_artifact "$TESTDIR/r.json" failure 9999 "$GOODSHA" "pwn"
d="$(EVENT_PR_OVERRIDE=4242 run_post "$TESTDIR/r.json")"
[[ "$(field "$d" .pr)" == 4242 ]] && ok "cross-pr: uses EVENT_PR not artifact pr" || bad "cross-pr: pr" "$d"
[[ "$(field "$d" .pr)" != 9999 ]] && ok "cross-pr: artifact's 9999 never used as target" || bad "cross-pr: leaked artifact pr" "$d"
teardown

# --- 4. EVENT_PR empty => pr null, NO label/comment even if artifact has pr ---
setup
write_artifact "$TESTDIR/r.json" success 4242 "$GOODSHA" "ok"
d="$(EVENT_PR_OVERRIDE="" run_post "$TESTDIR/r.json")"
[[ "$(field "$d" .pr)" == null ]] && ok "no-event-pr: pr null" || bad "no-event-pr: pr" "$d"
[[ "$(field "$d" .remove_label)" == false ]] && ok "no-event-pr: no label clear" || bad "no-event-pr: remove_label" "$d"
[[ "$(field "$d" .comment)" == false ]] && ok "no-event-pr: no comment" || bad "no-event-pr: comment" "$d"
[[ "$(field "$d" .state)" == success ]] && ok "no-event-pr: status still decided" || bad "no-event-pr: state" "$d"
teardown

# --- 5. (b) MISSING artifact + EVENT_PR => fail-safe failure, clears real PR --
setup
d="$(run_post "$TESTDIR/does-not-exist.json")"; rc=$?
[[ $rc -eq 0 ]] && ok "missing: exits 0 (decision emitted)" || bad "missing: exits 0" "rc=$rc"
[[ "$(field "$d" .state)" == failure ]] && ok "missing: fail-safes to failure" || bad "missing: state" "$d"
[[ "$(field "$d" .pr)" == 4242 ]] && ok "missing: still targets trusted EVENT_PR" || bad "missing: pr" "$d"
[[ "$(field "$d" .head_sha)" == "$GOODSHA" ]] && ok "missing: status on event sha" || bad "missing: sha" "$d"
teardown

# --- 6. (b) MISSING artifact + no EVENT_PR => failure, status only -----------
setup
d="$(EVENT_PR_OVERRIDE="" run_post "$TESTDIR/does-not-exist.json")"
[[ "$(field "$d" .state)" == failure ]] && ok "missing/no-pr: failure" || bad "missing/no-pr: state" "$d"
[[ "$(field "$d" .pr)" == null ]] && ok "missing/no-pr: pr null" || bad "missing/no-pr: pr" "$d"
[[ "$(field "$d" .remove_label)" == false ]] && ok "missing/no-pr: no writes" || bad "missing/no-pr: remove_label" "$d"
teardown

# --- 7. (b) MALFORMED JSON => fail-safe failure ------------------------------
setup
printf 'this is { not json' > "$TESTDIR/r.json"
d="$(run_post "$TESTDIR/r.json")"
[[ "$(field "$d" .state)" == failure ]] && ok "malformed: fail-safes to failure" || bad "malformed: state" "$d"
[[ "$(field "$d" .head_sha)" == "$GOODSHA" ]] && ok "malformed: status on event sha" || bad "malformed: sha" "$d"
teardown

# --- 8. UNKNOWN result value => fail-safe failure ----------------------------
setup
write_artifact "$TESTDIR/r.json" pending 4242 "$GOODSHA" "weird"
d="$(run_post "$TESTDIR/r.json")"
[[ "$(field "$d" .state)" == failure ]] && ok "unknown-result: fail-safes to failure" || bad "unknown-result: state" "$d"
teardown

# --- 9. sha MISMATCH => failure; status on authoritative sha; still clears PR -
setup
write_artifact "$TESTDIR/r.json" success 4242 "0000000000000000000000000000000000000000" "e2e passed"
d="$(run_post "$TESTDIR/r.json")"
[[ "$(field "$d" .state)" == failure ]] && ok "sha-mismatch: forces failure" || bad "sha-mismatch: state" "$d"
[[ "$(field "$d" .head_sha)" == "$GOODSHA" ]] && ok "sha-mismatch: posts on authoritative sha" || bad "sha-mismatch: sha" "$d"
[[ "$(field "$d" .pr)" == 4242 ]] && ok "sha-mismatch: still targets trusted EVENT_PR" || bad "sha-mismatch: pr" "$d"
teardown

# --- 10. comment sanitisation: attacker reason can't inject md/html ----------
setup
write_artifact "$TESTDIR/r.json" failure 4242 "$GOODSHA" \
  "unsafe to auto-run: changes <img src=x onerror=alert(1)> \`backtick\` path"
d="$(run_post "$TESTDIR/r.json")"
body="$(field "$d" .comment_body)"
[[ "$body" != *'<img'* ]] && ok "sanitise: strips angle brackets" || bad "sanitise: angle brackets" "$body"
[[ "$body" != *'`backtick`'* ]] && ok "sanitise: neutralises backticks" || bad "sanitise: backticks" "$body"
teardown

# --- 11. CHECK_PREFIX is swappable ------------------------------------------
setup
write_artifact "$TESTDIR/r.json" success 4242 "$GOODSHA" "ok"
d="$(run_post "$TESTDIR/r.json" CHECK_PREFIX="pr/")"
[[ "$(field "$d" .status_context)" == "pr/tested-e2e" ]] && ok "prefix: CHECK_PREFIX swaps context" || bad "prefix: swap" "$d"
teardown

# --- 12. malformed authoritative sha => module refuses (wrapper fail-safes) --
setup
write_artifact "$TESTDIR/r.json" success 4242 "$GOODSHA" "ok"
d="$(HEAD_OVERRIDE="not-a-sha" run_post "$TESTDIR/r.json")"; rc=$?
[[ $rc -ne 0 ]] && ok "bad-event-sha: non-zero exit" || bad "bad-event-sha: non-zero" "rc=$rc"
teardown

echo ""
echo "passed: $pass   failed: $fail"
[[ $fail -eq 0 ]]
