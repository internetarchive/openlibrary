"""Tests for the testing-environment status API and its underlying helper."""

import asyncio
import datetime
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import web

import openlibrary.plugins.openlibrary.jenkins as jenkins_module
import openlibrary.plugins.openlibrary.status as status_module


@pytest.fixture
def mock_maintainer_user(monkeypatch):
    """Patch get_current_user (used by require_maintainer) with a user of configurable role."""

    def create_user(is_maintainer: bool = False):
        user = MagicMock()
        user.is_maintainer.return_value = is_maintainer
        monkeypatch.setattr("openlibrary.fastapi.auth.get_current_user", lambda: user)
        return user

    return create_user


def _make_pr(pr_number=13269, active=True, added_at="2026-08-06T15:00:00+00:00"):
    return status_module.TestingPR(
        pr=pr_number,
        commit="1d23364b8c652d6107e2dc685f918551fda5d327",
        active=active,
        title="Test PR",
        added_at=added_at,
        added_by="openlibrary",
        author="author",
        assignee="assignee",
    )


def _make_state(prs=None, last_deploy_at="2026-08-05T18:00:00+00:00"):
    return status_module.TestingState(last_deploy_at=last_deploy_at, prs=prs or [_make_pr()])


def test_build_testing_status_merges_drift_and_derived_fields():
    state = _make_state()
    drift_info = {state.prs[0].pr: {"head_sha": "abc1234", "drift": 2, "merged": False}}

    result = status_module.build_testing_status(state, drift_info)

    assert result.last_deploy_at == "2026-08-05T18:00:00+00:00"
    assert result.has_pending is True  # added after last deploy
    assert result.deploying is False  # never triggered a build
    assert result.pending_changes == [status_module.PendingChange(pr=13269, title="Test PR", kind="add", detail="1d23364", reason="")]
    pr = result.prs[0]
    assert (pr.head_sha, pr.drift, pr.merged, pr.is_new) == ("abc1234", 2, False, True)
    assert (pr.title, pr.added_by) == ("Test PR", "openlibrary")
    assert (pr.live_now, pr.action, pr.in_set) == (False, "add", True)


def test_build_testing_status_missing_drift_uses_unknown_defaults():
    state = _make_state(prs=[_make_pr(pr_number=13238, added_at="2026-08-01T00:00:00+00:00")])

    result = status_module.build_testing_status(state, {})

    pr = result.prs[0]
    assert (pr.head_sha, pr.drift, pr.merged, pr.is_new) == ("", -1, False, False)
    assert result.has_pending is False


@pytest.mark.parametrize(
    ("pr_kwargs", "drift", "last_deploy_at", "expected"),
    [
        ({}, {}, "2026-08-05T18:00:00+00:00", True),  # added since last deploy
        ({"added_at": "2026-08-01T00:00:00+00:00"}, {}, "2026-08-05T18:00:00+00:00", False),
        ({"added_at": "2026-08-01T00:00:00+00:00"}, {}, "", True),  # never deployed
        ({"added_at": "2026-08-01T00:00:00+00:00"}, {"merged": True}, "2026-08-05T18:00:00+00:00", True),
    ],
)
def test_build_testing_status_has_pending(pr_kwargs, drift, last_deploy_at, expected):
    pr = _make_pr(**pr_kwargs)
    result = status_module.build_testing_status(_make_state(prs=[pr], last_deploy_at=last_deploy_at), {pr.pr: drift})
    assert result.has_pending is expected


@pytest.mark.asyncio
async def test_get_drift_info_fetches_prs_concurrently():
    """Per-PR GitHub fetches overlap (gather), not one-after-another."""
    state = _make_state(prs=[_make_pr(pr_number=n) for n in (13269, 13238, 13240)])
    info = {
        "head_sha": "abc1234",
        "drift": 0,
        "merged": False,
        "closed": False,
        "title": "Test PR",
        "author": "author",
        "author_avatar": "",
        "assignee": "assignee",
        "assignee_avatar": "",
    }
    active = 0
    peak = 0

    async def fake_drift(_pr):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)  # yield so siblings can start
        active -= 1
        return info

    mc = MagicMock()
    mc.get.return_value = None
    with (
        patch("openlibrary.plugins.openlibrary.status.cache.get_memcache", return_value=mc),
        patch("openlibrary.plugins.openlibrary.status._get_pr_drift_async", side_effect=fake_drift),
    ):
        drift, from_cache = await status_module._get_drift_info_async(state, persist=False)

    assert from_cache is False
    assert peak > 1  # sequential awaits would never see overlap
    assert drift == {p.pr: {"head_sha": "abc1234", "drift": 0, "merged": False, "closed": False} for p in state.prs}


def test_build_testing_status_marks_merge_conflicts():
    """Rows whose merge failed on the last deploy carry the merge_conflict flag."""
    state = _make_state(prs=[_make_pr(pr_number=13269), _make_pr(pr_number=13238, added_at="2026-08-01T00:00:00+00:00")])
    result = status_module.build_testing_status(state, {}, merge_conflicts=frozenset({13269}))

    by_pr = {pr.pr: pr for pr in result.prs}
    assert by_pr[13269].merge_conflict is True
    assert by_pr[13238].merge_conflict is False


