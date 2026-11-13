#!/usr/bin/env bash
#
# test_e2e_post.sh — unit tests for scripts/e2e/e2e-post.sh, the security-critical
# POST decision core. No real GitHub; the module only reads a local artifact file
# and emits a decision JSON, so these tests are hermetic.
#
# Covers wally's prove-the-test-fails requirement (b): a missing OR malformed
# artifact fail-safes to a terminal `failure` decision — plus the full validation
# matrix (sha mismatch, bad pr, unknown result value, comment sanitisation).

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

# jq-field assertion: run POST, capture stdout decision, compare one field.
# Usage: field <decision-json> <jq-path>
field() { printf '%s' "$1" | jq -r "$2"; }

setup() { TESTDIR="$(mktemp -d)"; }
teardown() { [[ -n "$TESTDIR" && -d "$TESTDIR" ]] && rm -rf "$TESTDIR"; }

# Write an artifact file and run the module against it. Echoes the decision JSON.
run_post() {
  local artifact_file="$1"; shift
  env ARTIFACT_FILE="$artifact_file" WORKFLOW_RUN_HEAD_SHA="${HEAD_OVERRIDE:-$GOODSHA}" \
      "$@" bash "$POST" 2>/dev/null
}

write_artifact() {
  # $1 file, $2 result, $3 pr, $4 head, $5 reason
  printf '{"schema":"ol-e2e-result/1","pr":%s,"head_sha":"%s","result":"%s","reason":"%s","ran":true}\n' \
    "$3" "$4" "$2" "$5" > "$1"
}

echo "test_e2e_post.sh"

# --- 1. clean success artifact => success, clear label, no comment -----------
setup
write_artifact "$TESTDIR/r.json" success 4242 "$GOODSHA" "e2e passed (@smoke)"
d="$(run_post "$TESTDIR/r.json")"; rc=$?
[[ $rc -eq 0 ]] && ok "success: exits 0" || bad "success: exits 0" "rc=$rc"
[[ "$(field "$d" .state)" == success ]] && ok "success: state=success" || bad "success: state=success" "$d"
[[ "$(field "$d" .pr)" == 4242 ]] && ok "success: pr carried" || bad "success: pr carried" "$d"
[[ "$(field "$d" .head_sha)" == "$GOODSHA" ]] && ok "success: posts on authoritative sha" || bad "success: sha" "$d"
[[ "$(field "$d" .remove_label)" == true ]] && ok "success: clears label" || bad "success: clears label" "$d"
[[ "$(field "$d" .comment)" == false ]] && ok "success: no comment" || bad "success: no comment" "$d"
[[ "$(field "$d" .status_context)" == "check/tested-e2e" ]] && ok "success: default context" || bad "success: default context" "$d"
teardown

# --- 2. clean failure artifact => failure, clear label, comment --------------
setup
write_artifact "$TESTDIR/r.json" failure 4242 "$GOODSHA" "e2e failed (@smoke)"
d="$(run_post "$TESTDIR/r.json")"
[[ "$(field "$d" .state)" == failure ]] && ok "failure: state=failure" || bad "failure: state=failure" "$d"
[[ "$(field "$d" .remove_label)" == true ]] && ok "failure: clears label" || bad "failure: clears label" "$d"
[[ "$(field "$d" .comment)" == true ]] && ok "failure: comments" || bad "failure: comments" "$d"
[[ -n "$(field "$d" .comment_body)" ]] && ok "failure: comment body present" || bad "failure: comment body" "$d"
teardown

# --- 3. (b) MISSING artifact => fail-safe to failure, no label/comment -------
setup
d="$(run_post "$TESTDIR/does-not-exist.json")"; rc=$?
[[ $rc -eq 0 ]] && ok "missing: exits 0 (decision emitted)" || bad "missing: exits 0" "rc=$rc"
[[ "$(field "$d" .state)" == failure ]] && ok "missing: fail-safes to failure" || bad "missing: failure" "$d"
[[ "$(field "$d" .pr)" == null ]] && ok "missing: pr null (no label/comment target)" || bad "missing: pr null" "$d"
[[ "$(field "$d" .remove_label)" == false ]] && ok "missing: does not clear label" || bad "missing: remove_label" "$d"
[[ "$(field "$d" .head_sha)" == "$GOODSHA" ]] && ok "missing: still posts status on event sha" || bad "missing: sha" "$d"
teardown

