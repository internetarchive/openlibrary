"""Tests for the testing-environment status API and its underlying helper."""

import asyncio
import datetime
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.sse import ServerSentEvent

import openlibrary.fastapi.status as fastapi_status
import openlibrary.plugins.openlibrary.jenkins as jenkins_module
import openlibrary.plugins.openlibrary.status as status_module
from openlibrary.fastapi.status import _current_status, _stream_events


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


def _empty_state():
    """A state with no PRs and no deploy — what the add endpoint starts from.

    ``_make_state(prs=[])`` can't express this: it reads the empty list as
    "not passed" and builds a default PR.
    """
    return status_module.TestingState(last_deploy_at="", prs=[])


def _gh_info(pr_number: int = 12914, draft: bool = False) -> status_module.GitHubPRInfo:
    """A successful GitHub PR lookup result."""
    return status_module.GitHubPRInfo(
        pr=pr_number,
        title=f"Test PR {pr_number}",
        head_sha="abc1234def5678901234567890123456789012345",
        author="author",
        assignee="assignee",
        draft=draft,
    )


_HEAD_SHA = "abc1234def5678901234567890123456789012345"


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


async def _gh_lookup(pr_number: int) -> status_module.GitHubPRInfo:
    """Stand-in for ``get_pr_info``: describes the PR it was asked about."""
    return _gh_info(pr_number)


def _post_add(client, state, pr_value="12914", gh=None):
    """POST /status/add with the state file and GitHub lookups stubbed out.

    ``gh`` is either a ``GitHubPRInfo`` (the lookup returns it for every number)
    or an exception instance (the lookup raises it); None means a lookup that
    returns the right info for whichever PR number was requested.
    """
    if isinstance(gh, BaseException):
        get_pr_info = patch(
            "openlibrary.plugins.openlibrary.status.get_pr_info",
            new_callable=AsyncMock,
            side_effect=gh,
        )
    elif gh is None:
        get_pr_info = patch(
            "openlibrary.plugins.openlibrary.status.get_pr_info",
            side_effect=_gh_lookup,
        )
    else:
        get_pr_info = patch(
            "openlibrary.plugins.openlibrary.status.get_pr_info",
            new_callable=AsyncMock,
            return_value=gh,
        )
    with (
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        get_pr_info,
        patch("openlibrary.plugins.openlibrary.status._save_testing_state"),
    ):
        if isinstance(pr_value, list):
            prs = pr_value
        else:
            try:
                prs = [int(pr_value)]
            except ValueError:
                prs = []
        return client.post("/status/add", json={"prs": prs})


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
async def test_get_drift_info_fetches_all_prs_in_one_graphql_request():
    """One GraphQL request covers every tracked PR."""
    state = _make_state(prs=[_make_pr(pr_number=n) for n in (13269, 13238, 13240)])
    calls = []

    async def fake_graphql(query):
        calls.append(query)
        return {"repository": {f"pr_{p.pr}": _graphql_pr(p.pr, head_sha=p.commit, commits=[p.commit]) for p in state.prs}}

    with (
        patch("openlibrary.plugins.openlibrary.status.has_github_token", return_value=True),
        patch("openlibrary.plugins.openlibrary.github.github_graphql", side_effect=fake_graphql),
    ):
        drift = await status_module._get_drift_info(state)

    assert len(calls) == 1
    assert all(f"pr_{p.pr}: pullRequest(number: {p.pr})" in calls[0] for p in state.prs)
    assert "isDraft" in calls[0]
    assert drift == {p.pr: {"head_sha": p.commit[:7], "drift": 0, "merged": False, "closed": False} for p in state.prs}


@pytest.mark.asyncio
async def test_get_drift_info_falls_back_to_rest_without_token():
    """Without a token the REST API is used, not GraphQL."""
    state = _make_state(prs=[_make_pr(pr_number=n) for n in (13269, 13238)])
    calls = []

    async def fake_rest_drift(pr):
        calls.append(pr.pr)
        return {
            "head_sha": pr.commit[:7],
            "drift": 0,
            "merged": False,
            "closed": False,
            "title": "Test PR",
            "author": "author",
            "author_avatar": "",
            "assignee": "",
            "assignee_avatar": "",
            "draft": False,
        }

    with (
        patch("openlibrary.plugins.openlibrary.status.has_github_token", return_value=False),
        patch("openlibrary.plugins.openlibrary.status.get_pr_drift", side_effect=fake_rest_drift),
    ):
        drift = await status_module._get_drift_info(state)

    assert set(calls) == {13269, 13238}
    assert drift == {p.pr: {"head_sha": p.commit[:7], "drift": 0, "merged": False, "closed": False} for p in state.prs}