def test_merge_conflicted_prs_reads_deploy_status_file():
    """Both the deploy script's summary and git's message mark a PR conflicted."""
    dms = status_module.DevMergedStatus(
        git_status="x",
        pr_statuses=[
            status_module.PRStatus(pull_line="origin pull/13208/head  # A", status="Already up to date.", body=""),
            # The real deploy-script summary (scripts/make-integration-branch.sh).
            status_module.PRStatus(
                pull_line="origin pull/13370/head  # B",
                status="Merge conflict for PR #13370 (pinned 0e710e2b7cd80fa8dcb05d1ccb941ab9d83e23a5) — skipping",
                body="",
            ),
            # git's own merge output, when the transcript captures it.
            status_module.PRStatus(
                pull_line="origin pull/12914/head  # C",
                status="Automatic merge failed; fix conflicts and then commit the result.",
                body="",
            ),
            status_module.PRStatus(pull_line="origin pull/13220/head  # D", status="Merge made by the 'ort' strategy.", body=""),
        ],
        footer="",
    )
    with patch("openlibrary.plugins.openlibrary.status.get_dev_merged_status", return_value=dms):
        assert status_module._merge_conflicted_prs() == frozenset({13370, 12914})

    with patch("openlibrary.plugins.openlibrary.status.get_dev_merged_status", return_value=None):
        assert status_module._merge_conflicted_prs() == frozenset()


def test_merge_conflicted_prs_falls_back_to_pr_number_in_message():
    """A summary line with no parseable pull_line still names its PR."""
    dms = status_module.DevMergedStatus(
        git_status="x",
        pr_statuses=[
            status_module.PRStatus(
                pull_line="Some branch title",
                status="Merge conflict for PR #13370 (pinned 0e710e2b) — skipping",
                body="",
            )
        ],
        footer="",
    )
    with patch("openlibrary.plugins.openlibrary.status.get_dev_merged_status", return_value=dms):
        assert status_module._merge_conflicted_prs() == frozenset({13370})


def test_load_testing_status_async_wires_merge_conflicts():
    """The async loader passes the deploy-status conflicts into the built rows."""
    state = _make_state()
    dms = status_module.DevMergedStatus(
        git_status="x",
        pr_statuses=[
            status_module.PRStatus(
                pull_line="origin pull/13269/head  # A",
                status="Automatic merge failed; fix conflicts and then commit the result.",
                body="",
            )
        ],
        footer="",
    )
    with (
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status._get_drift_info_async", return_value=({}, False)),
        patch("openlibrary.plugins.openlibrary.status.get_dev_merged_status", return_value=dms),
    ):
        result = asyncio.run(status_module.load_testing_status_async())

    assert result.prs[0].merge_conflict is True


def test_load_testing_status_returns_none_without_state():
    with patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=None):
        assert status_module.load_testing_status() is None


def test_load_testing_status_composes_state_and_drift():
    state = _make_state()
    drift_info = {state.prs[0].pr: {"head_sha": "abc1234", "drift": 2, "merged": False}}
    with (
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status._get_drift_info_async", return_value=(drift_info, False)),
    ):
        result = status_module.load_testing_status()

    assert result.prs[0].drift == 2


def test_pending_changes_itemizes_every_staged_edit():
    """One entry per staged change, ordered add → pin → enable → disable → remove."""
    new_pr = _make_pr(pr_number=13269)  # added after last deploy
    pinned = _make_pr(pr_number=13238, added_at="2026-08-01T10:00:00+00:00")
    pinned.pull_latest_sha = "9f8e7d6c5b4a39281706f5e4d3c2b1a098765432"
    toggled = _make_pr(pr_number=13240, added_at="2026-08-01T10:00:00+00:00")
    toggled.pending_active = False
    state = _make_state(prs=[new_pr, pinned, toggled])

    changes = status_module._pending_changes(state, {})

    assert [(c.kind, c.pr) for c in changes] == [
        ("add", 13269),
        ("pin", 13238),
        ("disable", 13240),
    ]
    assert changes[0].detail == "1d23364"
    assert changes[1].detail == "9f8e7d6"
    assert changes[0].title == "Test PR"


def test_pending_changes_ignores_a_toggle_back_to_the_live_state():
    """Off then on again stages nothing: deploying it would change nothing."""
    pr = _make_pr(pr_number=13240, active=True, added_at="2026-08-01T10:00:00+00:00")
    pr.pending_active = True
    state = _make_state(prs=[pr])

    assert status_module._pending_changes(state, {}) == []
    assert status_module.build_testing_status(state, {}).has_pending is False
    # And the row the template reads carries no pending toggle either: the
    # serialized form normalizes a no-op toggle back to None.
    assert pr.model_dump()["pending_active"] is None


def test_pending_changes_merged_pr_yields_only_a_removal():
    """The deploy drops merged PRs outright, so nothing else staged on one matters."""
    pr = _make_pr(pr_number=13238, added_at="2026-08-01T10:00:00+00:00")
    pr.pull_latest_sha = "9f8e7d6c5b4a39281706f5e4d3c2b1a098765432"
    state = _make_state(prs=[pr])

    changes = status_module._pending_changes(state, {13238: {"merged": True}})

    assert [c.kind for c in changes] == ["remove"]


