"""/tasks/admin on FastAPI: who gets in, and what the list and a project's page show."""

from dataclasses import replace
from datetime import UTC, datetime
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from openlibrary.contribute import initiatives, manage
from openlibrary.core.shell.user import ShellUser
from openlibrary.fastapi import tasks

MOST_READ, TAGS = initiatives.MOST_READ, initiatives.TAGS
# Two books on the list: one with a cover still missing, one where nobody could find the publisher.
GAPS = [["/books/OL1M", 9, ["covers"], []], ["/books/OL2M", 8, [], ["publishers"]]]
DOCS = [
    {"_key": "counts-2026-11-09", "initiatives": {MOST_READ.slug: {"open": 9, "people": 4}}, "tasks_saves_by_initiative_1d": {MOST_READ.slug: 3}},
    {
        "_key": "counts-2026-11-10",
        "initiatives": {MOST_READ.slug: {"open": 5, "people": 6}},
        "tasks_saves_by_initiative_1d": {MOST_READ.slug: 12},
        "tasks_saves_by_initiative_28d": {MOST_READ.slug: {"saves": 40, "undone": 2}},
    },
]
LOG = [
    {"at": "2026-11-09T10:00:00+00:00", "by": "/people/mek", "action": "hide", "changes": {"hidden": True}},
    {"at": "2026-11-10T12:30:00+00:00", "by": "/people/lokesh", "action": "edit", "changes": {"title": "X", "ends_at": None}},
]
DRAFT = {"slug": "winter-covers", "title": "Winter <Covers>", "description": "Covers.", "fields": ["covers"], "size": 40}


def shell_user(is_super_librarian: bool) -> ShellUser:
    return ShellUser(key="/people/u", created=None, ia_id=None, is_librarian=True, is_super_librarian=is_super_librarian, open_merges_count=0)


@pytest.fixture
def client(site_page_app, monkeypatch):
    """The pages as a super-librarian sees them, unless the request names another role in ``x-role``."""
    roles = {"visitor": None, "librarian": shell_user(False), "": shell_user(True)}
    monkeypatch.setattr("openlibrary.fastapi.shared.site_page.load_shell_user", lambda: roles[role["now"]])
    monkeypatch.setattr(initiatives, "get_gaps", lambda initiative: GAPS if initiative.slug == MOST_READ.slug else None)
    monkeypatch.setattr(initiatives, "started_at", lambda initiative, site: None)
    monkeypatch.setattr(manage.admin, "get_count_docs", lambda ndays: DOCS)
    monkeypatch.setattr(initiatives, "cached_definitions", lambda: [DRAFT])
    monkeypatch.setattr(initiatives, "read_definitions", lambda site: [DRAFT])
    monkeypatch.setattr(initiatives, "definition_doc", lambda site, slug: {"_rev": "7", "log": LOG} if slug == MOST_READ.slug else {})
    role = {"now": ""}
    test_client = TestClient(site_page_app(tasks.pages), follow_redirects=False)
    test_client.as_role = lambda name: role.update(now=name)  # type: ignore[attr-defined]
    return test_client


@pytest.mark.parametrize("path", ["/tasks/admin", f"/tasks/admin/{MOST_READ.slug}"])
def test_only_super_librarians_and_admins_get_in(client, path):
    client.as_role("visitor")
    response = client.get(path)
    assert (response.status_code, response.headers["location"]) == (303, f"/account/login?redirect={path}")
    client.as_role("librarian")
    assert client.get(path).status_code == 403
    client.as_role("")
    assert client.get(path).status_code == 200


def test_the_list_shows_every_project_whatever_its_status(client):
    html = client.get("/tasks/admin").text
    assert "<title>Community projects | Open Library</title>" in html
    for slug in (MOST_READ.slug, TAGS.slug, "winter-covers"):
        assert f'href="/tasks/admin/{slug}"' in html
    # Live ones first, the draft last, and its name escaped.
    assert html.index(TAGS.slug) < html.index("winter-covers")
    assert "Winter &lt;Covers&gt;" in html
    assert 'data-status="draft"' in html
    assert "Getting the list ready" in html  # the one whose gaps aren't built


def test_summary_figures_come_from_the_gaps_and_the_latest_count(client):
    summary = manage.build_summary(MOST_READ, DOCS)
    assert (summary["status"], summary["featured"], summary["building"]) == ("live", True, False)
    assert (summary["books"], summary["tasks_left"], summary["people"]) == ("2", "1", "6")
    draft = manage.build_summary(initiatives.every()[-1], DOCS)
    assert (draft["status"], draft["books"], draft["progress"], draft["building"]) == ("draft", "40", None, False)