@pytest.mark.asyncio
async def test_get_drift_info_refreshes_metadata_in_place_without_writing_the_state_file():
    """The drift read is a read, not a commit — structurally.

    Fresh metadata is refreshed onto the in-memory TestingPRs (callers build
    the panel from those objects), but the state file is never written by the
    read path: the file's metadata is a seed, refreshed in-memory before every
    use, and its only writers are mutation paths. This also keeps the read
    pure, the contract cache.singleflight_cache requires of its compute.
    """
    state = _make_state(prs=[_make_pr(pr_number=13269)])
    state.prs[0].title = "A staler title"

    async def fake_graphql(query):
        return {"repository": {"pr_13269": _graphql_pr(13269, head_sha=state.prs[0].commit, commits=[state.prs[0].commit])}}

    with (
        patch("openlibrary.plugins.openlibrary.status.has_github_token", return_value=True),
        patch("openlibrary.plugins.openlibrary.github.github_graphql", side_effect=fake_graphql),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state") as mock_save,
    ):
        drift = await status_module._get_drift_info(state)

    # The stale seed was refreshed in memory for the caller to build from...
    assert state.prs[0].title == "Test PR 13269"
    assert drift == {13269: {"head_sha": state.prs[0].commit[:7], "drift": 0, "merged": False, "closed": False}}
    # ...but the read never reached the disk.
    mock_save.assert_not_called()


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


def test_load_testing_status_wires_merge_conflicts():
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
        patch("openlibrary.plugins.openlibrary.status._get_drift_info", return_value={}),
        patch("openlibrary.plugins.openlibrary.status.get_dev_merged_status", return_value=dms),
    ):
        result = asyncio.run(status_module.load_testing_status())

    assert result.prs[0].merge_conflict is True


@pytest.mark.asyncio
async def test_load_testing_status_returns_none_without_state():
    with patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=None):
        assert await status_module.load_testing_status() is None


@pytest.mark.asyncio
async def test_load_testing_status_composes_state_and_drift():
    state = _make_state()
    infos = {state.prs[0].pr: {**status_module.unknown_pr_drift(), "head_sha": "abc1234", "drift": 2}}
    with (
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status._fetch_drift_infos", new_callable=AsyncMock, return_value=infos),
    ):
        result = await status_module.load_testing_status()

    assert result.prs[0].drift == 2


@pytest.mark.asyncio
async def test_load_testing_status_rereads_the_file_after_the_drift_fetch():
    """A mutation landing mid-fetch must win: staged flags come from the
    second read, drift from the fetch."""
    old = _make_state(prs=[_make_pr()])
    new = _make_state(prs=[_make_pr()])
    new.prs[0].pending_active = False
    infos = {13269: {**status_module.unknown_pr_drift(), "head_sha": "f" * 40, "drift": 0}}
    with (
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", side_effect=[old, new]),
        patch("openlibrary.plugins.openlibrary.status._fetch_drift_infos", new_callable=AsyncMock, return_value=infos),
    ):
        result = await status_module.load_testing_status()

    assert result is not None
    (row,) = result.prs
    assert row.pending_active is False  # the mid-fetch mutation, not the pre-fetch read
    assert (row.drift, row.head_sha) == (0, "f" * 40)  # ...joined with the fetched drift


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
async def test_deploy_drops_closed_prs():
    """Deploying removes closed (not merged) PRs from the set, like merged ones."""
    pr = _make_pr(added_at="2026-08-01T10:00:00+00:00")
    state = _make_state(prs=[pr])

    with (
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch(
            "openlibrary.plugins.openlibrary.status._get_drift_info",
            return_value={pr.pr: {"head_sha": "", "drift": 0, "merged": False, "closed": True}},
        ),
        patch("openlibrary.plugins.openlibrary.status.trigger_rebuild", return_value="unconfigured"),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state"),
        patch("openlibrary.plugins.openlibrary.status.get_current_user", return_value=None),
    ):
        await status_module.deploy_testing_status()

    assert state.prs == []


@pytest.mark.asyncio
async def test_deploy_drops_staged_removals():
    """Deploying deletes rows whose removal is staged; the rest survive."""
    doomed = _make_pr(added_at="2026-08-01T10:00:00+00:00")
    doomed.pending_remove = True
    survivor = _make_pr(pr_number=13238, added_at="2026-08-01T10:00:00+00:00")
    state = _make_state(prs=[doomed, survivor])

    with (
        patch("openlibrary.plugins.openlibrary.status._is_maintainer", return_value=True),
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status._get_drift_info", return_value={}),
        patch("openlibrary.plugins.openlibrary.status.trigger_rebuild", return_value="unconfigured"),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state"),
        patch("openlibrary.plugins.openlibrary.status.get_current_user", return_value=None),
    ):
        await status_module.deploy_testing_status()

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


