#!/usr/bin/env bash
#
# e2e-post.sh — the decision core of the POST half of the e2e GitHub Action.
#
# ============================================================================
# This runs in the TRUSTED base-repo context (see e2e_post.yml). It reads the
# RUN job's result artifact as PURE DATA — it NEVER executes it and the POST
# job NEVER checks out fork code. This module is the security-critical part:
# it validates the untrusted artifact and decides exactly what POST may write.
# The workflow's github-script step is only a thin GitHub-API wrapper around the
# decision this emits, so the validation stays unit-tested (test_e2e_post.sh).
#
# FAIL-SAFE: any problem with the artifact (missing, malformed, wrong shape,
# sha mismatch, unknown result value) resolves to a terminal `failure` status.
# A stuck/absent e2e state is therefore structurally impossible: RUN always
# emits an artifact, the workflow uploads it with if:always(), and here anything
# short of a clean `success` artifact becomes `failure`.
#
# Inputs (env):
#   ARTIFACT_FILE          (required) path to the downloaded e2e-result.json
#   WORKFLOW_RUN_HEAD_SHA  (required) the AUTHORITATIVE head sha, taken from the
#                          workflow_run event — NOT from the artifact. The commit
#                          status is always posted on this sha; the artifact's
#                          own head_sha is only cross-checked against it.
#   CHECK_PREFIX           default "check/" — the single swappable status-context
#                          prefix (the `check/` vs `pr/` choice is still open).
#   STATUS_CONTEXT         default "${CHECK_PREFIX}tested-e2e"
#   LABEL                  default "Needs: e2e testing"
#
# Output: a single-line decision JSON on stdout, consumed by the github-script
# API wrapper:
#   {"state","head_sha","pr","status_context","description",
#    "remove_label","label","comment","comment_body"}
# `pr` is null when the artifact did not yield a trustworthy PR number; the
# wrapper then posts the status but skips the label-clear and comment.
#
# Exit code: 0 whenever a decision was emitted (including every fail-safe to
# failure). Non-zero ONLY if it could not emit a decision at all (e.g. jq
# missing) — the wrapper must fail-safe to failure on a non-zero exit.
# ----------------------------------------------------------------------------

set -uo pipefail

err() { printf '[e2e-post] %s\n' "$*" >&2; }

command -v jq >/dev/null 2>&1 || { err "jq is required"; exit 2; }

ARTIFACT_FILE="${ARTIFACT_FILE:-}"
WORKFLOW_RUN_HEAD_SHA="${WORKFLOW_RUN_HEAD_SHA:-}"
CHECK_PREFIX="${CHECK_PREFIX:-check/}"
STATUS_CONTEXT="${STATUS_CONTEXT:-${CHECK_PREFIX}tested-e2e}"
LABEL="${LABEL:-Needs: e2e testing}"

[[ -n "$WORKFLOW_RUN_HEAD_SHA" ]] || { err "WORKFLOW_RUN_HEAD_SHA is required"; exit 2; }
# The authoritative sha must itself be well-formed, or we have nothing safe to
# post a status on.
[[ "$WORKFLOW_RUN_HEAD_SHA" =~ ^[0-9a-f]{40}$ ]] || { err "WORKFLOW_RUN_HEAD_SHA is not a 40-hex sha"; exit 2; }