def test_pending_changes_closed_pr_yields_only_a_removal():
    """A closed (not merged) PR is dropped on deploy just like a merged one."""
    pr = _make_pr(pr_number=13238, added_at="2026-08-01T10:00:00+00:00")
    pr.pull_latest_sha = "9f8e7d6c5b4a39281706f5e4d3c2b1a098765432"
    state = _make_state(prs=[pr])

    changes = status_module._pending_changes(state, {13238: {"merged": False, "closed": True}})

    assert [(c.kind, c.reason) for c in changes] == [("remove", "closed")]


def test_pending_changes_staged_removal_yields_only_a_removal():
    """A staged removal drops the row on deploy, so nothing else staged on it matters."""
    pr = _make_pr(pr_number=13238, added_at="2026-08-01T10:00:00+00:00")
    pr.pending_remove = True
    pr.pull_latest_sha = "9f8e7d6c5b4a39281706f5e4d3c2b1a098765432"
    state = _make_state(prs=[pr])

    changes = status_module._pending_changes(state, {})

    # No reason: unlike merged/closed, this removal the maintainer asked for.
    assert [(c.kind, c.reason) for c in changes] == [("remove", "")]


def test_build_testing_status_marks_closed_prs():
    """A closed PR carries the closed flag and reads as a pending removal."""
    pr = _make_pr(added_at="2026-08-01T10:00:00+00:00")
    state = _make_state(prs=[pr])

    result = status_module.build_testing_status(state, {pr.pr: {"head_sha": "abc1234", "drift": 0, "merged": False, "closed": True}})

    row = result.prs[0]
    assert row.closed is True
    assert row.action == "remove"
    assert result.has_pending is True


@pytest.mark.asyncio
async def test_pr_drift_distinguishes_closed_from_merged():
    """Merging closes a PR too; only a close without a merge counts as closed."""

    async def fake_get(path):
        if path.startswith("pulls/"):
            return {"state": "closed", "merged": False, "merged_at": None, "head": {"sha": "abc1234"}, "user": {}, "assignee": {}, "title": "Closed PR"}
        return {}  # compare response; no ahead_by → drift unknown

    with patch("openlibrary.plugins.openlibrary.status._github_get_async", side_effect=fake_get):
        assert (await status_module._get_pr_drift_async(_make_pr()))["closed"] is True

    async def fake_get_merged(path):
        if path.startswith("pulls/"):
            return {"state": "closed", "merged": True, "merged_at": "2026-08-01", "head": {"sha": "abc1234"}, "user": {}, "assignee": {}, "title": "Merged PR"}
        return {}

    with patch("openlibrary.plugins.openlibrary.status._github_get_async", side_effect=fake_get_merged):
        info = await status_module._get_pr_drift_async(_make_pr())
    assert info["closed"] is False
    assert info["merged"] is True


def test_deploy_drops_closed_prs():
    """Deploying removes closed (not merged) PRs from the set, like merged ones."""
    pr = _make_pr(added_at="2026-08-01T10:00:00+00:00")
    state = _make_state(prs=[pr])

    with (
        patch("openlibrary.plugins.openlibrary.status._is_maintainer", return_value=True),
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch(
            "openlibrary.plugins.openlibrary.status._get_drift_info",
            return_value=({pr.pr: {"head_sha": "", "drift": 0, "merged": False, "closed": True}}, False),
        ),
        patch("openlibrary.plugins.openlibrary.status.trigger_rebuild", return_value="unconfigured"),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state"),
        patch("openlibrary.plugins.openlibrary.status._evict_drift_cache"),
        patch("openlibrary.plugins.openlibrary.status.get_current_user", return_value=None),
    ):
        status_module.status_deploy().POST()

    assert state.prs == []


def test_deploy_drops_staged_removals():
    """Deploying deletes rows whose removal is staged; the rest survive."""
    doomed = _make_pr(added_at="2026-08-01T10:00:00+00:00")
    doomed.pending_remove = True
    survivor = _make_pr(pr_number=13238, added_at="2026-08-01T10:00:00+00:00")
    state = _make_state(prs=[doomed, survivor])

    with (
        patch("openlibrary.plugins.openlibrary.status._is_maintainer", return_value=True),
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status._get_drift_info", return_value=({}, False)),
        patch("openlibrary.plugins.openlibrary.status.trigger_rebuild", return_value="unconfigured"),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state"),
        patch("openlibrary.plugins.openlibrary.status._evict_drift_cache"),
        patch("openlibrary.plugins.openlibrary.status.get_current_user", return_value=None),
    ):
        status_module.status_deploy().POST()

    assert [p.pr for p in state.prs] == [13238]
    assert state.deployed == {13238: survivor.title}


def test_pending_changes_folds_a_pin_into_an_unlanded_add():
    """A PR that isn't live yet lands at its staged SHA, so that's one change, not two."""
    pr = _make_pr(pr_number=13269)  # added after last deploy
    pr.pull_latest_sha = "9f8e7d6c5b4a39281706f5e4d3c2b1a098765432"
    state = _make_state(prs=[pr])

    changes = status_module._pending_changes(state, {})

    assert [c.kind for c in changes] == ["add"]
    assert changes[0].detail == "9f8e7d6"  # the SHA that actually goes live


def test_pending_changes_empty_when_deployed_set_matches():
    state = _make_state(prs=[_make_pr(added_at="2026-08-01T10:00:00+00:00")])

    assert status_module._pending_changes(state, {}) == []
    assert status_module.build_testing_status(state, {}).has_pending is False


