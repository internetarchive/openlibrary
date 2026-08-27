#!/usr/bin/env python3
"""Best-effort post-deploy analysis of testing-environment merge conflicts."""

from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import tempfile
from pathlib import Path

DEFAULT_STATE_FILE = Path("_testing-prs.json")
DEFAULT_CONFLICTS_FILE = Path("_testing-merge-conflicts.json")
DEFAULT_STATUS_FILE = Path("_dev-merged_status.txt")


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
    """Return successfully merged PR SHAs and conflicted PR numbers."""
    merged: dict[int, str] = {}
    conflicts: set[int] = set()
    for pr, sha, section in transcript_sections(text):
        if "Merge conflict for PR #" in section:
            conflicts.add(pr)
        elif "Merge made by" in section:
            merged[pr] = sha
    return merged, conflicts


def update_state(output_file: Path, conflicts: dict[int, dict[str, object]]) -> None:
    """Atomically replace conflict metadata in its separate state file."""
    data = {
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "conflicts": {str(pr): details for pr, details in conflicts.items()},
    }
    with tempfile.NamedTemporaryFile("w", dir=output_file.parent, delete=False) as tmp:
        json.dump(data, tmp, indent=2)
        tmp.write("\n")
        temporary = Path(tmp.name)
    temporary.replace(output_file)


def main(
    status_file: Path = DEFAULT_STATUS_FILE,
    state_file: Path = DEFAULT_STATE_FILE,
    output_file: Path = DEFAULT_CONFLICTS_FILE,
) -> None:
    """Analyze the latest transcript; any exception is intentionally non-fatal."""
    if not status_file.exists() or not state_file.exists():
        return
    text = status_file.read_text()
    merged, parsed_conflicts = parse_transcript(text)
    sections = {pr: sha for pr, sha, section in transcript_sections(text) if "Merge conflict for PR #" in section}
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
    update_state(output_file, conflicts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--status-file", type=Path, default=DEFAULT_STATUS_FILE)
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_FILE)
    parser.add_argument("--output-file", type=Path, default=DEFAULT_CONFLICTS_FILE)
    args = parser.parse_args()
    main(args.status_file, args.state_file, args.output_file)
