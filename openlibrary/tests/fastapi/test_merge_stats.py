"""The stats page's access, inputs, links and per-request isolation."""

import datetime as dt
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from openlibrary.core.edits import CommunityEditsQueue
from openlibrary.core.shell.user import ShellUser
from openlibrary.fastapi.merge_stats import pages

ROWS = [{"username": "alice", "total": 4, "merged": 3, "declined": 1, "merge_rate": 75.0, "author_requests": 1, "work_requests": 3}]


@pytest.fixture
def stats_queries(monkeypatch):
    get_stats = AsyncMock(return_value=ROWS)
    get_count = AsyncMock(return_value=51)
    monkeypatch.setattr(CommunityEditsQueue, "get_stats", get_stats)
    monkeypatch.setattr(CommunityEditsQueue, "get_stats_count", get_count)
    return get_stats, get_count


def shell_user(is_librarian: bool) -> ShellUser:
    return ShellUser(key="/people/u", created=None, ia_id=None, is_librarian=is_librarian, is_super_librarian=False, open_merges_count=0)


@pytest.fixture
def client(site_page_app, stats_queries, monkeypatch):
    """The page as a librarian sees it, unless the test calls ``as_role`` with another role."""
    roles = {"visitor": None, "member": shell_user(False), "librarian": shell_user(True)}
    role = {"now": "librarian"}
    monkeypatch.setattr("openlibrary.fastapi.shared.site_page.load_shell_user", lambda: roles[role["now"]])
    test_client = TestClient(site_page_app(pages), headers={"x-user": "reader"}, follow_redirects=False)
    test_client.as_role = lambda name: role.update(now=name)  # type: ignore[attr-defined]
    return test_client


def test_only_librarians_and_above_get_in(client, stats_queries):
    client.as_role("member")
    assert client.get("/stats/merges").status_code == 403
    client.as_role("librarian")
    assert client.get("/stats/merges").status_code == 200
    stats_queries[0].assert_awaited_once()


def test_stats_page_renders_rows_and_pagination(client, stats_queries):
    response = client.get("/stats/merges")
    assert response.status_code == 200
    assert "Community Edit Request Statistics | Open Library" in response.text
    assert "alice" in response.text
    assert "75%" in response.text
    assert 'total-pages="3"' in response.text
    assert 'href="/merges?mode=closed&amp;reviewer=alice"' in response.text
    get_stats, get_count = stats_queries
    get_stats.assert_awaited_once_with("reviewer", since=None, sort="total", order="desc", limit=25, page=1)
    get_count.assert_awaited_once_with("reviewer", since=None)


@pytest.mark.parametrize(("date_range", "days"), [("year", 365), ("month", 30)])
def test_filters_reach_the_queries(client, stats_queries, date_range, days):
    response = client.get(f"/stats/merges?group=submitters&range={date_range}&sort=rate&order=asc&page=2")
    assert response.status_code == 200
    since = dt.date.today() - dt.timedelta(days=days)
    get_stats, get_count = stats_queries
    get_stats.assert_awaited_once_with("submitter", since=since, sort="rate", order="asc", limit=25, page=2)
    get_count.assert_awaited_once_with("submitter", since=since)


@pytest.mark.parametrize("query", ["group=other", "range=week", "sort=evil", "order=sideways", "page=abc", "page=1.5"])
def test_invalid_inputs_are_400_without_reading_database(client, stats_queries, query):
    response = client.get("/stats/merges?" + query)
    assert response.status_code == 400
    for query_mock in stats_queries:
        query_mock.assert_not_awaited()


@pytest.mark.parametrize("page", ["0", "-3"])
def test_nonpositive_page_is_clamped(client, stats_queries, page):
    assert client.get(f"/stats/merges?page={page}").status_code == 200
    assert stats_queries[0].await_args.kwargs["page"] == 1


def test_last_repeated_parameter_wins_and_unknown_is_ignored(client, stats_queries):
    response = client.get("/stats/merges?group=reviewers&group=submitters&extra=kept&page=2&page=3")
    assert response.status_code == 200
    assert stats_queries[0].await_args.args == ("submitter",)
    assert stats_queries[0].await_args.kwargs["page"] == 3
    html = BeautifulSoup(response.text, "html.parser")
    link = html.select_one(".table-header a")
    assert parse_qs(urlsplit(link["href"]).query) == {"group": ["reviewers"], "extra": ["kept"]}


