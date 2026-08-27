#!/usr/bin/env python3
"""Best-effort post-deploy analysis of testing-environment merge conflicts."""

from __future__ import annotations

import datetime
import json
import re
import subprocess
import tempfile
from pathlib import Path

STATE_FILE = Path("_testing-prs.json")
CONFLICTS_FILE = Path("_testing-merge-conflicts.json")
STATUS_FILE = Path("_dev-merged_status.txt")


def run_merge_tree(base: str, commit: str) -> bool:
    """Return whether merging commit into base has a conflict."""
    try:
        result = subprocess.run(
            ["git", "merge-tree", "--write-tree", base, commit],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return bool(re.search(r"^CONFLICT", result.stdout, re.MULTILINE))


def transcript_sections(text: str) -> list[tuple[int, str, str]]:
    """Return PR number, pinned SHA, and transcript section for each PR."""
    matches = list(re.finditer(r"^origin pull/(\d+)/head\s+# pinned at\s+(\S+)", text, re.MULTILINE))
    return [
        (int(match.group(1)), match.group(2), text[match.start() : matches[i + 1].start() if i + 1 < len(matches) else len(text)])
        for i, match in enumerate(matches)
    ]


def parse_transcript(text: str) -> tuple[dict[int, str], set[int]]:
    """Return successful PR SHAs and conflicted PR numbers from a transcript."""
    merged: dict[int, str] = {}
    conflicts: set[int] = set()
    for pr, sha, section in transcript_sections(text):
        if "Merge conflict for PR #" in section:
            conflicts.add(pr)
        elif "Merge made by" in section:
            merged[pr] = sha
    return merged, conflicts


def update_state(conflicts: dict[int, dict[str, object]]) -> None:
    """Atomically replace conflict metadata in its separate state file."""
    data = {
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "conflicts": {str(pr): details for pr, details in conflicts.items()},
    }
    with tempfile.NamedTemporaryFile("w", dir=CONFLICTS_FILE.parent, delete=False) as tmp:
        json.dump(data, tmp, indent=2)
        tmp.write("\n")
        temporary = Path(tmp.name)
    temporary.replace(CONFLICTS_FILE)


def main() -> None:
    """Analyze the latest transcript; any exception is intentionally non-fatal."""
    if not STATUS_FILE.exists() or not STATE_FILE.exists():
        return
    text = STATUS_FILE.read_text()
    merged, parsed_conflicts = parse_transcript(text)
    sections = {pr: sha for pr, sha, section in transcript_sections(text) for sha in [sha] if "Merge conflict for PR #" in section}
    conflicts: dict[int, dict[str, object]] = {}
    for pr in parsed_conflicts:
        sha = sections.get(pr)
        if not sha:
            continue
        if run_merge_tree("master", sha):
            conflicts[pr] = {"with_prs": [], "with_master": True, "analysis": "master"}
            continue
        culprits: list[int] = [prev for prev, prev_sha in merged.items() if run_merge_tree(prev_sha, sha)]
        conflicts[pr] = {"with_prs": culprits, "with_master": False, "analysis": "pairwise" if culprits else "combined"}
    update_state(conflicts)


if __name__ == "__main__":
    main()
