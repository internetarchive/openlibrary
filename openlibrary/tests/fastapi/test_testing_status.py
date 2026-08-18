"""Tests for the testing-environment status API and its underlying helper."""

import asyncio
import datetime
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import web

import openlibrary.fastapi.status as fastapi_status
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
    assert result.pending_changes == [{"pr": 13269, "title": "Test PR", "kind": "add", "detail": "1d23364", "reason": ""}]
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
    assert drift == {p.pr: {"head_sha": "abc1234", "drift": 0, "merged": False} for p in state.prs}


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

    assert [(c["kind"], c["pr"]) for c in changes] == [
        ("add", 13269),
        ("pin", 13238),
        ("disable", 13240),
    ]
    assert changes[0]["detail"] == "1d23364"
    assert changes[1]["detail"] == "9f8e7d6"
    assert changes[0]["title"] == "Test PR"


def test_pending_changes_ignores_a_toggle_back_to_the_live_state():
    """Off then on again stages nothing: deploying it would change nothing."""
    pr = _make_pr(pr_number=13240, active=True, added_at="2026-08-01T10:00:00+00:00")
    pr.pending_active = True
    state = _make_state(prs=[pr])

    assert status_module._pending_changes(state, {}) == []
    assert status_module.build_testing_status(state, {}).has_pending is False
    # And the row the template reads carries no pending toggle either.
    assert "pending_active" not in pr.to_dict()


def test_pending_changes_merged_pr_yields_only_a_removal():
    """The deploy drops merged PRs outright, so nothing else staged on one matters."""
    pr = _make_pr(pr_number=13238, added_at="2026-08-01T10:00:00+00:00")
    pr.pull_latest_sha = "9f8e7d6c5b4a39281706f5e4d3c2b1a098765432"
    state = _make_state(prs=[pr])

    changes = status_module._pending_changes(state, {13238: {"merged": True}})

    assert [c["kind"] for c in changes] == ["remove"]


def test_pending_changes_folds_a_pin_into_an_unlanded_add():
    """A PR that isn't live yet lands at its staged SHA, so that's one change, not two."""
    pr = _make_pr(pr_number=13269)  # added after last deploy
    pr.pull_latest_sha = "9f8e7d6c5b4a39281706f5e4d3c2b1a098765432"
    state = _make_state(prs=[pr])

    changes = status_module._pending_changes(state, {})

    assert [c["kind"] for c in changes] == ["add"]
    assert changes[0]["detail"] == "9f8e7d6"  # the SHA that actually goes live


def test_pending_changes_empty_when_deployed_set_matches():
    state = _make_state(prs=[_make_pr(added_at="2026-08-01T10:00:00+00:00")])

    assert status_module._pending_changes(state, {}) == []
    assert status_module.build_testing_status(state, {}).has_pending is False


def test_pending_changes_counts_everything_before_first_deploy():
    state = _make_state(prs=[_make_pr()], last_deploy_at="")

    changes = status_module._pending_changes(state, {})

    assert [c["kind"] for c in changes] == ["add"]


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


def _seed_web_ctx():
    """Minimal web.py request context so web.seeother() can build its redirect."""
    web.ctx.path = "/status/deploy"
    web.ctx.home = "http://localhost:8080"
    web.ctx.headers = []


def test_add_appends_pr_when_github_succeeds():
    """A successful GitHub fetch adds the PR and redirects cleanly."""
    _seed_web_ctx()
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
        pytest.raises(web.SeeOther),
    ):
        status_module.status_add().POST()

    assert ("Location", "http://localhost:8080/status") in web.ctx.headers
    assert [p.pr for p in state.prs] == [12914]