def test_links_sort_and_reset_page(client):
    response = client.get("/stats/merges?sort=merged&order=desc&page=3&range=year")
    html = BeautifulSoup(response.text, "html.parser")
    links = {a.get_text(): parse_qs(urlsplit(a["href"]).query) for a in html.select("th a")}
    assert links["Merged ▾"] == {"sort": ["merged"], "order": ["asc"], "range": ["year"]}
    assert links["Declined"] == {"sort": ["declined"], "order": ["desc"], "range": ["year"]}


def test_username_is_escaped_and_url_encoded(client, stats_queries):
    username = "<script>&a=b#c"
    stats_queries[0].return_value = [{**ROWS[0], "username": username}]
    response = client.get("/stats/merges")
    assert username not in response.text
    html = BeautifulSoup(response.text, "html.parser")
    link = html.select_one("tbody a")
    assert link.get_text() == username
    assert parse_qs(urlsplit(link["href"]).query) == {"mode": ["closed"], "reviewer": [username]}


def test_empty_table(client, stats_queries):
    stats_queries[0].return_value = []
    stats_queries[1].return_value = 0
    response = client.get("/stats/merges")
    assert "No entries here!" in response.text
    assert "<ol-pagination" not in response.text


def test_visitor_is_sent_to_login_with_full_return_path(client, stats_queries):
    client.as_role("visitor")
    response = client.get("/stats/merges?range=month&page=2")
    assert response.status_code == 303
    location = urlsplit(response.headers["location"])
    assert location.path == "/account/login"
    assert parse_qs(location.query) == {"redirect": ["/stats/merges?range=month&page=2"]}
    for query_mock in stats_queries:
        query_mock.assert_not_awaited()


def test_head_is_supported(client):
    response = client.head("/stats/merges")
    assert response.status_code == 200
    assert response.content == b""


def test_concurrent_requests_do_not_read_webpy_leftovers(site_page_app, stats_queries, webpy_leftovers, fetch_concurrently, monkeypatch):
    monkeypatch.setattr("openlibrary.fastapi.shared.site_page.load_shell_user", lambda: shell_user(True))
    requests = [(f"/stats/merges?group={'submitters' if i % 2 else 'reviewers'}&extra=request-{i}", {"x-user": "reader"}) for i in range(12)]
    responses = fetch_concurrently(site_page_app(pages), requests)
    for i, response in enumerate(responses):
        assert response.status_code == 200
        assert webpy_leftovers not in response.text
        assert f"extra=request-{i}" in response.text
        assert not any(f"extra=request-{j}&" in response.text for j in range(12) if i != j)


def test_nav_preserves_repeated_and_blank_parameters(client):
    response = client.get("/stats/merges?group=reviewers&group=submitters&extra=one&extra=two&empty=")
    html = BeautifulSoup(response.text, "html.parser")
    link = html.select(".table-header a")[2]
    assert parse_qs(urlsplit(link["href"]).query, keep_blank_values=True) == {
        "group": ["reviewers", "submitters"],
        "extra": ["one", "two"],
        "empty": [""],
        "range": ["all"],
    }


@pytest.mark.parametrize("sort", ["total", "merged", "declined", "rate"])
@pytest.mark.parametrize("order", ["asc", "desc"])
def test_table_headers_expose_sort_state(client, sort, order):
    response = client.get(f"/stats/merges?sort={sort}&order={order}")
    html = BeautifulSoup(response.text, "html.parser")
    headers = html.select(".mr-stats-table th")
    assert len(headers) == 7
    assert all(header.get("scope") == "col" for header in headers)
    sorted_headers = html.select("th[aria-sort]")
    assert len(sorted_headers) == 1
    assert sorted_headers[0]["aria-sort"] == ("ascending" if order == "asc" else "descending")
    query = parse_qs(urlsplit(sorted_headers[0].a["href"]).query)
    assert query["sort"] == [sort]