def test_remove_stages_a_removal_for_a_live_pr():
    """Removing a deployed PR stages it: the row survives with its pin and toggle."""
    pr = _make_pr(added_at="2026-08-01T10:00:00+00:00")
    pr.pull_latest_sha = "9f8e7d6c5b4a39281706f5e4d3c2b1a098765432"
    state = _make_state(prs=[pr])
    state.deployed = {pr.pr: pr.title}

    with (
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state") as mock_save,
    ):
        result = status_module.remove_testing_prs([13269])

    assert result == {"ok": True, "staged_prs": [13269], "removed_prs": [], "prs": [{"pr": 13269, "pending_active": None, "pending_remove": True}]}
    assert [p.pr for p in state.prs] == [13269]
    assert state.prs[0].pending_remove is True
    assert state.prs[0].pull_latest_sha == "9f8e7d6c5b4a39281706f5e4d3c2b1a098765432"
    mock_save.assert_called_once_with(state)


def test_remove_stages_a_removal_for_a_never_deployed_pr():
    """A PR that never reached the box stages like any other: the row
    survives read-only so undo works the same everywhere."""
    pr = _make_pr()  # added after last deploy
    state = _make_state(prs=[pr])
    state.deployed = {13238: "Other PR"}

    with (
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state"),
    ):
        result = status_module.remove_testing_prs([13269])

    assert result == {"ok": True, "staged_prs": [13269], "removed_prs": [], "prs": [{"pr": 13269, "pending_active": None, "pending_remove": True}]}
    assert [p.pr for p in state.prs] == [13269]
    assert state.prs[0].pending_remove is True


def test_mutation_responses_echo_the_staged_rows():
    """Toggle/remove/restore answers carry the staged flags so the panel can
    confirm from the last queued response instead of refetching."""
    state = _make_state(prs=[_make_pr()])

    with (
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state"),
    ):
        assert status_module.set_prs_active([13269], False) == {
            "ok": True,
            "prs": [{"pr": 13269, "pending_active": False, "pending_remove": False}],
        }
        # Staging back to the live state normalizes away, like the snapshot.
        assert status_module.set_prs_active([13269], True) == {
            "ok": True,
            "prs": [{"pr": 13269, "pending_active": None, "pending_remove": False}],
        }


def test_restore_clears_a_staged_removal():
    pr = _make_pr(added_at="2026-08-01T10:00:00+00:00")
    pr.pending_remove = True
    state = _make_state(prs=[pr])

    with (
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state") as mock_save,
    ):
        response = status_module.restore_prs([13269])

    assert response == {"ok": True, "prs": [{"pr": 13269, "pending_active": None, "pending_remove": False}]}
    assert state.prs[0].pending_remove is False
    mock_save.assert_called_once_with(state)


@pytest.mark.asyncio
async def test_pull_latest_stages_the_new_head_sha():
    pr = _make_pr(added_at="2026-08-01T10:00:00+00:00")
    state = _make_state(prs=[pr])
    info = _gh_info(pr.pr).model_copy(update={"head_sha": "f" * 40})

    with (
        patch("openlibrary.plugins.openlibrary.status._is_maintainer", return_value=True),
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status.get_pr_info", new_callable=AsyncMock, return_value=info),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state") as mock_save,
    ):
        response = await status_module.pull_latest_prs([pr.pr])

    assert response == {"ok": True}
    assert pr.pull_latest_sha == "f" * 40
    mock_save.assert_called_once_with(state)


@pytest.mark.parametrize(
    "error",
    [status_module.PRNotFoundError("gone"), status_module.GitHubUnavailableError("rate limited")],
)
@pytest.mark.asyncio
async def test_pull_latest_skips_a_pr_github_could_not_answer_for(error):
    """A GitHub failure leaves the row alone and still answers ok.

    Regression guard: ``get_pr_info`` used to signal failure with an empty
    ``head_sha`` rather than raising. Now that it raises, this handler has to
    catch it — an uncaught error here would 500 the endpoint, where it has
    always been a silent no-op.
    """
    pr = _make_pr(added_at="2026-08-01T10:00:00+00:00")
    state = _make_state(prs=[pr])

    with (
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status.get_pr_info", new_callable=AsyncMock, side_effect=error),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state"),
    ):
        response = await status_module.pull_latest_prs([pr.pr])

    assert response == {"ok": True}
    assert pr.pull_latest_sha == ""