def test_pending_changes_counts_everything_before_first_deploy():
    state = _make_state(prs=[_make_pr()], last_deploy_at="")

    changes = status_module._pending_changes(state, {})

    assert [c.kind for c in changes] == ["add"]


def test_payload_marks_live_now_from_the_deployed_set():
    pr = _make_pr(added_at="2026-08-01T10:00:00+00:00")
    state = _make_state(prs=[pr])
    state.deployed = {pr.pr: pr.title}

    result = status_module.build_testing_status(state, {})

    assert result.prs[0].live_now is True
    assert result.prs[0].action == ""  # live and unchanged
    assert result.prs[0].in_set is True


def test_payload_infers_live_now_without_a_deployed_record():
    """Pre-record state files have an empty `deployed`; a PR added before the
    last deploy was part of it, mirroring how _pending_changes treats it."""
    pr = _make_pr(added_at="2026-08-01T10:00:00+00:00")  # before last deploy
    state = _make_state(prs=[pr])  # deployed={} by default

    result = status_module.build_testing_status(state, {})

    assert result.prs[0].live_now is True


def test_payload_never_deployed_means_nothing_live():
    pr = _make_pr()
    state = _make_state(prs=[pr], last_deploy_at="")

    result = status_module.build_testing_status(state, {})

    assert result.prs[0].live_now is False
    assert result.prs[0].action == "add"


def test_payload_action_mirrors_the_plan_kinds():
    """The row chip names the same change the plan itemizes."""
    new_pr = _make_pr(pr_number=13269)  # added after last deploy
    pinned = _make_pr(pr_number=13238, added_at="2026-08-01T10:00:00+00:00")
    pinned.pull_latest_sha = "9f8e7d6c5b4a39281706f5e4d3c2b1a098765432"
    disabled = _make_pr(pr_number=13240, active=True, added_at="2026-08-01T10:00:00+00:00")
    disabled.pending_active = False
    state = _make_state(prs=[new_pr, pinned, disabled])
    state.deployed = {13238: pinned.title, 13240: disabled.title}

    result = status_module.build_testing_status(state, {})
    actions = {p.pr: p.action for p in result.prs}

    assert actions == {13269: "add", 13238: "pin", 13240: "disable"}


def test_payload_marks_a_staged_removal():
    """The row stays in the set with its state intact, reading as a pending removal."""
    pr = _make_pr(added_at="2026-08-01T10:00:00+00:00")
    pr.pending_remove = True
    state = _make_state(prs=[pr])
    state.deployed = {pr.pr: pr.title}

    result = status_module.build_testing_status(state, {})
    row = result.prs[0]

    assert (row.pending_remove, row.in_set, row.action) == (True, True, "remove")
    assert result.has_pending is True


def test_payload_includes_dropped_prs_as_readonly_rows():
    """Removed from the set but still on the box: a REMOVE row, not a ghost."""
    pr = _make_pr(pr_number=13269, added_at="2026-08-01T10:00:00+00:00")
    state = _make_state(prs=[pr])
    state.deployed = {13269: pr.title, 13238: "Old PR"}

    result = status_module.build_testing_status(state, {})
    dropped = next(p for p in result.prs if p.pr == 13238)

    assert dropped.in_set is False
    assert dropped.live_now is True
    assert dropped.action == "remove"
    assert dropped.title == "Old PR"
    assert dropped.drift == -1


@pytest.mark.parametrize(
    ("age_seconds", "expected"),
    [(60, True), (status_module._DEPLOY_WINDOW + 60, False)],
)
def test_is_deploying_is_a_window_not_a_result(age_seconds, expected):
    started = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=age_seconds)
    state = _make_state()
    state.deploy_started_at = started.isoformat()

    assert status_module._is_deploying(state) is expected


def test_is_deploying_false_without_a_triggered_build():
    """No Jenkins token means no build was accepted, so nothing is in flight."""
    assert status_module._is_deploying(_make_state()) is False


def test_load_testing_state_accepts_legacy_bare_array(tmp_path, monkeypatch):
    """State files predating the object format (a bare array) still load."""
    state_file = tmp_path / "_testing-prs.json"
    state_file.write_text(json.dumps([{"pr": 13269, "commit": "1d23364b8c652d6107e2dc685f918551fda5d327", "active": True, "title": "Test PR"}]))
    monkeypatch.setattr(status_module, "TESTING_STATE_FILE", state_file)

    state = status_module._load_testing_state()

    assert state is not None
    assert state.last_deploy_at == ""
    assert state.prs[0].pr == 13269
    assert state.prs[0].added_at == ""  # field that postdates the legacy format
    assert state.prs[0].pull_latest_sha == ""


def test_ensure_testing_state_file_creates_empty_state(tmp_path, monkeypatch):
    state_file = tmp_path / "_testing-prs.json"
    monkeypatch.setattr(status_module, "TESTING_STATE_FILE", state_file)

    status_module._ensure_testing_state_file()

    assert json.loads(state_file.read_text()) == {"last_deploy_at": "", "prs": []}


def test_ensure_testing_state_file_does_not_overwrite_existing(tmp_path, monkeypatch):
    state_file = tmp_path / "_testing-prs.json"
    state_file.write_text(json.dumps({"last_deploy_at": "x", "prs": [{"pr": 13269}]}))
    monkeypatch.setattr(status_module, "TESTING_STATE_FILE", state_file)

    status_module._ensure_testing_state_file()

    assert json.loads(state_file.read_text())["prs"][0]["pr"] == 13269


