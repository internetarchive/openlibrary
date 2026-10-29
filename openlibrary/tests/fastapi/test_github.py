"""Tests for the GitHub PR client (openlibrary.plugins.openlibrary.github)."""

from unittest.mock import patch

import pytest

import openlibrary.plugins.openlibrary.github as github_module
import openlibrary.plugins.openlibrary.status as status_module

_HEAD_SHA = "abc1234def5678901234567890123456789012345"


def _make_pr(pr_number=13269):
    return status_module.TestingPR(
        pr=pr_number,
        commit="1d23364b8c652d6107e2dc685f918551fda5d327",
        active=True,
        title="Test PR",
        added_at="2026-08-06T15:00:00+00:00",
        added_by="openlibrary",
        author="author",
        assignee="assignee",
    )


def _graphql_pr(pr_number: int, head_sha: str = _HEAD_SHA, state: str = "OPEN", draft: bool = False, commits: list[str] | None = None) -> dict:
    return {
        "title": f"Test PR {pr_number}",
        "state": state,
        "isDraft": draft,
        "mergedAt": "2026-08-01T00:00:00Z" if state == "MERGED" else None,
        "headRefOid": head_sha,
        "author": {"login": "author", "avatarUrl": "https://example.com/author.png"},
        "assignees": {"nodes": [{"login": "assignee", "avatarUrl": "https://example.com/assignee.png"}]},
        "commits": {"nodes": [{"commit": {"oid": oid}} for oid in (commits or [head_sha])]},
    }


def test_pr_drift_distinguishes_closed_from_merged():
    """Merging closes a PR too; only a close without a merge counts as closed."""

    assert github_module.parse_pr_drift(_make_pr(), _graphql_pr(13269, state="CLOSED"))["closed"] is True
    info = github_module.parse_pr_drift(_make_pr(), _graphql_pr(13269, state="MERGED"))
    assert info["closed"] is False
    assert info["merged"] is True


@pytest.mark.asyncio
async def test_get_pr_info_raises_not_found_when_github_reports_no_such_pr():
    """A null GraphQL node is a missing PR, not an outage."""
    with (
        patch("openlibrary.plugins.openlibrary.github.has_github_token", return_value=True),
        patch("openlibrary.plugins.openlibrary.github.github_graphql", return_value={"repository": {"pr_12914": None}}),
        pytest.raises(github_module.PRNotFoundError),
    ):
        await github_module.get_pr_info(12914)


@pytest.mark.asyncio
async def test_get_pr_info_raises_unavailable_when_github_cannot_answer():
    """A GraphQL failure stays distinguishable from a missing PR."""
    with (
        patch("openlibrary.plugins.openlibrary.github.has_github_token", return_value=True),
        patch("openlibrary.plugins.openlibrary.github.github_graphql", side_effect=github_module.GitHubUnavailableError("rate limited")),
        pytest.raises(github_module.GitHubUnavailableError),
    ):
        await github_module.get_pr_info(12914)


@pytest.mark.asyncio
async def test_get_pr_info_raises_unavailable_on_bad_graphql_body():
    """A malformed GraphQL PR node is an outage, not an absence."""
    with (
        patch("openlibrary.plugins.openlibrary.github.has_github_token", return_value=True),
        patch("openlibrary.plugins.openlibrary.github.github_graphql", return_value={"repository": {"pr_12914": {"title": "no headRefOid"}}}),
        pytest.raises(github_module.GitHubUnavailableError),
    ):
        await github_module.get_pr_info(12914)


@pytest.mark.asyncio
async def test_get_pr_info_returns_only_valid_data_on_success():
    """GraphQL fields map to the existing metadata DTO, including draft."""
    body = _graphql_pr(12914, draft=True)
    body["assignees"] = {"nodes": []}
    with (
        patch("openlibrary.plugins.openlibrary.github.has_github_token", return_value=True),
        patch("openlibrary.plugins.openlibrary.github.github_graphql", return_value={"repository": {"pr_12914": body}}),
    ):
        info = await github_module.get_pr_info(12914)

    assert info == github_module.GitHubPRInfo(
        pr=12914,
        title="Test PR 12914",
        head_sha="abc1234def5678901234567890123456789012345",
        author="author",
        author_avatar="https://example.com/author.png",
        draft=True,
    )


@pytest.mark.asyncio
async def test_get_pr_info_falls_back_when_the_title_is_empty():
    """GitHub always sends a title, but an empty one shouldn't render a blank row."""
    body = _graphql_pr(12914)
    body["title"] = ""
    body["author"] = None
    with (
        patch("openlibrary.plugins.openlibrary.github.has_github_token", return_value=True),
        patch("openlibrary.plugins.openlibrary.github.github_graphql", return_value={"repository": {"pr_12914": body}}),
    ):
        info = await github_module.get_pr_info(12914)

    assert info.title == "PR #12914"
