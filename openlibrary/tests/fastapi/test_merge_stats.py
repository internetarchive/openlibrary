"""The stats page's inputs, links and per-request isolation on both servers."""

import datetime as dt
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest
import web
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from openlibrary.core.edits import CommunityEditsQueue
from openlibrary.fastapi.merge_stats import pages
from openlibrary.plugins.upstream.edits import community_edits_queue_stats

ROWS = [{"username": "alice", "total": 4, "merged": 3, "declined": 1, "merge_rate": 75.0, "author_requests": 1, "work_requests": 3}]


@pytest.fixture
def stats_queries(monkeypatch):
    get_stats = Mock(return_value=ROWS)
    get_count = Mock(return_value=51)
    monkeypatch.setattr(CommunityEditsQueue, "get_stats", get_stats)
    monkeypatch.setattr(CommunityEditsQueue, "get_stats_count", get_count)
    return get_stats, get_count


@pytest.fixture
def client(site_page_app, stats_queries):
    return TestClient(site_page_app(pages), headers={"x-user": "reader"})


def test_stats_page_renders_rows_and_pagination(client, stats_queries):
    response = client.get("/merges/stats")
    assert response.status_code == 200
    assert "Community Edit Request Statistics | Open Library" in response.text
    assert "alice" in response.text
    assert "75%" in response.text
    assert 'total-pages="3"' in response.text
    assert 'href="/merges?mode=closed&amp;reviewer=alice"' in response.text
    get_stats, get_count = stats_queries
    get_stats.assert_called_once_with("reviewer", since=None, sort="total", order="desc", limit=25, page=1)
    get_count.assert_called_once_with("reviewer", since=None)


@pytest.mark.parametrize(("date_range", "days"), [("year", 365), ("month", 30)])
def test_filters_reach_the_queries(client, stats_queries, date_range, days):
    response = client.get(f"/merges/stats?group=submitters&range={date_range}&sort=rate&order=asc&page=2")
    assert response.status_code == 200
    since = dt.date.today() - dt.timedelta(days=days)
    get_stats, get_count = stats_queries
    get_stats.assert_called_once_with("submitter", since=since, sort="rate", order="asc", limit=25, page=2)
    get_count.assert_called_once_with("submitter", since=since)


@pytest.mark.parametrize("query", ["group=other", "range=week", "sort=evil", "order=sideways", "page=abc", "page=1.5"])
def test_invalid_inputs_are_400_without_reading_database(client, stats_queries, query):
    response = client.get("/merges/stats?" + query)
    assert response.status_code == 400
    for query_mock in stats_queries:
        query_mock.assert_not_called()


@pytest.mark.parametrize("page", ["0", "-3"])
def test_nonpositive_page_is_clamped(client, stats_queries, page):
    assert client.get(f"/merges/stats?page={page}").status_code == 200
    assert stats_queries[0].call_args.kwargs["page"] == 1


def test_last_repeated_parameter_wins_and_unknown_is_ignored(client, stats_queries):
    response = client.get("/merges/stats?group=reviewers&group=submitters&extra=kept&page=2&page=3")
    assert response.status_code == 200
    assert stats_queries[0].call_args.args == ("submitter",)
    assert stats_queries[0].call_args.kwargs["page"] == 3
    html = BeautifulSoup(response.text, "html.parser")
    link = html.select_one(".table-header a")
    assert parse_qs(urlsplit(link["href"]).query) == {"group": ["reviewers"], "extra": ["kept"]}


def test_links_sort_and_reset_page(client):
    response = client.get("/merges/stats?sort=merged&order=desc&page=3&range=year")
    html = BeautifulSoup(response.text, "html.parser")
    links = {a.get_text(): parse_qs(urlsplit(a["href"]).query) for a in html.select("th a")}
    assert links["Merged ▾"] == {"sort": ["merged"], "order": ["asc"], "range": ["year"]}
    assert links["Declined"] == {"sort": ["declined"], "order": ["desc"], "range": ["year"]}