@pytest.mark.asyncio
async def test_deploy_unconfigured_answers_error_but_advances_state():
    """Local dev (no Jenkins token): state advances so the UI is exercisable,
    but the response says nothing was actually deployed."""
    state = _make_state(prs=[_make_pr(added_at="2026-08-01T10:00:00+00:00")])

    with (
        patch("openlibrary.plugins.openlibrary.status._is_maintainer", return_value=True),
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status._get_drift_info", return_value={}),
        patch("openlibrary.plugins.openlibrary.status.trigger_rebuild", return_value="unconfigured"),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state"),
        patch("openlibrary.plugins.openlibrary.status.get_current_user", return_value=None),
    ):
        response = await status_module.deploy_testing_status()

    assert response == {"ok": False, "error": "deploy_unconfigured"}
    # No build was accepted, so no deploy window starts…
    assert state.deploy_started_at == ""
    # …but the record advances so a dev can exercise the rest of the panel.
    assert state.deployed == {13269: "Test PR"}


def test_from_github_builds_a_row_from_the_lookup():
    """The DTO converts to a persisted row, stamped and credited."""
    pr = status_module.TestingPR.from_github(_gh_info(13269, draft=True), "mecha-kraken")

    assert pr.pr == 13269
    assert pr.commit == "abc1234def5678901234567890123456789012345"
    assert pr.title == "Test PR 13269"
    assert pr.added_by == "mecha-kraken"
    assert pr.author == "author"
    assert pr.assignee == "assignee"
    assert pr.draft is True
    assert pr.active is True
    # Stamped with a real time, not the "" that legacy state files carry.
    assert pr.added_at
    # The staging fields stay at their defaults: a fresh add is not staged.
    assert pr.pending_remove is False
    assert pr.pull_latest_sha == ""


@pytest.mark.asyncio
async def test_deploy_failure_never_persists_staged_changes():
    """A failed Jenkins trigger must not write staged changes to disk.

    Regression: status_deploy used to call _get_drift_info(state) after staging
    changes, and that helper's metadata refresh saved the file — persisting
    pins/toggles before Jenkins accepted the build. The drift read can no
    longer write at all; the only save happens after a successful trigger.
    """
    state = _make_deploy_state()

    with (
        patch("openlibrary.plugins.openlibrary.status._is_maintainer", return_value=True),
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch(
            "openlibrary.plugins.openlibrary.status._get_drift_info",
            return_value={13238: {"head_sha": "", "drift": 0, "merged": False}, 13240: {"head_sha": "", "drift": 0, "merged": False}},
        ) as mock_drift,
        patch("openlibrary.plugins.openlibrary.status.trigger_rebuild", return_value="failed"),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state") as mock_save,
    ):
        response = await status_module.deploy_testing_status()

    assert response == {"ok": False, "error": "deploy_failed"}
    # The drift read is a read, not a commit — structurally: it cannot persist.
    mock_drift.assert_called_once_with(state)
    mock_save.assert_not_called()


@pytest.mark.asyncio
async def test_deploy_success_applies_staged_changes_then_saves_once():
    """A successful trigger lands the staged pins/toggles and saves exactly once."""
    state = _make_deploy_state()
    pinned, toggled = state.prs

    with (
        patch("openlibrary.plugins.openlibrary.status._is_maintainer", return_value=True),
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch(
            "openlibrary.plugins.openlibrary.status._get_drift_info",
            return_value={13238: {"head_sha": "", "drift": 0, "merged": False}, 13240: {"head_sha": "", "drift": 0, "merged": False}},
        ),
        patch("openlibrary.plugins.openlibrary.status.trigger_rebuild", return_value="triggered"),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state") as mock_save,
        patch("openlibrary.plugins.openlibrary.status.get_current_user", return_value=None),
    ):
        response = await status_module.deploy_testing_status()

    assert response == {"ok": True}
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


@pytest.mark.asyncio
async def test_deploy_records_who_clicked_it():
    """A deploy records the OL username of the maintainer who clicked it."""
    state = _make_state(prs=[_make_pr(added_at="2026-08-01T10:00:00+00:00")])
    user = MagicMock()
    user.key = "/people/mecha-kraken"

    with (
        patch("openlibrary.plugins.openlibrary.status._is_maintainer", return_value=True),
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status._get_drift_info", return_value={}),
        patch("openlibrary.plugins.openlibrary.status.trigger_rebuild", return_value="triggered"),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state"),
        patch("openlibrary.plugins.openlibrary.status.get_current_user", return_value=user),
    ):
        await status_module.deploy_testing_status()

    assert state.deployed_by == "mecha-kraken"


def test_build_testing_status_passes_deployed_by():
    """The API response carries the recorded deployer username through."""
    state = _make_state(prs=[_make_pr(added_at="2026-08-01T10:00:00+00:00")])
    state.deployed_by = "mecha-kraken"

    result = status_module.build_testing_status(state, {})

    assert result.deployed_by == "mecha-kraken"