def test_setup_ensures_testing_state_file_in_local_dev(monkeypatch):
    calls = []
    monkeypatch.setattr(status_module, "_ensure_testing_state_file", lambda: calls.append(True))
    env = MagicMock()
    env.LOCAL_DEV = True
    monkeypatch.setattr(status_module, "get_ol_env", lambda: env)
    monkeypatch.setattr(status_module.stats, "increment", lambda *args, **kwargs: None)
    monkeypatch.setattr(status_module, "get_software_version", lambda: "test")

    status_module.setup()

    assert calls == [True]


def test_setup_skips_state_file_creation_outside_local_dev(monkeypatch):
    calls = []
    monkeypatch.setattr(status_module, "_ensure_testing_state_file", lambda: calls.append(True))
    env = MagicMock()
    env.LOCAL_DEV = False
    monkeypatch.setattr(status_module, "get_ol_env", lambda: env)
    monkeypatch.setattr(status_module.stats, "increment", lambda *args, **kwargs: None)
    monkeypatch.setattr(status_module, "get_software_version", lambda: "test")

    status_module.setup()

    assert calls == []


def _make_deploy_state():
    """A state with one staged pin and one staged disable, both before the last deploy."""
    pinned = _make_pr(pr_number=13238, added_at="2026-08-01T10:00:00+00:00")
    pinned.pull_latest_sha = "9f8e7d6c5b4a39281706f5e4d3c2b1a098765432"
    toggled = _make_pr(pr_number=13240, added_at="2026-08-01T10:00:00+00:00")
    toggled.pending_active = False
    return _make_state(prs=[pinned, toggled])


def test_add_appends_pr_when_github_succeeds():
    """A successful GitHub fetch adds the PR and answers ok."""
    state = status_module.TestingState(last_deploy_at="", prs=[])
    gh_info = {
        "title": "Test PR",
        "head_sha": "abc1234def5678901234567890123456789012345",
        "author": "author",
        "author_avatar": "",
        "assignee": "assignee",
        "assignee_avatar": "",
        "error": "",
    }
    with (
        patch("openlibrary.plugins.openlibrary.status._is_maintainer", return_value=True),
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status._get_pr_info", return_value=gh_info),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state"),
        patch("openlibrary.plugins.openlibrary.status._evict_drift_cache"),
        patch("openlibrary.plugins.openlibrary.status.get_current_user", return_value=None),
        patch("web.input", return_value=web.storage(pr="12914")),
    ):
        response = status_module.status_add().POST()

    assert json.loads(response["rawtext"]) == {"ok": True}
    assert [p.pr for p in state.prs] == [12914]


def test_add_skips_pr_and_marks_failure_when_github_errors():
    """A GitHub failure (rate limit, outage, invalid PR) must not pretend the add landed."""
    state = status_module.TestingState(last_deploy_at="", prs=[])
    gh_info = {
        "title": "PR #12914",
        "head_sha": "",
        "author": "",
        "author_avatar": "",
        "assignee": "",
        "assignee_avatar": "",
        "error": "unavailable",
    }
    with (
        patch("openlibrary.plugins.openlibrary.status._is_maintainer", return_value=True),
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status._get_pr_info", return_value=gh_info),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state"),
        patch("openlibrary.plugins.openlibrary.status._evict_drift_cache"),
        patch("openlibrary.plugins.openlibrary.status.get_current_user", return_value=None),
        patch("web.input", return_value=web.storage(pr="12914")),
    ):
        response = status_module.status_add().POST()

    # The error code is what lets the panel keep the add input.
    assert json.loads(response["rawtext"]) == {"ok": False, "error": "add_failed"}
    assert state.prs == []


def test_remove_stages_a_removal_for_a_live_pr():
    """Removing a deployed PR stages it: the row survives with its pin and toggle."""
    pr = _make_pr(added_at="2026-08-01T10:00:00+00:00")
    pr.pull_latest_sha = "9f8e7d6c5b4a39281706f5e4d3c2b1a098765432"
    state = _make_state(prs=[pr])
    state.deployed = {pr.pr: pr.title}

    with (
        patch("openlibrary.plugins.openlibrary.status._is_maintainer", return_value=True),
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state") as mock_save,
        patch("web.input", return_value=web.storage(prs=["13269"])),
    ):
        response = status_module.status_remove().POST()

    assert json.loads(response["rawtext"]) == {"ok": True}
    assert [p.pr for p in state.prs] == [13269]
    assert state.prs[0].pending_remove is True
    assert state.prs[0].pull_latest_sha == "9f8e7d6c5b4a39281706f5e4d3c2b1a098765432"
    mock_save.assert_called_once_with(state)


def test_remove_deletes_a_never_deployed_pr_outright():
    """A PR that never reached the box has nothing to undo, so no staged removal."""
    pr = _make_pr()  # added after last deploy
    state = _make_state(prs=[pr])
    state.deployed = {13238: "Other PR"}

    with (
        patch("openlibrary.plugins.openlibrary.status._is_maintainer", return_value=True),
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state"),
        patch("web.input", return_value=web.storage(prs=["13269"])),
    ):
        status_module.status_remove().POST()

    assert state.prs == []