def test_username_is_escaped_and_url_encoded(client, stats_queries):
    username = "<script>&a=b#c"
    stats_queries[0].return_value = [{**ROWS[0], "username": username}]
    response = client.get("/merges/stats")
    assert username not in response.text
    html = BeautifulSoup(response.text, "html.parser")
    link = html.select_one("tbody a")
    assert link.get_text() == username
    assert parse_qs(urlsplit(link["href"]).query) == {"mode": ["closed"], "reviewer": [username]}


def test_empty_table(client, stats_queries):
    stats_queries[0].return_value = []
    stats_queries[1].return_value = 0
    response = client.get("/merges/stats")
    assert "No entries here!" in response.text
    assert "<ol-pagination" not in response.text


def test_visitor_is_sent_to_login_with_full_return_path(site_page_app, stats_queries):
    client = TestClient(site_page_app(pages))
    response = client.get("/merges/stats?range=month&page=2", follow_redirects=False)
    assert response.status_code == 303
    location = urlsplit(response.headers["location"])
    assert location.path == "/account/login"
    assert parse_qs(location.query) == {"redirect": ["/merges/stats?range=month&page=2"]}
    for query_mock in stats_queries:
        query_mock.assert_not_called()


def test_head_is_supported(client):
    response = client.head("/merges/stats")
    assert response.status_code == 200
    assert response.content == b""


def test_concurrent_requests_do_not_read_webpy_leftovers(site_page_app, stats_queries, webpy_leftovers, fetch_concurrently):
    requests = [(f"/merges/stats?group={'submitters' if i % 2 else 'reviewers'}&extra=request-{i}", {"x-user": "reader"}) for i in range(12)]
    responses = fetch_concurrently(site_page_app(pages), requests)
    for i, response in enumerate(responses):
        assert response.status_code == 200
        assert webpy_leftovers not in response.text
        assert f"extra=request-{i}" in response.text
        assert not any(f"extra=request-{j}&" in response.text for j in range(12) if i != j)


@pytest.mark.parametrize("query", ["", "group=submitters&range=month&sort=rate&order=asc&page=2", "group=reviewers&group=submitters&extra=kept"])
def test_webpy_wrapper_renders_same_body(monkeypatch, request_context_fixture, client, query):
    request_context_fixture(lang="en")
    monkeypatch.setattr(web.ctx, "site", web.storage(get_user=lambda: True), raising=False)
    monkeypatch.setattr(web.ctx, "path", "/merges/stats", raising=False)
    monkeypatch.setattr(web.ctx, "env", {"QUERY_STRING": query, "REQUEST_METHOD": "GET"}, raising=False)
    result = community_edits_queue_stats().GET()
    assert result.title == "Community Edit Request Statistics"
    response = client.get("/merges/stats?" + query)
    assert response.status_code == 200
    assert BeautifulSoup(str(result), "html.parser").select_one(".merge-stats") == BeautifulSoup(response.text, "html.parser").select_one(".merge-stats")


@pytest.mark.parametrize("query", ["group=other", "range=week", "sort=evil", "order=sideways", "page=abc"])
def test_webpy_wrapper_rejects_invalid_inputs(monkeypatch, request_context_fixture, stats_queries, query):
    request_context_fixture(lang="en")
    monkeypatch.setattr(web.ctx, "site", web.storage(get_user=lambda: True), raising=False)
    monkeypatch.setattr(web.ctx, "env", {"QUERY_STRING": query, "REQUEST_METHOD": "GET"}, raising=False)
    monkeypatch.setattr(web.ctx, "headers", [], raising=False)
    result = community_edits_queue_stats().GET()
    assert isinstance(result, web.HTTPError)
    assert web.ctx.status == "400 Bad Request"
    for query_mock in stats_queries:
        query_mock.assert_not_called()


def test_nav_preserves_repeated_and_blank_parameters(client):
    response = client.get("/merges/stats?group=reviewers&group=submitters&extra=one&extra=two&empty=")
    html = BeautifulSoup(response.text, "html.parser")
    link = html.select(".table-header a")[2]
    assert parse_qs(urlsplit(link["href"]).query, keep_blank_values=True) == {
        "group": ["reviewers", "submitters"],
        "extra": ["one", "two"],
        "empty": [""],
        "range": ["all"],
    }