# --- 4. (b) MALFORMED JSON => fail-safe to failure ---------------------------
setup
printf 'this is { not json' > "$TESTDIR/r.json"
d="$(run_post "$TESTDIR/r.json")"
[[ "$(field "$d" .state)" == failure ]] && ok "malformed: fail-safes to failure" || bad "malformed: failure" "$d"
[[ "$(field "$d" .head_sha)" == "$GOODSHA" ]] && ok "malformed: posts on event sha" || bad "malformed: sha" "$d"
teardown

# --- 5. UNKNOWN result value => fail-safe to failure -------------------------
setup
write_artifact "$TESTDIR/r.json" pending 4242 "$GOODSHA" "weird"
d="$(run_post "$TESTDIR/r.json")"
[[ "$(field "$d" .state)" == failure ]] && ok "unknown-result: fail-safes to failure" || bad "unknown-result" "$d"
teardown

# --- 6. sha MISMATCH => failure, distrust pr (null) --------------------------
setup
write_artifact "$TESTDIR/r.json" success 4242 "0000000000000000000000000000000000000000" "e2e passed"
d="$(run_post "$TESTDIR/r.json")"
[[ "$(field "$d" .state)" == failure ]] && ok "sha-mismatch: forces failure" || bad "sha-mismatch: failure" "$d"
[[ "$(field "$d" .pr)" == null ]] && ok "sha-mismatch: distrusts pr" || bad "sha-mismatch: pr null" "$d"
[[ "$(field "$d" .head_sha)" == "$GOODSHA" ]] && ok "sha-mismatch: posts on authoritative sha" || bad "sha-mismatch: sha" "$d"
teardown

# --- 7. non-integer pr => post status, skip label/comment -------------------
setup
printf '{"pr":"not-a-number","head_sha":"%s","result":"success","reason":"x","ran":true}\n' "$GOODSHA" > "$TESTDIR/r.json"
d="$(run_post "$TESTDIR/r.json")"
[[ "$(field "$d" .state)" == success ]] && ok "bad-pr: keeps real result" || bad "bad-pr: state" "$d"
[[ "$(field "$d" .pr)" == null ]] && ok "bad-pr: pr null" || bad "bad-pr: pr null" "$d"
[[ "$(field "$d" .remove_label)" == false ]] && ok "bad-pr: skips label clear" || bad "bad-pr: remove_label" "$d"
teardown

# --- 8. comment sanitisation: attacker path can't inject md/html ------------
setup
write_artifact "$TESTDIR/r.json" failure 4242 "$GOODSHA" \
  "unsafe to auto-run: changes <img src=x onerror=alert(1)> \`backtick\` path"
d="$(run_post "$TESTDIR/r.json")"
body="$(field "$d" .comment_body)"
[[ "$body" != *'<img'* ]] && ok "sanitise: strips angle brackets" || bad "sanitise: angle brackets" "$body"
[[ "$body" != *'`backtick`'* ]] && ok "sanitise: neutralises backticks" || bad "sanitise: backticks" "$body"
teardown

# --- 9. CHECK_PREFIX is swappable -------------------------------------------
setup
write_artifact "$TESTDIR/r.json" success 4242 "$GOODSHA" "ok"
d="$(run_post "$TESTDIR/r.json" CHECK_PREFIX="pr/")"
[[ "$(field "$d" .status_context)" == "pr/tested-e2e" ]] && ok "prefix: CHECK_PREFIX swaps context" || bad "prefix: swap" "$d"
teardown

# --- 10. malformed authoritative sha => module refuses (non-zero) -----------
setup
write_artifact "$TESTDIR/r.json" success 4242 "$GOODSHA" "ok"
d="$(HEAD_OVERRIDE="not-a-sha" run_post "$TESTDIR/r.json")"; rc=$?
[[ $rc -ne 0 ]] && ok "bad-event-sha: non-zero exit (wrapper fail-safes)" || bad "bad-event-sha: non-zero" "rc=$rc"
teardown

echo ""
echo "passed: $pass   failed: $fail"
[[ $fail -eq 0 ]]