def test_a_draft_is_never_asked_for_its_gaps(monkeypatch):
    monkeypatch.setattr(initiatives, "get_gaps", lambda initiative: pytest.fail("asking would pick the list early"))
    monkeypatch.setattr(initiatives, "cached_definitions", lambda: [DRAFT])
    assert manage.build_summary(initiatives.every()[-1], [])["tasks_left"] == manage.BLANK


def test_a_project_page_breaks_progress_down_by_detail(client):
    rows = {r["label"]: r for r in manage.build_field_rows(MOST_READ, GAPS)}
    assert rows["Cover"] == {"label": "Cover", "open": "1", "not_found": "0", "filled": "1", "percent": 50}
    assert rows["Publisher"] == {"label": "Publisher", "open": "0", "not_found": "1", "filled": "1", "percent": 100}
    html = client.get(f"/tasks/admin/{MOST_READ.slug}").text
    assert "40 saves, 2 since undone (5%)" in html
    assert "From 9 to 5 over 2 days" in html
    assert f'href="/tasks?initiative={MOST_READ.slug}"' in html


def test_a_draft_has_no_public_link_and_no_progress(client):
    html = client.get("/tasks/admin/winter-covers").text
    assert "Progress is counted once the project starts." in html
    assert "View on Tasks" not in html
    assert "No saves counted yet." in html


def test_an_unknown_project_is_a_404(client):
    assert client.get("/tasks/admin/nope").status_code == 404


def test_a_trend_needs_two_counts_and_skips_days_without_one():
    assert manage.sparkline_points([None, 4, None]) == ""
    assert manage.sparkline_points([10, None, 0]) == "0.0,2.0 100.0,30.0"
    assert manage.sparkline_points([5, 5]) == "0.0,2.0 100.0,2.0"


def test_concurrent_requests_each_get_only_their_own_project(site_page_app, client, webpy_leftovers, fetch_concurrently):
    slugs = [MOST_READ.slug, TAGS.slug, "winter-covers"] * 4
    responses = fetch_concurrently(site_page_app(tasks.pages), [(f"/tasks/admin/{slug}", {}) for slug in slugs])
    for slug, response in zip(slugs, responses):
        assert response.status_code == 200
        assert webpy_leftovers not in response.text
        assert f"<code>{slug}</code>" in response.text


@pytest.fixture
def changes(monkeypatch):
    """Every write the routes ask for, in order, in place of the store."""
    made = []
    monkeypatch.setattr(initiatives, "change", lambda site, slug, changes, by, action, rev: made.append((slug, action, changes, by, rev)))
    monkeypatch.setattr(initiatives, "set_headline", lambda site, slug, by, rev: made.append((slug, "headline", {}, by, rev)))
    return made


def flash(response) -> str:
    return unquote(response.cookies["flash"])


@pytest.mark.parametrize("action", ["hide", "unhide", "stop", "headline", "edit"])
def test_only_super_librarians_and_admins_can_change_a_project(client, changes, action):
    path = f"/tasks/admin/{MOST_READ.slug}/{action}"
    client.as_role("visitor")
    assert client.post(path, data={"rev": "7"}).status_code == 303
    client.as_role("librarian")
    assert client.post(path, data={"rev": "7"}).status_code == 403
    assert changes == []


def test_the_project_page_offers_the_actions_that_apply_and_shows_its_history(client):
    html = client.get(f"/tasks/admin/{MOST_READ.slug}").text
    assert f'action="/tasks/admin/{MOST_READ.slug}/hide"' in html
    assert f'action="/tasks/admin/{MOST_READ.slug}/stop"' in html
    # It is the headline already, and it isn't hidden.
    assert "/headline" not in html
    assert "/unhide" not in html
    assert html.count('name="rev" value="7"') == 3
    assert html.index("Edited: title, end date") < html.index("Hid the project")
    assert 'href="/people/lokesh"' in html
    assert "2026-11-10 12:30 UTC" in html
    draft = client.get("/tasks/admin/winter-covers").text
    assert "/stop" not in draft
    assert "/headline" not in draft
    assert "No changes have been made here yet." in draft


