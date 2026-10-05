"""Client for Open Library's GitHub PR status lookups.

The /status testing panel fetches live PR metadata (title, author, assignee,
draft state) and drift (commits behind HEAD) from GitHub. When a
``github_api_token`` is configured, one GraphQL request fetches every tracked
PR at once; otherwise the REST API is used (one request per PR, tolerating
unauthenticated requests at a lower rate limit).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
from pydantic import BaseModel

from infogami import config
from openlibrary.utils.async_utils import cache_per_event_loop

if TYPE_CHECKING:
    from openlibrary.plugins.openlibrary.status import TestingPR

_GITHUB_API_BASE = "https://api.github.com/repos/internetarchive/openlibrary"
_GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"

# One pooled client per event loop. cache_per_event_loop keeps a separate pool
# per loop, since AsyncBridge's background loop and FastAPI's can't share one.
get_github_client = cache_per_event_loop(lambda: httpx.AsyncClient(timeout=5.0))


class GitHubAPIError(Exception):
    """A GitHub lookup failed. Base for the failure modes callers act on."""


class PRNotFoundError(GitHubAPIError):
    """GitHub answered 404: the PR number doesn't exist, or isn't visible."""


class GitHubUnavailableError(GitHubAPIError):
    """Rate limits, network outages, timeouts, or an unparsable response."""


class GitHubTokenInvalidError(GitHubUnavailableError):
    """The configured ``github_api_token`` was rejected (HTTP 401)."""


class GitHubPRInfo(BaseModel):
    """The PR metadata fetched from GitHub.

    A transport shape, not persisted state: it carries only what GitHub
    reports, so a value here is always real data (``get_pr_info`` raises
    rather than returning placeholders).
    """

    pr: int
    title: str
    head_sha: str
    author: str = ""
    author_avatar: str = ""
    assignee: str = ""
    assignee_avatar: str = ""
    draft: bool = False


def has_github_token() -> bool:
    """Whether a ``github_api_token`` is configured (enabling GraphQL)."""
    return bool(getattr(config, "github_api_token", None))


async def github_get(path: str) -> dict:
    """GET a GitHub API path; raises httpx.HTTPError (network or non-2xx) on failure."""
    url = f"{_GITHUB_API_BASE}/{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "openlibrary-status",
    }
    if token := getattr(config, "github_api_token", None):
        headers["Authorization"] = f"Bearer {token}"
    resp = await get_github_client().get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()


def _build_pr_query(pr_numbers: list[int]) -> str:
    """Build one GraphQL query for the requested pull requests."""
    fields = """
        title state isDraft mergedAt headRefOid
        author { login avatarUrl }
        assignees(first: 1) { nodes { login avatarUrl } }
        commits(last: 100) { nodes { commit { oid } } }
    """
    prs = " ".join(f"pr_{number}: pullRequest(number: {number}) {{ {fields} }}" for number in pr_numbers)
    return f'query GitHubPRStatus {{ repository(owner: "internetarchive", name: "openlibrary") {{ {prs} }} }}'


async def github_graphql(query: str) -> dict:
    """POST a GitHub GraphQL query and return its data payload."""
    headers = {
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "openlibrary-status",
    }
    if token := getattr(config, "github_api_token", None):
        headers["Authorization"] = f"Bearer {token}"
    else:
        raise GitHubUnavailableError("GitHub GraphQL token is not configured")
    try:
        resp = await get_github_client().post(_GITHUB_GRAPHQL_URL, headers=headers, json={"query": query})
        resp.raise_for_status()
        body = resp.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise GitHubTokenInvalidError("GitHub API token was rejected (401)") from e
        raise GitHubUnavailableError(f"GitHub returned {e.response.status_code}") from e
    except (httpx.HTTPError, ValueError) as e:
        raise GitHubUnavailableError("Could not fetch GitHub PR data") from e
    if body.get("errors") and not body.get("data"):
        raise GitHubUnavailableError("GitHub GraphQL query failed")
    if not isinstance(body.get("data"), dict):
        raise GitHubUnavailableError("GitHub GraphQL response had no data")
    return body["data"]


async def fetch_prs_graphql(pr_numbers: list[int]) -> dict[int, dict | None]:
    """Fetch metadata and drift inputs for all requested PRs in one request."""
    if not pr_numbers:
        return {}
    data = await github_graphql(_build_pr_query(pr_numbers))
    repository = data.get("repository")
    if not isinstance(repository, dict):
        raise GitHubUnavailableError("GitHub GraphQL response had no repository")
    return {number: repository.get(f"pr_{number}") for number in pr_numbers}


def parse_pr_info(pr_number: int, pr: dict) -> GitHubPRInfo:
    author = pr.get("author") or {}
    assignees = (pr.get("assignees") or {}).get("nodes") or []
    assignee = assignees[0] if assignees else {}
    return GitHubPRInfo(
        pr=pr_number,
        title=pr.get("title") or f"PR #{pr_number}",
        head_sha=pr["headRefOid"],
        author=author.get("login", ""),
        author_avatar=author.get("avatarUrl", ""),
        assignee=assignee.get("login", ""),
        assignee_avatar=assignee.get("avatarUrl", ""),
        draft=bool(pr.get("isDraft", False)),
    )


def unknown_pr_drift() -> dict:
    return {
        "head_sha": "",
        "drift": -1,
        "merged": False,
        "closed": False,
        "title": "",
        "author": "",
        "author_avatar": "",
        "assignee": "",
        "assignee_avatar": "",
        "draft": None,
    }


def parse_pr_drift(pr: TestingPR, payload: dict | None) -> dict:
    if not payload:
        return unknown_pr_drift()
    try:
        info = parse_pr_info(pr.pr, payload)
        stored = pr.commit.strip()
        if info.head_sha == stored or (len(stored) < 40 and info.head_sha.startswith(stored)):
            drift = 0
        else:
            commits = (payload.get("commits") or {}).get("nodes") or []
            oids = [node.get("commit", {}).get("oid", "") for node in commits]
            index = next((i for i, oid in enumerate(oids) if oid == stored or (len(stored) < 40 and oid.startswith(stored))), None)
            drift = len(oids) - index - 1 if index is not None else -1
        merged = bool(payload.get("mergedAt"))
        return {
            "head_sha": info.head_sha[:7],
            "drift": drift,
            "merged": merged,
            "closed": payload.get("state") == "CLOSED" and not merged,
            "title": info.title,
            "author": info.author,
            "author_avatar": info.author_avatar,
            "assignee": info.assignee,
            "assignee_avatar": info.assignee_avatar,
            "draft": info.draft,
        }
    except AttributeError, KeyError, TypeError, ValueError:
        return unknown_pr_drift()


async def get_pr_info(pr_number: int) -> GitHubPRInfo:
    """Fetch title, HEAD SHA, author, and assignee for a PR from GitHub.

    Raises ``PRNotFoundError`` on a 404 and ``GitHubUnavailableError`` for rate
    limits, network failures, or an unparsable body — so callers can tell a bad
    PR number from a GitHub outage, and a returned value is always real data.
    """
    if has_github_token():
        try:
            payload = (await fetch_prs_graphql([pr_number]))[pr_number]
            if payload is None:
                raise PRNotFoundError(f"PR #{pr_number} not found")
            return parse_pr_info(pr_number, payload)
        except PRNotFoundError:
            raise
        except (AttributeError, KeyError, TypeError, ValueError) as e:
            raise GitHubUnavailableError(f"Could not fetch PR #{pr_number}") from e
    try:
        pr = await github_get(f"pulls/{pr_number}")
        user = pr.get("user") or {}
        assignee = pr.get("assignee") or {}
        return GitHubPRInfo(
            pr=pr_number,
            title=pr.get("title") or f"PR #{pr_number}",
            head_sha=pr["head"]["sha"],
            author=user.get("login", ""),
            author_avatar=user.get("avatar_url", ""),
            assignee=assignee.get("login", ""),
            assignee_avatar=assignee.get("avatar_url", ""),
            draft=bool(pr.get("draft", False)),
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise PRNotFoundError(f"PR #{pr_number} not found") from e
        raise GitHubUnavailableError(f"GitHub returned {e.response.status_code} for PR #{pr_number}") from e
    except (httpx.HTTPError, KeyError, ValueError) as e:
        raise GitHubUnavailableError(f"Could not fetch PR #{pr_number}") from e


async def get_pr_drift(pr: TestingPR) -> dict:
    """Fetch live drift info + metadata for a PR from GitHub.

    Returns head_sha, drift, merged plus title/author/assignee so callers can
    refresh state without a second API call.
    """
    try:
        gh = await github_get(f"pulls/{pr.pr}")
        head_sha = gh["head"]["sha"]
        merged = bool(gh.get("merged") or gh.get("merged_at"))
        stored = pr.commit.strip()
        if head_sha == stored or (len(stored) < 40 and head_sha.startswith(stored)):
            drift = 0
        else:
            try:
                cmp = await github_get(f"compare/{stored}...{head_sha}")
                drift = cmp.get("ahead_by", -1)
            except httpx.HTTPError, ValueError:
                drift = -1
        user = gh.get("user") or {}
        assignee = gh.get("assignee") or {}
        return {
            "head_sha": head_sha[:7],
            "drift": drift,
            "merged": merged,
            "closed": gh.get("state") == "closed" and not merged,
            "title": gh.get("title", f"PR #{pr.pr}"),
            "author": user.get("login", ""),
            "author_avatar": user.get("avatar_url", ""),
            "assignee": assignee.get("login", ""),
            "assignee_avatar": assignee.get("avatar_url", ""),
            "draft": bool(gh.get("draft", False)),
        }
    except httpx.HTTPError, KeyError, ValueError:
        return {
            "head_sha": "",
            "drift": -1,
            "merged": False,
            "closed": False,
            "title": "",
            "author": "",
            "author_avatar": "",
            "assignee": "",
            "assignee_avatar": "",
            "draft": None,
        }