# Neutralise an attacker-influenced string before it goes into a PR comment: the
# RUN artifact is untrusted data, and its `reason` can embed a PR-chosen path
# (the denylist message). Collapse whitespace, strip backticks/angle brackets so
# it can't break out of the code span it is rendered in, and cap the length.
sanitize() {
  local s="$1"
  s="${s//\`/\'}"              # backticks -> apostrophes (no code-span escape)
  s="${s//</(}"; s="${s//>/)}" # angle brackets -> parens (no raw HTML)
  s="$(printf '%s' "$s" | tr '\n\r\t' '   ')"
  s="$(printf '%s' "$s" | tr -s ' ')"
  if (( ${#s} > 500 )); then s="${s:0:497}..."; fi
  printf '%s' "$s"
}

# Truncate a commit-status description to GitHub's 140-char limit.
clip_desc() { local s="$1"; if (( ${#s} > 140 )); then printf '%s' "${s:0:137}..."; else printf '%s' "$s"; fi; }

emit() {
  # $1 state, $2 pr (integer or empty => null), $3 description, $4 comment_body ("" => no comment)
  local state="$1" pr="$2" desc comment_body="$4"
  desc="$(clip_desc "$3")"
  local do_comment="false" do_label="false" pr_json="null"
  if [[ "$pr" =~ ^[0-9]+$ ]]; then
    pr_json="$pr"
    do_label="true"                                   # resolved run => clear the label
    [[ "$state" == "failure" && -n "$comment_body" ]] && do_comment="true"
  fi
  jq -cn \
    --arg state "$state" \
    --argjson pr "$pr_json" \
    --arg head "$WORKFLOW_RUN_HEAD_SHA" \
    --arg ctx "$STATUS_CONTEXT" \
    --arg desc "$desc" \
    --arg label "$LABEL" \
    --argjson rl "$do_label" \
    --argjson cm "$do_comment" \
    --arg body "$comment_body" \
    '{state:$state, head_sha:$head, pr:$pr, status_context:$ctx, description:$desc,
      remove_label:$rl, label:$label, comment:$cm, comment_body:$body}'
}

# --- read + validate the artifact (fail-safe to failure on any problem) -------
if [[ -z "$ARTIFACT_FILE" || ! -f "$ARTIFACT_FILE" ]]; then
  emit "failure" "" "e2e did not produce a result (no artifact)" \
    "e2e (@smoke) could not be reported: the RUN job produced no result artifact — it likely crashed or timed out before writing one. A maintainer can re-run e2e by re-applying the label."
  exit 0
fi

artifact="$(cat "$ARTIFACT_FILE" 2>/dev/null)"
if ! a_json="$(printf '%s' "$artifact" | jq -ce . 2>/dev/null)"; then
  emit "failure" "" "e2e result artifact was malformed" \
    "e2e (@smoke) could not be reported: the result artifact was not valid JSON. Re-run e2e by re-applying the label."
  exit 0
fi

a_result="$(printf '%s' "$a_json" | jq -r '.result // empty' 2>/dev/null)"
a_pr="$(printf '%s' "$a_json" | jq -r '.pr // empty' 2>/dev/null)"
a_head="$(printf '%s' "$a_json" | jq -r '.head_sha // empty' 2>/dev/null)"
a_reason="$(printf '%s' "$a_json" | jq -r '.reason // empty' 2>/dev/null)"

# The artifact's sha must be well-formed AND equal the authoritative event sha.
# A mismatch means the artifact does not describe this run — don't trust its PR
# number for label/comment; still post a failure status on the authoritative sha.
if [[ ! "$a_head" =~ ^[0-9a-f]{40}$ || "$a_head" != "$WORKFLOW_RUN_HEAD_SHA" ]]; then
  emit "failure" "" "e2e result did not match this commit" \
    "e2e (@smoke) could not be reported: the result artifact's head sha did not match this run. Re-run e2e by re-applying the label."
  exit 0
fi

# The PR number must be a positive integer to be used for label/comment; if not,
# still post the status, just without label/comment (pr=null).
pr_for_writes=""
[[ "$a_pr" =~ ^[0-9]+$ ]] && pr_for_writes="$a_pr"

case "$a_result" in
  success)
    emit "success" "$pr_for_writes" "e2e @smoke passed" ""
    ;;
  failure)
    reason="$(sanitize "${a_reason:-e2e failed}")"
    emit "failure" "$pr_for_writes" "e2e @smoke failed" \
      "❌ **e2e (@smoke) failed.** Reason: \`${reason}\`. See the e2e workflow run for logs and the Playwright report. Push a fix (or a maintainer can re-apply the \`${LABEL}\` label) to re-run."
    ;;
  *)
    # Unknown / absent result value — fail-safe.
    emit "failure" "$pr_for_writes" "e2e result was not recognised" \
      "e2e (@smoke) could not be reported: the result value was not recognised. Re-run e2e by re-applying the label."
    ;;
esac
exit 0
