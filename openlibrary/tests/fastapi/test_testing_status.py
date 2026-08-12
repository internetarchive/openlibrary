"""Tests for the testing-environment status API and its underlying helper."""

import datetime
import json
from unittest.mock import MagicMock, patch

import pytest

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


def test_get_testing_status_merges_drift_and_derived_fields():
    state = _make_state()
    drift_info = {state.prs[0].pr: {"head_sha": "abc1234", "drift": 2, "merged": False}}
    with (
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status._get_drift_info", return_value=(drift_info, False)),
    ):
        payload = status_module.get_testing_status()

    assert payload["last_deploy_at"] == "2026-08-05T18:00:00+00:00"
    assert payload["has_pending"] is True  # added after last deploy
    pr = payload["prs"][0]
    assert pr["head_sha"] == "abc1234"
    assert pr["drift"] == 2
    assert pr["merged"] is False
    assert pr["is_new"] is True
    assert pr["title"] == "Test PR"
    assert pr["added_by"] == "openlibrary"


def test_get_testing_status_accepts_precomputed_state_and_drift():
    state = _make_state(prs=[_make_pr(pr_number=13238)])
    drift_info = {13238: {"head_sha": "", "drift": -1, "merged": True}}
    payload = status_module.get_testing_status(state, drift_info)

    assert payload["prs"][0]["drift"] == -1
    assert payload["prs"][0]["merged"] is True


def test_get_testing_status_returns_none_without_state():
    with patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=None):
        assert status_module.get_testing_status() is None


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
    assert status_module.get_testing_status(state, {})["has_pending"] is False
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
    assert status_module.get_testing_status(state, {})["has_pending"] is False


def test_pending_changes_counts_everything_before_first_deploy():
    state = _make_state(prs=[_make_pr()], last_deploy_at="")

    changes = status_module._pending_changes(state, {})

    assert [c["kind"] for c in changes] == ["add"]


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


def test_testing_status_endpoint(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    mock_maintainer_user(is_maintainer=True)
    payload = {
        "last_deploy_at": "2026-08-05T18:00:00+00:00",
        "deploy_started_at": "",
        "deploying": False,
        "has_pending": True,
        "pending_changes": [{"pr": 13269, "title": "Test PR", "kind": "add", "detail": "1d23364"}],
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
            }
        ],
    }
    with patch("openlibrary.fastapi.status.get_testing_status", return_value=payload) as mock:
        response = fastapi_client.get("/status/testing.json")

    assert response.status_code == 200
    assert response.json() == payload
    mock.assert_called_once_with()


def test_testing_status_endpoint_matches_response_model(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    mock_maintainer_user(is_maintainer=True)
    payload = {
        "last_deploy_at": "",
        "has_pending": False,
        "prs": [_make_pr().to_dict()],
    }
    with patch("openlibrary.fastapi.status.get_testing_status", return_value=payload):
        response = fastapi_client.get("/status/testing.json")

    assert response.status_code == 200
    assert fastapi_status.TestingStatusResponse(**response.json()).model_dump() == response.json()


def test_testing_status_endpoint_404_when_no_state(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    mock_maintainer_user(is_maintainer=True)
    with patch("openlibrary.fastapi.status.get_testing_status", return_value=None):
        response = fastapi_client.get("/status/testing.json")

    assert response.status_code == 404


def test_testing_status_endpoint_requires_auth(fastapi_client):
    response = fastapi_client.get("/status/testing.json")

    assert response.status_code == 401


def test_testing_status_endpoint_forbidden_for_non_maintainer(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    mock_maintainer_user(is_maintainer=False)
    payload = {"last_deploy_at": "", "has_pending": False, "prs": []}
    with patch("openlibrary.fastapi.status.get_testing_status", return_value=payload) as mock:
        response = fastapi_client.get("/status/testing.json")

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"
    mock.assert_not_called()
