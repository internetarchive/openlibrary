"""Shared helpers for oracle check predicates.

Every predicate here follows ONE rule: **fail open**. A check helper exits 0
("satisfied — do not gate on me") when it cannot prove the item is unmet, and
exits 1 ("unmet — force-continue") only when it positively observes the gap.
Any exception, missing tool, network failure, or unparsable artifact => exit 0.

Why: a Stop hook that can WEDGE a session is strictly worse than one that
under-enforces. See .claude/oracle/README.md.

State is never stored here. Every predicate re-derives its answer live from
GitHub (the artifact) each call. The only GitHub-authoritative anchors we trust:
  - headRefOid        (always populated, server-side, nothing to spoof)
  - PR/issue existence and body text (incl. the oracle body block)
We deliberately do NOT depend on push-time dates: GitHub's Commit.pushedDate is
null in practice and PushEvent is 90d/300-event capped. Plan-currency is anchored
on HEAD SHA equality instead (Oliver's schema call).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

# The status vocabulary. Reuses the existing ada-status State set; `developing`
# is the one addition for actively-coding (Oliver resolution #3). Carried in the
# PR-body oracle block (artifact-native) rather than as a repo label, so the
# prototype does not mint agent-internal labels on the public openlibrary repo.
STATUS_VOCAB = {
    "investigating",
    "developing",
    "ready-for-review",
    "needs-decision",
    "blocked",
    "merged-pending-deploy",
}

# A blocker is only a legitimate escape if it is typed and lead-actionable.
BLOCKER_TYPES = {"decision-needed", "missing-info", "access", "upstream-dependency"}

# Phrases that reduce a "blocker" to "I haven't finished looking yet" — these are
# rejected so `blocked` cannot become a lazy bail (prompt §ADA/blocked-escape).
_LAZY_BLOCKER = re.compile(
    r"\b(still|haven'?t|have not|need(s)? to|not done|keep|continue)\b.*\b"
    r"(look|invsetigat|investigat|check|explor|research|read|understand)",
    re.IGNORECASE,
)
_MIN_BLOCKER_SPECIFICS = 15  # chars of actual detail after the type prefix


def run(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    """Run a command, capturing output. Raises on non-zero so callers inside a
    fail-open wrapper treat tool failure as 'cannot prove unmet' => satisfied."""
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=True)


def gh_json(args: list[str]):
    """`gh ... --json ...` -> parsed JSON. Raises (caught by fail_open) on error."""
    return json.loads(run(["gh", *args]).stdout)


def current_branch() -> str:
    return run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()


def pr_for_branch() -> dict | None:
    """The open PR whose head is the current branch, or None. Draft PRs count."""
    branch = current_branch()
    prs = gh_json(
        [
            "pr",
            "list",
            "--head",
            branch,
            "--state",
            "open",
            "--json",
            "number,body,headRefOid,isDraft",
        ]
    )
    return prs[0] if prs else None


def parse_oracle_block(body: str) -> dict:
    """Extract the structured oracle block from a PR/issue body.

    Format (an HTML comment so it is invisible in rendered Markdown):

        <!-- oracle
        status: developing
        head: <40-char sha the plan was last written against>
        blocker: <type>: <specifics>        # only when status: blocked
        -->

    Returns a dict of the key: value lines (empty dict if absent)."""
    if not body:
        return {}
    m = re.search(r"<!--\s*oracle\b(.*?)-->", body, re.DOTALL | re.IGNORECASE)
    if not m:
        return {}
    fields: dict[str, str] = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, val = line.partition(":")
        fields[key.strip().lower()] = val.strip()
    return fields


def blocker_is_valid(block: dict) -> bool:
    """A blocker escapes the force-continue loop only if it is typed, lead-
    actionable, specific, and not a 'haven't-finished-looking' bail."""
    raw = block.get("blocker", "").strip()
    if not raw:
        return False
    btype, _, specifics = raw.partition(":")
    btype, specifics = btype.strip().lower(), specifics.strip()
    if btype not in BLOCKER_TYPES:
        return False
    if len(specifics) < _MIN_BLOCKER_SPECIFICS:
        return False
    if _LAZY_BLOCKER.search(raw):
        return False
    return True


def satisfied(ok: bool) -> None:
    """Translate a predicate's boolean into the oracle check contract:
    satisfied (ok=True)  -> exit 0 (do not gate)
    unmet     (ok=False) -> exit 1 (force-continue on this item)."""
    sys.exit(0 if ok else 1)


def fail_open(predicate) -> None:
    """Run a predicate() -> bool and exit per satisfied(); ANY exception =>
    exit 0 (satisfied / fail open). This is the single safety net."""
    try:
        satisfied(predicate())
    except SystemExit:
        raise
    except BaseException:
        sys.exit(0)