def test_hide_and_unhide_write_the_flag_against_the_revision_the_page_showed(client, changes):
    response = client.post(f"/tasks/admin/{MOST_READ.slug}/hide", data={"rev": "7"})
    assert (response.status_code, response.headers["location"]) == (303, f"/tasks/admin/{MOST_READ.slug}")
    client.post(f"/tasks/admin/{MOST_READ.slug}/unhide", data={"rev": "8"})
    assert changes == [
        (MOST_READ.slug, "hide", {"hidden": True}, "/people/u", "7"),
        (MOST_READ.slug, "unhide", {"hidden": False}, "/people/u", "8"),
    ]


def test_stopping_ends_a_live_project_now_and_refuses_any_other(client, changes):
    client.post(f"/tasks/admin/{MOST_READ.slug}/stop", data={"rev": "7"})
    [(slug, action, change, _by, _rev)] = changes
    assert (slug, action) == (MOST_READ.slug, "stop")
    assert initiatives.parse_time(change["ends_at"]) <= datetime.now(UTC)
    response = client.post("/tasks/admin/winter-covers/stop", data={"rev": ""})
    assert "Only a live project can be stopped." in flash(response)
    assert len(changes) == 1


def test_only_a_live_visible_project_can_become_the_headline(client, changes):
    client.post(f"/tasks/admin/{TAGS.slug}/headline", data={"rev": ""})
    assert changes == [(TAGS.slug, "headline", {}, "/people/u", "")]
    assert "isn't hidden" in flash(client.post("/tasks/admin/winter-covers/headline", data={"rev": ""}))
    assert len(changes) == 1


def test_a_change_against_a_stale_page_is_refused_with_a_message(client, monkeypatch):
    def conflict(*args):
        raise initiatives.Conflict

    monkeypatch.setattr(initiatives, "change", conflict)
    response = client.post(f"/tasks/admin/{MOST_READ.slug}/hide", data={"rev": "1"})
    assert response.status_code == 303
    assert "Someone else changed this project" in flash(response)


def test_an_unknown_project_cannot_be_changed(client, changes):
    assert client.post("/tasks/admin/nope/hide", data={"rev": ""}).status_code == 404
    assert changes == []


def test_editing_saves_only_what_differs(client, changes):
    form = {"rev": "", "title": " Winter <Covers> ", "description": "Covers.", "starts": "2026-12-01", "ends": "2026-12-31"}
    client.post("/tasks/admin/winter-covers/edit", data=form)
    # The title and description are as they were; the end date is stored as the midnight after its last day.
    assert changes == [("winter-covers", "edit", {"starts_at": "2026-12-01T00:00:00+00:00", "ends_at": "2027-01-01T00:00:00+00:00"}, "/people/u", "")]
    assert "Nothing changed." in flash(client.post("/tasks/admin/winter-covers/edit", data=form | {"starts": "", "ends": ""}))
    assert len(changes) == 1


@pytest.mark.parametrize(
    ("form", "error"),
    [
        ({"title": ""}, "A project needs a title."),
        ({"title": "x" * 81}, "too long"),
        ({"title": "T", "ends": "2026-12-31"}, "needs a start date"),
        ({"title": "T", "starts": "2026-12-31", "ends": "2026-12-01"}, "before the start date"),
        ({"title": "T", "starts": "soon"}, "isn't one we can read"),
    ],
)
def test_a_bad_edit_is_refused_with_its_reason(client, changes, form, error):
    assert error in flash(client.post("/tasks/admin/winter-covers/edit", data=form))
    assert changes == []


def test_a_built_in_project_may_blank_its_title_to_keep_its_translated_name():
    renamed = replace(MOST_READ, title="Gaps!", description="Fill them.")
    assert manage.parse_edit(renamed, "", "ignored without a title", "2026-11-01", "") == ({"title": "", "description": ""}, "")
    assert manage.parse_edit(MOST_READ, "", "", "2026-11-01", "") == ({}, "")


def test_saving_the_form_again_does_not_restart_a_project_stopped_today():
    stopped = replace(MOST_READ, ends_at=datetime(2026, 11, 11, 14, 0, tzinfo=UTC))
    assert manage.build_controls(stopped, "ended", {})["form"]["ends"] == "2026-11-11"
    assert manage.parse_edit(stopped, "", "", "2026-11-01", "2026-11-11") == ({}, "")
    assert manage.parse_edit(stopped, "", "", "2026-11-01", "2026-11-12")[0] == {"ends_at": "2026-11-13T00:00:00+00:00"}
