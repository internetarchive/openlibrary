#!/usr/bin/env python3
"""LEAD-role check predicates, dispatched by subcommand.

Usage:  python3 now.py <predicate>

The lead owns ONE dedicated per-division GitHub issue titled `[NOW] <division>`.
At the lead's stop we ask only: is my NOW stale relative to the adas beneath it?

  now_exists    the `[NOW] <division>` issue exists
  now_current   NO owned/child issue has `updatedAt` newer than the NOW issue's
                `lastEditedAt` (Oliver resolution #4: children pull on updatedAt
                — intentionally sensitive; the NOW is gated on body lastEditedAt,
                which only the lead AUTHORING a reconciliation moves).

Division comes from $ORACLE_DIVISION (set by the hook from `agents whoami`).
Child issues default to those carrying a label == the division; override with
$ORACLE_CHILD_QUERY (a gh search fragment). All predicates fail open to 0.
"""

from __future__ import annotations

import json
import os
import sys

from _util import fail_open, gh_json, run

# GraphQL search with the search string passed as a *variable*, so nothing is
# interpolated into the query braces (no f-string brace-doubling, no injection).
_SEARCH = "query($q:String!){search(query:$q, type:ISSUE, first:50){nodes{... on Issue {number title lastEditedAt createdAt updatedAt}}}}"


def _search(query: str) -> list[dict]:
    out = run(["gh", "api", "graphql", "-f", f"query={_SEARCH}", "-f", f"q={query}"]).stdout
    return json.loads(out)["data"]["search"]["nodes"]


def _repo() -> str:
    return gh_json(["repo", "view", "--json", "nameWithOwner"])["nameWithOwner"]


def _division() -> str:
    div = os.environ.get("ORACLE_DIVISION", "").strip()
    if not div:
        raise RuntimeError("no ORACLE_DIVISION set")  # fail open: lead un-scoped
    return div


def _now_issue() -> dict | None:
    """The open `[NOW] <division>` issue, with its lastEditedAt/createdAt."""
    div = _division()
    nodes = _search(f'repo:{_repo()} is:issue is:open in:title "[NOW] {div}"')
    want = f"[now] {div.lower()}"  # prefer an exact title match
    for n in nodes:
        if n.get("title", "").strip().lower() == want:
            return n
    return nodes[0] if nodes else None


def _child_updated_times() -> list[str]:
    div = _division()
    frag = os.environ.get("ORACLE_CHILD_QUERY", "").strip() or f'label:"{div}"'
    nodes = _search(f"repo:{_repo()} is:issue {frag}")
    now = _now_issue()
    now_num = now.get("number") if now else None
    return [n["updatedAt"] for n in nodes if n.get("number") != now_num and n.get("updatedAt")]


def now_exists() -> bool:
    return _now_issue() is not None


def now_current() -> bool:
    """True (satisfied) iff no child's updatedAt is newer than the NOW's
    lastEditedAt (falling back to createdAt when the body was never edited)."""
    now = _now_issue()
    if now is None:
        return False
    anchor = now.get("lastEditedAt") or now.get("createdAt")
    if not anchor:
        return True  # cannot prove stale => fail open to satisfied
    children = _child_updated_times()
    if not children:
        return True
    # ISO-8601 Zulu timestamps are lexically ordered, so string compare suffices.
    return max(children) <= anchor


PREDICATES = {"now_exists": now_exists, "now_current": now_current}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in PREDICATES:
        sys.exit(0)
    fail_open(PREDICATES[sys.argv[1]])


if __name__ == "__main__":
    main()
