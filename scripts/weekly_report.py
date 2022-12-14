"""
Write a weekly report of:
- Milestone progress by teammate
- Number of untriaged GitHub issues by teammate
- Number of unprioritized GitHub issues by teammate
- List of GitHub issues that do not have a lead assigned
- List of GitHub issues with labels "Priority: 0" and  "Priority: 1"

Gathering data from GitHub requires a GitHub token which should be passed in via
the GITHUB_TOKEN environment variable.  The data is rate limited so please see
https://docs.github.com/en/rest/overview/resources-in-the-rest-api#rate-limiting
if exceptions are raised.
"""

import os
import pickle
from collections.abc import Iterator
from datetime import date
from logging import getLogger

import github  # pip install PyGithub

logger = getLogger(__file__)
team: dict[str, str] = {
    "cclauss": "Christian Clauss",
    "cdrini": "Drini Cami",
    "hornc": "Charles Horn",
    "jimchamp": "Jim Champ",
    "mekarpeles": "Mek",
}


def get_open_issues(
    filename: str = f"open_issues_{date.today().isoformat()}.pickle",
) -> list[github.Issue]:
    """
    Get open issues from GitHub repository internetarchive/openlibrary.

    Gathering data from GitHub requires a GitHub token which should be passed in via
    the GITHUB_TOKEN environment variable.  The data is rate limited so please see
    https://docs.github.com/en/rest/overview/resources-in-the-rest-api#rate-limiting
    if exceptions are raised.

    If there is a local file of today's open issues, it will be used instead of
    querying GitHub.  To force a new query, delete today's local file.
    """
    if os.path.exists(filename):
        with open(filename, "rb") as in_file:
            return pickle.load(in_file)

    try:
        gh = github.Github(os.getenv("GITHUB_TOKEN"))
    except github.BadCredentialsException as e:
        logger.exception(
            "Bad credentials. Please check the GITHUB_TOKEN environment variable."
        )
        exit(1)
    except github.GithubException as e:
        logger.exception("Error connecting to GitHub. Please try again later.")
        exit(1)

    try:
        repo = gh.get_repo("internetarchive/openlibrary")
        # We want to get all open issues but not pull requests -- takes a few seconds
        open_issues = [x for x in repo.get_issues(state='open')]
        # if x.pull_request is None]  # Eliminating pull requests exceeds rate limit
        with open(filename, "wb") as out_file:
            pickle.dump(open_issues, out_file)
        print(f"Found {len(open_issues)} open issues plus pull requests.")
    except github.RateLimitExceededException as e:
        logger.exception("Rate limit exceeded. Please wait 60 minutes and try again.")
        exit(1)
    return open_issues


def issue_has_label(issue: github.Issue, label_name: str) -> bool:
    """Return True if the issue has a label with the given name."""
    return any(label.name == label_name for label in issue.labels)


def issue_has_label_startswith(issue: github.Issue, label_prefix: str) -> bool:
    """Return True if the issue has a label that starts with the given prefix."""
    return any(label.name.startswith(label_prefix) for label in issue.labels)


def get_milestone_progress():
    """Get the progress of each milestone by teammate."""


def get_untriaged_issues(issues: list[github.Issue]) -> Iterator[int]:
    """Get the number of untriaged issues by teammate."""
    yield from (i.number for i in issues if issue_has_label(i, "Needs: triage"))
    yield from (
        i.number for i in issues if not issue_has_label_startswith(i, "Needs: ")
    )


def get_unassigned_issues(issues: list[github.Issue]) -> Iterator[int]:
    """Get the number of unassigned issues."""
    yield from (issue.number for issue in issues if not issue.assignee)


def get_priority_issues(priority: int, issues: list[github.Issue]) -> Iterator[int]:
    """Get the number of issues with a Priority label."""
    assert priority in range(4)
    label_name = f"Priority: {priority}"
    yield from (i.number for i in issues if issue_has_label(i, label_name))


def get_unprioritized_issues(issues: list[github.Issue]) -> Iterator[int]:
    """Get the number of unprioritized issues by teammate."""
    yield from (
        i.number for i in issues if not issue_has_label_startswith(i, "Priority: ")
    )


def main():
    open_issues = get_open_issues()
    team_issues = [
        [i for i in open_issues if i.assignee and i.assignee.login == github_id]
        for github_id in team
    ]

    for (github_id, name), issues in zip(team.items(), team_issues):
        print(f"{name} ({github_id}): {len(issues)} issues")
        for priority in range(2):
            print("\tPriority", priority, list(get_priority_issues(priority, issues)))
        print("\tUntriaged", list(get_untriaged_issues(issues)))
    print(f"\nTeam total: {len(open_issues)} issues")
    print("Unassigned", list(get_unassigned_issues(open_issues)))
    print("Unprioritized", list(get_unprioritized_issues(open_issues)))
    print("Untriaged", list(get_untriaged_issues(open_issues)))
    for priority in range(2):
        print("Priority", priority, list(get_priority_issues(priority, open_issues)))


if __name__ == "__main__":
    main()