def test_add_appends_pr_and_credits_the_maintainer(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    """A verified PR lands in the set, credited to the authenticated user."""
    mock_maintainer_user(is_maintainer=True)
    state = _empty_state()

    response = _post_add(fastapi_client, state)

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    (pr,) = state.prs
    assert pr.pr == 12914
    assert pr.commit == "abc1234def5678901234567890123456789012345"
    assert pr.title == "Test PR 12914"
    assert pr.author == "author"
    assert pr.assignee == "assignee"
    assert pr.active is True
    # The username comes from the authenticated-user dependency, not from the
    # get_current_user() mock that only guards the maintainer check.
    assert pr.added_by == "testuser"


@pytest.mark.parametrize(
    ("pr_value", "expected"),
    [
        ([12914, 13269], [12914, 13269]),
        ([12914], [12914]),
    ],
)
def test_add_accepts_several_prs_at_once(pr_value, expected, fastapi_client, mock_authenticated_user, mock_maintainer_user):
    """Space-, comma-, and URL-separated input all add every PR they name."""
    mock_maintainer_user(is_maintainer=True)
    state = _empty_state()

    response = _post_add(fastapi_client, state, pr_value=pr_value)

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert [p.pr for p in state.prs] == expected


def test_add_answers_ok_false_when_github_fails(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    """A GitHub failure (rate limit, outage) must not pretend the add landed."""
    mock_maintainer_user(is_maintainer=True)
    state = _empty_state()

    response = _post_add(fastapi_client, state, gh=status_module.GitHubUnavailableError("rate limited"))

    # The error code is what lets the panel keep the add input; failed_prs says
    # which number was rejected and why.
    assert response.status_code == 200
    assert response.json() == {"ok": False, "error": "add_failed", "failed_prs": {"12914": "unavailable"}}
    assert state.prs == []


def test_add_reports_a_missing_pr_as_not_found(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    """A 404 is distinguishable from an outage, so the panel can say "no such PR"."""
    mock_maintainer_user(is_maintainer=True)
    state = _empty_state()

    response = _post_add(fastapi_client, state, gh=status_module.PRNotFoundError("PR #12914 not found"))

    assert response.status_code == 200
    assert response.json() == {"ok": False, "error": "add_failed", "failed_prs": {"12914": "not_found"}}
    assert state.prs == []


def test_add_reports_token_invalid(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    """A 401 from GitHub is its own error code so the panel can say the token is bad."""
    mock_maintainer_user(is_maintainer=True)
    state = _empty_state()

    response = _post_add(fastapi_client, state, gh=status_module.GitHubTokenInvalidError("401"))

    assert response.status_code == 200
    assert response.json() == {"ok": False, "error": "add_failed", "failed_prs": {"12914": "token_invalid"}}
    assert state.prs == []


def test_add_keeps_the_prs_that_succeeded_and_names_the_one_that_failed(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    """Failures are per-PR: one bad number doesn't discard the good ones."""
    mock_maintainer_user(is_maintainer=True)
    state = _empty_state()

    async def lookup(pr_number: int) -> status_module.GitHubPRInfo:
        if pr_number == 9999:
            raise status_module.PRNotFoundError(f"PR #{pr_number} not found")
        return _gh_info(pr_number)

    with (
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status.get_pr_info", side_effect=lookup),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state"),
    ):
        response = fastapi_client.post("/status/add", json={"prs": [12914, 9999]})

    assert response.status_code == 200
    assert response.json() == {"ok": False, "error": "add_failed", "failed_prs": {"9999": "not_found"}}
    # The valid one still landed.
    assert [p.pr for p in state.prs] == [12914]


@pytest.mark.parametrize("prs", [[], [999]])
def test_add_rejects_invalid_pr_numbers(prs, fastapi_client, mock_authenticated_user, mock_maintainer_user):
    mock_maintainer_user(is_maintainer=True)
    state = _empty_state()

    response = fastapi_client.post("/status/add", json={"prs": prs})

    assert response.status_code == 422
    assert state.prs == []


def test_add_cancels_a_staged_removal(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    """Re-adding a PR whose removal is staged is an undo, not a duplicate row."""
    mock_maintainer_user(is_maintainer=True)
    pr = _make_pr(pr_number=13269, added_at="2026-08-01T10:00:00+00:00")
    pr.pending_remove = True
    state = _make_state(prs=[pr])

    with (
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status.get_pr_info", new_callable=AsyncMock) as mock_info,
        patch("openlibrary.plugins.openlibrary.status._save_testing_state"),
    ):
        response = fastapi_client.post("/status/add", json={"prs": [13269]})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert [p.pr for p in state.prs] == [13269]
    assert state.prs[0].pending_remove is False
    # Already in the set: no GitHub fetch, no fresh row.
    mock_info.assert_not_called()


def test_add_persists_the_state(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    mock_maintainer_user(is_maintainer=True)
    state = _empty_state()
    gh_info = _gh_info()

    with (
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status.get_pr_info", new_callable=AsyncMock, return_value=gh_info),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state") as mock_save,
    ):
        response = fastapi_client.post("/status/add", json={"prs": [12914]})

    assert response.status_code == 200
    mock_save.assert_called_once_with(state)


def test_add_requires_auth(fastapi_client):
    response = fastapi_client.post("/status/add", json={"prs": [12914]})

    assert response.status_code == 401


def test_add_forbidden_for_non_maintainer(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    mock_maintainer_user(is_maintainer=False)
    state = _empty_state()

    response = _post_add(fastapi_client, state)

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"
    assert state.prs == []


def _dict_memcache(store: dict) -> MagicMock:
    """A memcache stub backed by ``store``, so get/set/add/delete round-trip like memcached.

    ``add`` fails when the key exists, so exactly one concurrent acquirer
    wins the singleflight lease; ``delete`` really clears the entry, so a
    test using this stub fails if the code under test evicts a cache it
    should have extended.
    """
    mc = MagicMock()
    mc.get.side_effect = store.get
    mc.set.side_effect = lambda key, value, expires=0: store.__setitem__(key, value)

    def _add(key, value, expires=0):
        if key in store:
            return False
        store[key] = value
        return True

    mc.add.side_effect = _add
    mc.delete.side_effect = lambda key: store.pop(key, None)
    return mc


@pytest.fixture(autouse=True)
def fresh_memcache():
    """A fresh in-memory memcache per test.

    Without configured servers the real client is an in-memory mock shared
    across this whole session — one test's singleflight entry would be
    served fresh to the next. Tests that patch ``get_memcache`` explicitly
    override this within their own ``with`` block.
    """
    with patch("openlibrary.core.cache.get_memcache", return_value=_dict_memcache({})):
        yield


def test_testing_status_endpoint(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    mock_maintainer_user(is_maintainer=True)
    state = _make_state()
    result = status_module.build_testing_status(state, {13269: {"head_sha": "abc1234", "drift": 2, "merged": False}})
    with (
        patch("openlibrary.plugins.openlibrary.status.load_testing_status", AsyncMock(return_value=result)) as mock,
        patch("openlibrary.plugins.openlibrary.status.jenkins_deploy_status", AsyncMock(return_value=None)),
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
                "draft": False,
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
        patch("openlibrary.plugins.openlibrary.status.load_testing_status", AsyncMock(return_value=result)),
        patch("openlibrary.plugins.openlibrary.status.jenkins_deploy_status", AsyncMock(return_value=None)),
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
        patch("openlibrary.plugins.openlibrary.status.load_testing_status", AsyncMock(return_value=result)),
        patch("openlibrary.plugins.openlibrary.status.jenkins_deploy_status", AsyncMock(return_value=jenkins)),
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
        patch("openlibrary.plugins.openlibrary.status.load_testing_status", AsyncMock(return_value=result)),
        patch("openlibrary.plugins.openlibrary.status.jenkins_deploy_status", AsyncMock(return_value=jenkins)),
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
        patch("openlibrary.plugins.openlibrary.status.load_testing_status", AsyncMock(return_value=None)),
        patch("openlibrary.plugins.openlibrary.status.jenkins_deploy_status", AsyncMock(return_value=None)),
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
        patch("openlibrary.plugins.openlibrary.status.load_testing_status", side_effect=fake_load),
        patch("openlibrary.plugins.openlibrary.status.jenkins_deploy_status", side_effect=fake_jenkins),
    ):
        response = fastapi_client.get("/status/testing.json")

    assert response.status_code == 200
    assert peak == 2  # sequential awaits would peak at 1


def test_testing_status_endpoint_requires_auth(fastapi_client):
    response = fastapi_client.get("/status/testing.json")

    assert response.status_code == 401


def test_testing_status_endpoint_forbidden_for_non_maintainer(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    mock_maintainer_user(is_maintainer=False)
    with patch("openlibrary.plugins.openlibrary.status.load_testing_status", AsyncMock()) as mock:
        response = fastapi_client.get("/status/testing.json")

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"
    mock.assert_not_called()


def test_remove_prs_endpoint_requires_auth(fastapi_client):
    response = fastapi_client.post("/status/remove")
    assert response.status_code == 401


def test_remove_prs_endpoint_forbidden_for_non_maintainer(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    mock_maintainer_user(is_maintainer=False)
    with patch("openlibrary.fastapi.status.remove_testing_prs") as mock:
        response = fastapi_client.post("/status/remove")

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"
    mock.assert_not_called()


def test_remove_prs_endpoint(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    mock_maintainer_user(is_maintainer=True)
    with patch("openlibrary.fastapi.status.remove_testing_prs") as mock:
        mock.return_value = {"ok": True, "staged_prs": [13269], "removed_prs": []}
        response = fastapi_client.post("/status/remove", json={"prs": [13269]})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "staged_prs": [13269], "removed_prs": []}
    mock.assert_called_once_with([13269])


def test_set_prs_active_endpoint_requires_auth(fastapi_client):
    response = fastapi_client.patch("/status/testing/prs", json={"prs": [13269], "active": True})

    assert response.status_code == 401


@pytest.mark.parametrize("active", [True, False])
def test_set_prs_active_endpoint(fastapi_client, mock_authenticated_user, mock_maintainer_user, active):
    mock_maintainer_user(is_maintainer=True)
    with patch("openlibrary.fastapi.status.set_prs_active", return_value={"ok": True}) as mock:
        response = fastapi_client.patch("/status/testing/prs", json={"prs": [13269], "active": active})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    mock.assert_called_once_with([13269], active)


def test_refresh_status_endpoint_requires_auth(fastapi_client):
    response = fastapi_client.post("/status/refresh", json={})

    assert response.status_code == 401


def test_refresh_status_endpoint(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    """Refresh = invalidate: the next read recomputes from GitHub."""
    mock_maintainer_user(is_maintainer=True)
    with patch("openlibrary.fastapi.status._invalidate_cached_snapshot") as invalidate:
        response = fastapi_client.post("/status/refresh", json={})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    invalidate.assert_called_once_with()


def test_deploy_status_endpoint_requires_auth(fastapi_client):
    response = fastapi_client.post("/status/deploy", json={})

    assert response.status_code == 401


def test_deploy_status_endpoint(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    mock_maintainer_user(is_maintainer=True)
    with patch("openlibrary.fastapi.status.deploy_testing_status", new_callable=AsyncMock, return_value={"ok": True}) as mock:
        response = fastapi_client.post("/status/deploy", json={})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    mock.assert_called_once_with()


def test_pull_latest_endpoint_requires_auth(fastapi_client):
    response = fastapi_client.post("/status/pull-latest", json={"prs": [13269]})

    assert response.status_code == 401


def test_pull_latest_endpoint(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    mock_maintainer_user(is_maintainer=True)
    with patch("openlibrary.fastapi.status.pull_latest_prs", return_value={"ok": True}) as mock:
        response = fastapi_client.post("/status/pull-latest", json={"prs": [13269]})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    mock.assert_called_once_with([13269])


def test_restore_endpoint_requires_auth(fastapi_client):
    response = fastapi_client.post("/status/restore", json={"prs": [13269]})

    assert response.status_code == 401


def test_restore_endpoint(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    mock_maintainer_user(is_maintainer=True)
    with patch("openlibrary.fastapi.status.restore_prs", return_value={"ok": True}) as mock:
        response = fastapi_client.post("/status/restore", json={"prs": [13269]})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    mock.assert_called_once_with([13269])


def test_restore_endpoint_e2e_clears_a_staged_removal(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    """The real function through the real endpoint: unstages and echoes the
    staged rows. Guards the response contract — FastAPI 500s on a shape the
    annotation doesn't allow, after the write already landed."""
    mock_maintainer_user(is_maintainer=True)
    pr = _make_pr(added_at="2026-08-01T10:00:00+00:00")
    pr.pending_remove = True
    state = _make_state(prs=[pr])

    with (
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state") as mock_save,
    ):
        response = fastapi_client.post("/status/restore", json={"prs": [13269]})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "prs": [{"pr": 13269, "pending_active": None, "pending_remove": False}]}
    assert state.prs[0].pending_remove is False
    mock_save.assert_called_once_with(state)


def test_remove_prs_endpoint_accepts_multiple_prs(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    mock_maintainer_user(is_maintainer=True)
    with patch("openlibrary.fastapi.status.remove_testing_prs") as mock:
        mock.return_value = {"ok": True, "staged_prs": [13269, 13270], "removed_prs": []}
        response = fastapi_client.post("/status/remove", json={"prs": [13269, 13270]})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "staged_prs": [13269, 13270], "removed_prs": []}
    mock.assert_called_once_with([13269, 13270])


def test_remove_prs_endpoint_e2e_stages_live_pr(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    mock_maintainer_user(is_maintainer=True)
    pr = _make_pr(added_at="2026-08-01T10:00:00+00:00")
    pr.pull_latest_sha = "9f8e7d6c5b4a39281706f5e4d3c2b1a098765432"
    state = _make_state(prs=[pr])
    state.deployed = {pr.pr: pr.title}

    with (
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state") as mock_save,
    ):
        response = fastapi_client.post("/status/remove", json={"prs": [13269]})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "staged_prs": [13269], "removed_prs": [], "prs": [{"pr": 13269, "pending_active": None, "pending_remove": True}]}
    assert [p.pr for p in state.prs] == [13269]
    assert state.prs[0].pending_remove is True
    assert state.prs[0].pull_latest_sha == "9f8e7d6c5b4a39281706f5e4d3c2b1a098765432"
    mock_save.assert_called_once_with(state)


def test_remove_prs_endpoint_e2e_stages_never_deployed_pr(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    mock_maintainer_user(is_maintainer=True)
    pr = _make_pr()
    state = _make_state(prs=[pr])
    state.deployed = {13238: "Other PR"}

    with (
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=state),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state") as mock_save,
    ):
        response = fastapi_client.post("/status/remove", json={"prs": [13269]})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "staged_prs": [13269], "removed_prs": [], "prs": [{"pr": 13269, "pending_active": None, "pending_remove": True}]}
    assert [p.pr for p in state.prs] == [13269]
    assert state.prs[0].pending_remove is True
    mock_save.assert_called_once_with(state)


# --- SSE stream endpoint --------------------------------------------------------


@pytest.mark.asyncio
async def test_current_status_shares_one_fleet_wide_compute():
    """The port onto cache.singleflight_cache: within the TTL every tab
    on every worker shares one compute; a mutation invalidates it."""
    payload = status_module.build_testing_status(_make_state(), {}).model_dump()
    with (
        patch("openlibrary.fastapi.status.compute_testing_status", new_callable=AsyncMock, return_value=payload) as compute,
        patch("openlibrary.core.cache.get_memcache", return_value=_dict_memcache({})),
    ):
        assert await _current_status() == payload
        assert await _current_status() == payload
        assert compute.await_count == 1  # fresh: the fleet-wide cache served both

        fastapi_status._invalidate_cached_snapshot()  # a mutation landed, somewhere
        assert await _current_status() == payload
        assert compute.await_count == 2  # invalidated despite a fresh TTL


@pytest.mark.asyncio
async def test_status_stream_frames_only_changed_payloads(monkeypatch):
    monkeypatch.setattr("openlibrary.fastapi.status._STREAM_TICK_SECONDS", 0.01)
    first = {"deploying": False, "prs": []}
    changed = {"deploying": True, "prs": []}
    with patch("openlibrary.fastapi.status._current_status", new_callable=AsyncMock, side_effect=[first, first, changed]):
        events = _stream_events()
        assert (await anext(events)).data == first
        # The second tick returned an identical payload — no frame for it, so
        # this anext can only resolve on the third tick's changed payload.
        assert (await anext(events)).data == changed
        await events.aclose()


def test_status_stream_endpoint_serves_the_route_as_event_stream(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    """The route wiring: registered, maintainer-gated, framed as SSE.

    The generator tests bound the stream body directly; this pins the part
    they bypass — route registration, the response class, and the SSE
    framing — which a FastAPI/SSE upgrade would otherwise break silently.
    The stream is bounded to one frame because the TestClient buffers whole
    responses: an infinite stream could never be drained through it.
    """
    mock_maintainer_user(is_maintainer=True)
    payload = {"deploying": False, "prs": []}

    async def one_frame():
        yield ServerSentEvent(data=payload, event="status")

    with patch("openlibrary.fastapi.status._stream_events", return_value=one_frame()), fastapi_client.stream("GET", "/status/testing/stream") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        lines = list(response.iter_lines())
    assert "event: status" in lines
    data_line = next(line for line in lines if line.startswith("data:"))
    assert json.loads(data_line[len("data:") :]) == payload


def test_remove_endpoint_invalidates_the_cached_snapshot(fastapi_client, mock_authenticated_user, mock_maintainer_user):
    """A mutation bumps the snapshot's version key, invalidating it fleet-wide."""
    mock_maintainer_user(is_maintainer=True)
    store: dict = {}
    with (
        patch("openlibrary.plugins.openlibrary.status._load_testing_state", return_value=_make_state()),
        patch("openlibrary.plugins.openlibrary.status._save_testing_state"),
        patch("openlibrary.core.cache.get_memcache", return_value=_dict_memcache(store)),
    ):
        response = fastapi_client.post("/status/remove", json={"prs": [13269]})

    assert response.json()["ok"] is True
    assert store[f"{fastapi_status._SNAPSHOT_KEY}.v"] == 1
