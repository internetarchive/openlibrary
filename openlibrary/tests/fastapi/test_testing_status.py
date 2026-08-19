"""Tests for the testing-environment status API and its underlying helper."""

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


def test_build_testing_status_merges_drift_and_derived_fields():
    state = _make_state()
    drift_info = {state.prs[0].pr: {"head_sha": "abc1234", "drift": 2, "merged": False}}

    result = status_module.build_testing_status(state, drift_info)

    assert result.last_deploy_at == "2026-08-05T18:00:00+00:00"
    assert result.has_pending is True  # added after last deploy
    pr = result.prs[0]
    assert (pr.head_sha, pr.drift, pr.merged, pr.is_new) == ("abc1234", 2, False, True)
    assert (pr.title, pr.added_by) == ("Test PR", "openlibrary")


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


def test_load_testing_status_returns_none_without_state():
    with patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=None):
        assert status_module.load_testing_status() is None


def test_load_testing_status_composes_state_and_drift():
    state = _make_state()
    drift_info = {state.prs[0].pr: {"head_sha": "abc1234", "drift": 2, "merged": False}}
    with (
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status._get_drift_info", return_value=(drift_info, False)),
    ):
        result = status_module.load_testing_status()

    assert result.prs[0].drift == 2


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
    state = _make_state()
    result = status_module.build_testing_status(state, {13269: {"head_sha": "abc1234", "drift": 2, "merged": False}})
    with patch("openlibrary.fastapi.status.load_testing_status", return_value=result) as mock:
        response = fastapi_client.get("/status/testing.json")

    assert response.status_code == 200
    assert response.json() == {
        "last_deploy_at": "2026-08-05T18:00:00+00:00",
        "has_pending": True,
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
    mock.assert_called_once_with()


def test_testing_status_endpoint_matches_response_model(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    mock_maintainer_user(is_maintainer=True)
    result = status_module.build_testing_status(_make_state(last_deploy_at=""), {})
    with patch("openlibrary.fastapi.status.load_testing_status", return_value=result):
        response = fastapi_client.get("/status/testing.json")

    assert response.status_code == 200
    assert fastapi_status.TestingStatusResponse(**response.json()).model_dump() == response.json()


def test_testing_status_endpoint_404_when_no_state(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    mock_maintainer_user(is_maintainer=True)
    with patch("openlibrary.fastapi.status.load_testing_status", return_value=None):
        response = fastapi_client.get("/status/testing.json")

    assert response.status_code == 404


def test_testing_status_endpoint_requires_auth(fastapi_client):
    response = fastapi_client.get("/status/testing.json")

    assert response.status_code == 401


def test_testing_status_endpoint_forbidden_for_non_maintainer(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    mock_maintainer_user(is_maintainer=False)
    with patch("openlibrary.fastapi.status.load_testing_status") as mock:
        response = fastapi_client.get("/status/testing.json")

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"
    mock.assert_not_called()