def test_restore_clears_a_staged_removal():
    pr = _make_pr(added_at="2026-08-01T10:00:00+00:00")
    pr.pending_remove = True
    state = _make_state(prs=[pr])

    with (
        patch("openlibrary.plugins.openlibrary.status._is_maintainer", return_value=True),
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state") as mock_save,
        patch("web.input", return_value=web.storage(prs=["13269"])),
    ):
        response = status_module.status_restore().POST()

    assert json.loads(response["rawtext"]) == {"ok": True}
    assert state.prs[0].pending_remove is False
    mock_save.assert_called_once_with(state)


def test_add_cancels_a_staged_removal():
    """Re-adding a PR whose removal is staged is an undo, not a duplicate row."""
    pr = _make_pr(added_at="2026-08-01T10:00:00+00:00")
    pr.pending_remove = True
    state = _make_state(prs=[pr])

    with (
        patch("openlibrary.plugins.openlibrary.status._is_maintainer", return_value=True),
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status._get_pr_info") as mock_info,
        patch("openlibrary.plugins.openlibrary.status._save_testing_state"),
        patch("openlibrary.plugins.openlibrary.status._evict_drift_cache"),
        patch("openlibrary.plugins.openlibrary.status.get_current_user", return_value=None),
        patch("web.input", return_value=web.storage(pr="13269")),
    ):
        response = status_module.status_add().POST()

    assert json.loads(response["rawtext"]) == {"ok": True}
    assert [p.pr for p in state.prs] == [13269]
    assert state.prs[0].pending_remove is False
    # Already in the set: no GitHub fetch, no fresh row.
    mock_info.assert_not_called()


def test_deploy_unconfigured_answers_error_but_advances_state():
    """Local dev (no Jenkins token): state advances so the UI is exercisable,
    but the response says nothing was actually deployed."""
    state = _make_state(prs=[_make_pr(added_at="2026-08-01T10:00:00+00:00")])

    with (
        patch("openlibrary.plugins.openlibrary.status._is_maintainer", return_value=True),
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status._get_drift_info", return_value=({}, False)),
        patch("openlibrary.plugins.openlibrary.status.trigger_rebuild", return_value="unconfigured"),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state"),
        patch("openlibrary.plugins.openlibrary.status._evict_drift_cache"),
        patch("openlibrary.plugins.openlibrary.status.get_current_user", return_value=None),
    ):
        response = status_module.status_deploy().POST()

    assert json.loads(response["rawtext"]) == {"ok": False, "error": "deploy_unconfigured"}
    # No build was accepted, so no deploy window starts…
    assert state.deploy_started_at == ""
    # …but the record advances so a dev can exercise the rest of the panel.
    assert state.deployed == {13269: "Test PR"}


def test_get_pr_info_distinguishes_not_found_from_unavailable():
    """404 → not_found; rate limit → unavailable; both leave head_sha empty."""
    request = httpx.Request("GET", "https://api.github.com/repos/internetarchive/openlibrary/pulls/12914")
    with patch(
        "openlibrary.plugins.openlibrary.status._github_get_async",
        side_effect=httpx.HTTPStatusError("Not Found", request=request, response=httpx.Response(404, request=request)),
    ):
        info = status_module._get_pr_info(12914)
    assert info["error"] == "not_found"
    assert info["head_sha"] == ""

    with patch(
        "openlibrary.plugins.openlibrary.status._github_get_async",
        side_effect=httpx.HTTPStatusError("rate limit exceeded", request=request, response=httpx.Response(403, request=request)),
    ):
        info = status_module._get_pr_info(12914)
    assert info["error"] == "unavailable"
    assert info["head_sha"] == ""


def test_deploy_failure_never_persists_staged_changes():
    """A failed Jenkins trigger must not write staged changes to disk.

    Regression: status_deploy used to call _get_drift_info(state) after staging
    changes, and that helper's metadata refresh saved the file — persisting
    pins/toggles before Jenkins accepted the build. The drift read is now
    persist=False, and the only save happens after a successful trigger.
    """
    state = _make_deploy_state()

    with (
        patch("openlibrary.plugins.openlibrary.status._is_maintainer", return_value=True),
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch(
            "openlibrary.plugins.openlibrary.status._get_drift_info",
            return_value=(
                {13238: {"head_sha": "", "drift": 0, "merged": False}, 13240: {"head_sha": "", "drift": 0, "merged": False}},
                False,
            ),
        ) as mock_drift,
        patch("openlibrary.plugins.openlibrary.status.trigger_rebuild", return_value="failed"),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state") as mock_save,
    ):
        response = status_module.status_deploy().POST()

    assert json.loads(response["rawtext"]) == {"ok": False, "error": "deploy_failed"}
    # The drift read is a read, not a commit: it must not persist.
    mock_drift.assert_called_once_with(state, persist=False)
    mock_save.assert_not_called()


