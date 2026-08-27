import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from scripts import analyze_merge_conflicts


def test_parse_transcript_returns_merged_and_conflicted_prs():
    transcript = """start
---
origin pull/10/head  # pinned at sha10
Merge made by the 'ort' strategy.
---
origin pull/11/head  # pinned at sha11
Merge conflict for PR #11 (pinned sha11) — skipping
"""

    merged, conflicts = analyze_merge_conflicts.parse_transcript(transcript)

    assert merged == {10: "sha10"}
    assert conflicts == {11}


def test_update_state_writes_conflict_metadata_atomically(tmp_path: Path):
    conflicts_file = tmp_path / "_testing-merge-conflicts.json"

    with patch.object(analyze_merge_conflicts, "CONFLICTS_FILE", conflicts_file):
        analyze_merge_conflicts.update_state(
            {
                11: {"with_prs": [10], "with_master": False, "analysis": "pairwise"},
                12: {"with_prs": [], "with_master": True, "analysis": "master"},
            }
        )

    data = json.loads(conflicts_file.read_text())
    assert data["generated_at"]
    assert data["conflicts"]["11"]["with_prs"] == [10]
    assert data["conflicts"]["12"]["with_master"] is True


def test_run_merge_tree_detects_conflict():
    result = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout="CONFLICT (content): Merge conflict in file.py\n",
        stderr="",
    )
    with patch("scripts.analyze_merge_conflicts.subprocess.run", return_value=result):
        assert analyze_merge_conflicts.run_merge_tree("master", "sha") is True


def test_run_merge_tree_accepts_clean_merge():
    result = subprocess.CompletedProcess(args=[], returncode=0, stdout="clean-tree\n", stderr="")
    with patch("scripts.analyze_merge_conflicts.subprocess.run", return_value=result):
        assert analyze_merge_conflicts.run_merge_tree("master", "sha") is False


def test_analyzer_can_report_multiple_individual_culprits(tmp_path: Path):
    state_file = tmp_path / "_testing-prs.json"
    conflicts_file = tmp_path / "_testing-merge-conflicts.json"
    status_file = tmp_path / "_dev-merged_status.txt"
    state_file.write_text(json.dumps({"prs": [{"pr": 10, "commit": "sha10"}, {"pr": 11, "commit": "sha11"}, {"pr": 12, "commit": "sha12"}]}))
    status_file.write_text(
        """start
---
origin pull/10/head  # pinned at sha10
Merge made by the 'ort' strategy.
---
origin pull/11/head  # pinned at sha11
Merge made by the 'ort' strategy.
---
origin pull/12/head  # pinned at sha12
Merge conflict for PR #12 (pinned sha12) — skipping
"""
    )

    def merge_tree(base, commit):
        return base in {"sha10", "sha11"}

    with (
        patch.object(analyze_merge_conflicts, "STATE_FILE", state_file),
        patch.object(analyze_merge_conflicts, "CONFLICTS_FILE", conflicts_file),
        patch.object(analyze_merge_conflicts, "STATUS_FILE", status_file),
        patch.object(analyze_merge_conflicts, "run_merge_tree", side_effect=merge_tree),
    ):
        analyze_merge_conflicts.main()

    data = json.loads(conflicts_file.read_text())
    assert data["conflicts"]["12"] == {"with_prs": [10, 11], "with_master": False, "analysis": "pairwise"}
