"""Tests for the FastAPI /status/add endpoint (add PRs to the testing set)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import openlibrary.plugins.openlibrary.status as status_module


@pytest.fixture
def mock_maintainer_user(monkeypatch):
    """Patch get_current_user (used by require_maintainer) with a user of configurable role."""

    def create_user(is_maintainer: bool = False, key: str = "/people/openlibrary"):
        user = MagicMock()
        user.is_maintainer.return_value = is_maintainer
        user.key = key
        monkeypatch.setattr("openlibrary.fastapi.auth.get_current_user", lambda: user)
        return user

    return create_user


def _gh_info(pr_number: int = 12914) -> dict:
    return {
        "title": f"Test PR {pr_number}",
        "head_sha": "abc1234def5678901234567890123456789012345",
        "author": "author",
        "author_avatar": "",
        "assignee": "assignee",
        "assignee_avatar": "",
        "error": "",
    }


def _gh_error(error: str = "unavailable") -> dict:
    return {
        "title": "PR #12914",
        "head_sha": "",
        "author": "",
        "author_avatar": "",
        "assignee": "",
        "assignee_avatar": "",
        "error": error,
    }


def _post_add(client, state, pr_value="12914", gh_side_effect=None, gh_info=None, current_user=None):
    """POST /status/add with standardized mocks so tests only override what they need."""
    if gh_side_effect is not None:
        get_pr_info_patch = patch(
            "openlibrary.plugins.openlibrary.status._get_pr_info_async",
            new_callable=AsyncMock,
            side_effect=gh_side_effect,
        )
    else:
        get_pr_info_patch = patch(
            "openlibrary.plugins.openlibrary.status._get_pr_info_async",
            new_callable=AsyncMock,
            return_value=gh_info if gh_info is not None else _gh_info(),
        )
    with (
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        get_pr_info_patch,
        patch("openlibrary.plugins.openlibrary.status._save_testing_state"),
        patch("openlibrary.plugins.openlibrary.status._evict_drift_cache"),
        patch("openlibrary.plugins.openlibrary.status.get_current_user", return_value=current_user),
    ):
        return client.post("/status/add", data={"pr": pr_value})


class TestStatusAdd:
    """Test the FastAPI /status/add endpoint."""

    def test_add_pr_success(self, fastapi_client, mock_authenticated_user, mock_maintainer_user):
        mock_maintainer_user(is_maintainer=True)
        state = status_module.TestingState(last_deploy_at="", prs=[])

        resp = _post_add(fastapi_client, state)

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert [p.pr for p in state.prs] == [12914]
        pr = state.prs[0]
        assert pr.commit == "abc1234def5678901234567890123456789012345"
        assert pr.active is True
        assert pr.title == "Test PR 12914"
        assert pr.author == "author"
        assert pr.assignee == "assignee"
        assert pr.added_by == ""

    def test_add_multiple_prs_space_and_url_separated(self, fastapi_client, mock_authenticated_user, mock_maintainer_user):
        mock_maintainer_user(is_maintainer=True)
        state = status_module.TestingState(last_deploy_at="", prs=[])
        infos = {12914: _gh_info(12914), 13269: _gh_info(13269)}

        resp = _post_add(
            fastapi_client,
            state,
            pr_value="12914 https://github.com/internetarchive/openlibrary/pull/13269",
            gh_side_effect=lambda n: infos[n],
        )

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert [p.pr for p in state.prs] == [12914, 13269]

    def test_add_records_the_acting_user(self, fastapi_client, mock_authenticated_user, mock_maintainer_user):
        mock_maintainer_user(is_maintainer=True)
        state = status_module.TestingState(last_deploy_at="", prs=[])
        user = mock_maintainer_user(is_maintainer=True, key="/people/mecha-kraken")

        resp = _post_add(fastapi_client, state, current_user=user)

        assert resp.status_code == 200
        assert state.prs[0].added_by == "mecha-kraken"

    def test_add_github_failure_answers_ok_false(self, fastapi_client, mock_authenticated_user, mock_maintainer_user):
        """A GitHub failure (rate limit, outage, invalid PR) must not pretend the add landed."""
        mock_maintainer_user(is_maintainer=True)
        state = status_module.TestingState(last_deploy_at="", prs=[])

        resp = _post_add(fastapi_client, state, gh_info=_gh_error())

        assert resp.status_code == 200
        assert resp.json() == {"ok": False, "error": "add_failed"}
        assert state.prs == []

    def test_add_invalid_input_is_400(self, fastapi_client, mock_authenticated_user, mock_maintainer_user):
        mock_maintainer_user(is_maintainer=True)
        state = status_module.TestingState(last_deploy_at="", prs=[])

        for bad in ("", "   ", "not a number"):
            resp = _post_add(fastapi_client, state, pr_value=bad)
            assert resp.status_code == 400
        assert state.prs == []

    def test_add_cancels_a_staged_removal(self, fastapi_client, mock_authenticated_user, mock_maintainer_user):
        """Re-adding a PR whose removal is staged is an undo, not a duplicate row."""
        mock_maintainer_user(is_maintainer=True)
        pr = status_module.TestingPR(
            pr=13269,
            commit="abc1234def5678901234567890123456789012345",
            active=True,
            title="Test PR",
            added_at="2026-08-01T10:00:00+00:00",
            added_by="openlibrary",
            author="author",
            assignee="assignee",
            pending_remove=True,
        )
        state = status_module.TestingState(last_deploy_at="2026-08-05T18:00:00+00:00", prs=[pr])

        with (
            patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
            patch("openlibrary.plugins.openlibrary.status._get_pr_info_async", new_callable=AsyncMock) as mock_info,
            patch("openlibrary.plugins.openlibrary.status._save_testing_state"),
            patch("openlibrary.plugins.openlibrary.status._evict_drift_cache"),
            patch("openlibrary.plugins.openlibrary.status.get_current_user", return_value=None),
        ):
            resp = fastapi_client.post("/status/add", data={"pr": "13269"})

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert [p.pr for p in state.prs] == [13269]
        assert state.prs[0].pending_remove is False
        mock_info.assert_not_called()

    def test_add_saves_state_and_evicts_drift_cache(self, fastapi_client, mock_authenticated_user, mock_maintainer_user):
        mock_maintainer_user(is_maintainer=True)
        state = status_module.TestingState(last_deploy_at="", prs=[])

        with (
            patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
            patch("openlibrary.plugins.openlibrary.status._get_pr_info_async", new_callable=AsyncMock, return_value=_gh_info()),
            patch("openlibrary.plugins.openlibrary.status._save_testing_state") as mock_save,
            patch("openlibrary.plugins.openlibrary.status._evict_drift_cache") as mock_evict,
            patch("openlibrary.plugins.openlibrary.status.get_current_user", return_value=None),
        ):
            resp = fastapi_client.post("/status/add", data={"pr": "12914"})

        assert resp.status_code == 200
        mock_save.assert_called_once_with(state)
        mock_evict.assert_called_once_with()

    def test_add_requires_auth(self, fastapi_client):
        resp = fastapi_client.post("/status/add", data={"pr": "12914"})

        assert resp.status_code == 401

    def test_add_forbidden_for_non_maintainer(self, fastapi_client, mock_authenticated_user, mock_maintainer_user):
        mock_maintainer_user(is_maintainer=False)
        state = status_module.TestingState(last_deploy_at="", prs=[])

        resp = _post_add(fastapi_client, state)

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Insufficient permissions"
        assert state.prs == []