def test_deploy_success_applies_staged_changes_then_saves_once():
    """A successful trigger lands the staged pins/toggles and saves exactly once."""
    state = _make_deploy_state()
    pinned, toggled = state.prs

    with (
        patch("openlibrary.plugins.openlibrary.status._is_maintainer", return_value=True),
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch(
            "openlibrary.plugins.openlibrary.status._get_drift_info",
            return_value=(
                {13238: {"head_sha": "", "drift": 0, "merged": False}, 13240: {"head_sha": "", "drift": 0, "merged": False}},
                False,
            ),
        ),
        patch("openlibrary.plugins.openlibrary.status.trigger_rebuild", return_value="triggered"),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state") as mock_save,
        patch("openlibrary.plugins.openlibrary.status._evict_drift_cache"),
        patch("openlibrary.plugins.openlibrary.status.get_current_user", return_value=None),
    ):
        response = status_module.status_deploy().POST()

    assert json.loads(response["rawtext"]) == {"ok": True}
    # Pin applied and consumed.
    assert pinned.commit == "9f8e7d6c5b4a39281706f5e4d3c2b1a098765432"
    assert pinned.pull_latest_sha == ""
    # Toggle applied and consumed.
    assert toggled.active is False
    assert toggled.pending_active is None
    # The deploy record is what the build put on the box: active PRs only, so
    # the disabled one is not on it.
    assert state.deployed == {13238: pinned.title}
    assert state.last_deploy_at
    mock_save.assert_called_once_with(state)


def test_deploy_records_who_clicked_it():
    """A deploy records the OL username of the maintainer who clicked it."""
    state = _make_state(prs=[_make_pr(added_at="2026-08-01T10:00:00+00:00")])
    user = MagicMock()
    user.key = "/people/mecha-kraken"

    with (
        patch("openlibrary.plugins.openlibrary.status._is_maintainer", return_value=True),
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status._get_drift_info", return_value=({}, False)),
        patch("openlibrary.plugins.openlibrary.status.trigger_rebuild", return_value="triggered"),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state"),
        patch("openlibrary.plugins.openlibrary.status._evict_drift_cache"),
        patch("openlibrary.plugins.openlibrary.status.get_current_user", return_value=user),
    ):
        status_module.status_deploy().POST()

    assert state.deployed_by == "mecha-kraken"


def test_build_testing_status_passes_deployed_by():
    """The API response carries the recorded deployer username through."""
    state = _make_state(prs=[_make_pr(added_at="2026-08-01T10:00:00+00:00")])
    state.deployed_by = "mecha-kraken"

    result = status_module.build_testing_status(state, {})

    assert result.deployed_by == "mecha-kraken"


