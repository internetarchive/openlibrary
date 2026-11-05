#!/usr/bin/env python3
"""ADA-role check predicates, dispatched by subcommand.

Usage:  python3 pr.py <predicate>

Each predicate re-derives its answer live from GitHub and exits per the oracle
check contract: 0 = satisfied (do not gate), 1 = unmet (force-continue). ANY
error fails open to 0 (see _util.fail_open). The oracle.yml `check:` lines call
these by exit code only.

Predicates:
  pr_exists        an open PR exists for the current branch
  pr_body_nonempty that PR's body has real content
  plan_current     the oracle block's recorded HEAD == live headRefOid (SHA
                   equality — the plan reflects the pushed code)
  status_set       the oracle block carries a status in the vocabulary
  blocked_labeled  the oracle block's status is `blocked`
  blocked_valid    status is `blocked` AND a typed, lead-actionable blocker is
                   written (the one legitimate clear-to-stop escape)
"""

from __future__ import annotations

import sys

from _util import (
    STATUS_VOCAB,
    blocker_is_valid,
    fail_open,
    parse_oracle_block,
    pr_for_branch,
)


def pr_exists() -> bool:
    return pr_for_branch() is not None


def pr_body_nonempty() -> bool:
    pr = pr_for_branch()
    if pr is None:
        return False  # no PR => body is trivially not there => force-continue
    return bool((pr.get("body") or "").strip())


def plan_current() -> bool:
    """SHA equality: the oracle block records the HEAD the plan was written
    against; it is current iff that matches the PR's live headRefOid. Tolerates
    short SHAs by prefix match in either direction."""
    pr = pr_for_branch()
    if pr is None:
        return False
    recorded = parse_oracle_block(pr.get("body") or "").get("head", "").strip().lower()
    live = (pr.get("headRefOid") or "").strip().lower()
    if not recorded or not live:
        return False
    return live.startswith(recorded) or recorded.startswith(live)


def status_set() -> bool:
    pr = pr_for_branch()
    if pr is None:
        return False
    return parse_oracle_block(pr.get("body") or "").get("status", "").strip().lower() in STATUS_VOCAB


def _status_is_blocked() -> bool:
    pr = pr_for_branch()
    if pr is None:
        return False
    return parse_oracle_block(pr.get("body") or "").get("status", "").strip().lower() == "blocked"


def blocked_labeled() -> bool:
    return _status_is_blocked()


def blocked_valid() -> bool:
    pr = pr_for_branch()
    if pr is None:
        return False
    block = parse_oracle_block(pr.get("body") or "")
    if block.get("status", "").strip().lower() != "blocked":
        return False
    return blocker_is_valid(block)


PREDICATES = {
    "pr_exists": pr_exists,
    "pr_body_nonempty": pr_body_nonempty,
    "plan_current": plan_current,
    "status_set": status_set,
    "blocked_labeled": blocked_labeled,
    "blocked_valid": blocked_valid,
}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in PREDICATES:
        # Unknown predicate: fail open rather than wedge.
        sys.exit(0)
    fail_open(PREDICATES[sys.argv[1]])


if __name__ == "__main__":
    main()