def test_add_skips_pr_and_marks_failure_when_github_errors():
    """A GitHub failure (rate limit, outage, invalid PR) must not pretend the add landed."""
    _seed_web_ctx()
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
        pytest.raises(web.SeeOther),
    ):
        status_module.status_add().POST()

    # The redirect marker is what lets the panel keep the add input.
    assert ("Location", "http://localhost:8080/status?add_failed=1") in web.ctx.headers
    assert state.prs == []


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
    _seed_web_ctx()
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
        patch("openlibrary.plugins.openlibrary.status._trigger_rebuild", return_value="failed"),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state") as mock_save,
        pytest.raises(web.SeeOther),
    ):
        status_module.status_deploy().POST()

    assert ("Location", "http://localhost:8080/status?deploy_failed=1") in web.ctx.headers
    # The drift read is a read, not a commit: it must not persist.
    mock_drift.assert_called_once_with(state, persist=False)
    mock_save.assert_not_called()


def test_deploy_success_applies_staged_changes_then_saves_once():
    """A successful trigger lands the staged pins/toggles and saves exactly once."""
    _seed_web_ctx()
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
        patch("openlibrary.plugins.openlibrary.status._trigger_rebuild", return_value="triggered"),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state") as mock_save,
        patch("openlibrary.plugins.openlibrary.status._evict_drift_cache"),
        pytest.raises(web.SeeOther),
    ):
        status_module.status_deploy().POST()

    assert ("Location", "http://localhost:8080/status?deploy_triggered=1") in web.ctx.headers
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
        "deploy_started_at": "",
        "deploying": False,
        "deploy_result": "",
        "deploy_finished_at": "",
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
                "author": "author",
                "author_avatar": "",
                "assignee": "assignee",
                "assignee_avatar": "",
                "head_sha": "abc1234",
                "drift": 2,
                "merged": False,
                "is_new": True,
                "live_now": False,
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
    assert fastapi_status.TestingStatusResponse(**response.json()).model_dump() == response.json()


def test_testing_status_endpoint_reports_jenkins_result(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    """The latest Jenkins run replaces the time-window guess with real status."""
    mock_maintainer_user(is_maintainer=True)
    result = status_module.build_testing_status(_make_state(), {})
    jenkins = {
        "status": "SUCCESS",
        "start_time": "2026-08-18T20:25:57.516000+00:00",
        "end_time": "2026-08-18T20:27:07.498000+00:00",
    }
    with (
        patch("openlibrary.fastapi.status.load_testing_status_async", AsyncMock(return_value=result)),
        patch("openlibrary.fastapi.status.jenkins_deploy_status", AsyncMock(return_value=jenkins)),
    ):
        response = fastapi_client.get("/status/testing.json")

    assert response.status_code == 200
    body = response.json()
    assert body["deploying"] is False
    assert body["deploy_result"] == "SUCCESS"
    assert body["deploy_finished_at"] == jenkins["end_time"]


@pytest.mark.asyncio
async def test_jenkins_deploy_status_parses_latest_run():
    """wfapi/runs is newest-first: status and timestamps come from the first run."""
    runs = [
        {"status": "SUCCESS", "startTimeMillis": 1787085957516, "endTimeMillis": 1787086027498},
        {"status": "IN_PROGRESS", "startTimeMillis": 1787085000000, "endTimeMillis": None},
    ]
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = runs
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    mc = MagicMock()
    mc.get.return_value = None
    with (
        patch("openlibrary.plugins.openlibrary.status.cache.get_memcache", return_value=mc),
        patch("openlibrary.plugins.openlibrary.status.httpx.AsyncClient", return_value=mock_client),
    ):
        result = await status_module.jenkins_deploy_status()

    assert result["status"] == "SUCCESS"
    assert result["start_time"].startswith("2026-08-18T")
    assert result["end_time"].startswith("2026-08-18T")


@pytest.mark.asyncio
async def test_jenkins_deploy_status_returns_none_on_error():
    """Jenkins being down falls back to the state file's time-window guess."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=httpx.RequestError("down"))

    mc = MagicMock()
    mc.get.return_value = None
    with (
        patch("openlibrary.plugins.openlibrary.status.cache.get_memcache", return_value=mc),
        patch("openlibrary.plugins.openlibrary.status.httpx.AsyncClient", return_value=mock_client),
    ):
        assert await status_module.jenkins_deploy_status() is None


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