def test_testing_status_endpoint(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    mock_maintainer_user(is_maintainer=True)
    state = _make_state()
    result = status_module.build_testing_status(state, {13269: {"head_sha": "abc1234", "drift": 2, "merged": False}})
    with (
        patch("openlibrary.fastapi.status.load_testing_status_async", AsyncMock(return_value=result)) as mock,
        patch("openlibrary.fastapi.status.jenkins_deploy_status", AsyncMock(return_value=None)),
    ):
        response = fastapi_client.get("/status/testing.json")

    assert response.status_code == 200
    assert response.json() == {
        "last_deploy_at": "2026-08-05T18:00:00+00:00",
        "deployed_by": "",
        "deploy_started_at": "",
        "deploying": False,
        "deploy_result": "",
        "deploy_finished_at": "",
        "deploy_stage": "",
        "has_pending": True,
        "pending_changes": [{"pr": 13269, "title": "Test PR", "kind": "add", "detail": "1d23364", "reason": ""}],
        "prs": [
            {
                "pr": 13269,
                "title": "Test PR",
                "commit": "1d23364b8c652d6107e2dc685f918551fda5d327",
                "active": True,
                "added_at": "2026-08-06T15:00:00+00:00",
                "added_by": "openlibrary",
                "pull_latest_sha": "",
                "pending_active": None,
                "pending_remove": False,
                "author": "author",
                "author_avatar": "",
                "assignee": "assignee",
                "assignee_avatar": "",
                "head_sha": "abc1234",
                "drift": 2,
                "merged": False,
                "closed": False,
                "is_new": True,
                "live_now": False,
                "merge_conflict": False,
                "action": "add",
                "in_set": True,
            }
        ],
    }
    mock.assert_called_once_with()


def test_testing_status_endpoint_matches_response_model(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    mock_maintainer_user(is_maintainer=True)
    result = status_module.build_testing_status(_make_state(last_deploy_at=""), {})
    with (
        patch("openlibrary.fastapi.status.load_testing_status_async", AsyncMock(return_value=result)),
        patch("openlibrary.fastapi.status.jenkins_deploy_status", AsyncMock(return_value=None)),
    ):
        response = fastapi_client.get("/status/testing.json")

    assert response.status_code == 200
    assert status_module.TestingStatus(**response.json()).model_dump() == response.json()


def test_testing_status_endpoint_reports_jenkins_result(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    """The latest Jenkins run replaces the time-window guess with real status."""
    mock_maintainer_user(is_maintainer=True)
    result = status_module.build_testing_status(_make_state(), {})
    # A stale state-file start time (e.g. a week-old local copy): Jenkins' run
    # start must win, or the panel says "Deploying, started 7 days ago".
    result.deploy_started_at = "2026-08-11T09:00:00+00:00"
    jenkins = {
        "status": "SUCCESS",
        "start_time": "2026-08-18T20:25:57.516000+00:00",
        "end_time": "2026-08-18T20:27:07.498000+00:00",
        "current_stage": "",
    }
    with (
        patch("openlibrary.fastapi.status.load_testing_status_async", AsyncMock(return_value=result)),
        patch("openlibrary.fastapi.status.jenkins_deploy_status", AsyncMock(return_value=jenkins)),
    ):
        response = fastapi_client.get("/status/testing.json")

    assert response.status_code == 200
    body = response.json()
    assert body["deploying"] is False
    assert body["deploy_started_at"] == jenkins["start_time"]
    assert body["deploy_result"] == "SUCCESS"
    assert body["deploy_finished_at"] == jenkins["end_time"]
    assert body["deploy_stage"] == ""


def test_testing_status_endpoint_reports_deploy_stage(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    """A running deploy names the stage it is on."""
    mock_maintainer_user(is_maintainer=True)
    result = status_module.build_testing_status(_make_state(), {})
    # Stale state-file start time; the live Jenkins run's start must replace it.
    result.deploy_started_at = "2026-08-11T09:00:00+00:00"
    jenkins = {
        "status": "IN_PROGRESS",
        "start_time": "2026-08-18T20:25:57.516000+00:00",
        "end_time": "",
        "current_stage": "components",
    }
    with (
        patch("openlibrary.fastapi.status.load_testing_status_async", AsyncMock(return_value=result)),
        patch("openlibrary.fastapi.status.jenkins_deploy_status", AsyncMock(return_value=jenkins)),
    ):
        response = fastapi_client.get("/status/testing.json")

    assert response.status_code == 200
    body = response.json()
    assert body["deploying"] is True
    assert body["deploy_started_at"] == jenkins["start_time"]
    assert body["deploy_stage"] == "components"


@pytest.mark.asyncio
async def test_jenkins_deploy_status_parses_latest_run():
    """wfapi/runs is newest-first: status and timestamps come from the first run."""
    runs = [
        {
            "status": "SUCCESS",
            "startTimeMillis": 1787085957516,
            "endTimeMillis": 1787086027498,
            "stages": [{"name": "js", "status": "SUCCESS"}, {"name": "components", "status": "SUCCESS"}],
        },
        {"status": "IN_PROGRESS", "startTimeMillis": 1787085000000, "endTimeMillis": None, "stages": []},
    ]
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = runs
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("openlibrary.plugins.openlibrary.jenkins.httpx.AsyncClient", return_value=mock_client):
        result = await jenkins_module.jenkins_deploy_status()

    assert result["status"] == "SUCCESS"
    assert result["start_time"].startswith("2026-08-18T")
    assert result["end_time"].startswith("2026-08-18T")
    assert result["current_stage"] == ""  # a finished run has no current stage


@pytest.mark.asyncio
async def test_jenkins_deploy_status_reports_current_stage():
    """A running build names the stage Jenkins is executing."""
    runs = [
        {
            "status": "IN_PROGRESS",
            "startTimeMillis": 1787085957516,
            "endTimeMillis": None,
            "stages": [
                {"name": "Checkout", "status": "SUCCESS"},
                {"name": "js", "status": "SUCCESS"},
                {"name": "components", "status": "IN_PROGRESS"},
                {"name": "deploy", "status": "NOT_EXECUTED"},
            ],
        }
    ]
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = runs
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("openlibrary.plugins.openlibrary.jenkins.httpx.AsyncClient", return_value=mock_client):
        result = await jenkins_module.jenkins_deploy_status()

    assert result["status"] == "IN_PROGRESS"
    assert result["current_stage"] == "components"


@pytest.mark.asyncio
async def test_jenkins_deploy_status_returns_none_on_error():
    """Jenkins being down falls back to the state file's time-window guess."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=httpx.RequestError("down"))

    with patch("openlibrary.plugins.openlibrary.jenkins.httpx.AsyncClient", return_value=mock_client):
        assert await jenkins_module.jenkins_deploy_status() is None


def test_testing_status_endpoint_404_when_no_state(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    mock_maintainer_user(is_maintainer=True)
    with (
        patch("openlibrary.fastapi.status.load_testing_status_async", AsyncMock(return_value=None)),
        patch("openlibrary.fastapi.status.jenkins_deploy_status", AsyncMock(return_value=None)),
    ):
        response = fastapi_client.get("/status/testing.json")

    assert response.status_code == 404


def test_testing_status_fetches_github_and_jenkins_concurrently(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    """The GitHub drift fetch and the Jenkins fetch start together, not in sequence."""
    mock_maintainer_user(is_maintainer=True)
    result = status_module.build_testing_status(_make_state(), {})
    active = 0
    peak = 0

    async def fake_load():
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.05)  # yield so the other fetch can start
        active -= 1
        return result

    async def fake_jenkins():
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.05)
        active -= 1

    with (
        patch("openlibrary.fastapi.status.load_testing_status_async", side_effect=fake_load),
        patch("openlibrary.fastapi.status.jenkins_deploy_status", side_effect=fake_jenkins),
    ):
        response = fastapi_client.get("/status/testing.json")

    assert response.status_code == 200
    assert peak == 2  # sequential awaits would peak at 1


def test_testing_status_endpoint_requires_auth(fastapi_client):
    response = fastapi_client.get("/status/testing.json")

    assert response.status_code == 401


def test_testing_status_endpoint_forbidden_for_non_maintainer(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    mock_maintainer_user(is_maintainer=False)
    with patch("openlibrary.fastapi.status.load_testing_status_async", AsyncMock()) as mock:
        response = fastapi_client.get("/status/testing.json")

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"
    mock.assert_not_called()
