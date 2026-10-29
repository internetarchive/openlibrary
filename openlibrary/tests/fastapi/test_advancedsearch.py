"""/advancedsearch on FastAPI, and its web.py handler while that still exists.

The shell around the page (user, flash messages, language) is tested in
``test_site_page.py``; these test the page's own body and inputs.
"""

from urllib.parse import quote

import pytest
import web
from fastapi import Request
from fastapi.testclient import TestClient

from openlibrary.core.jinja import render_jinja_template
from openlibrary.fastapi.search import AdvancedSearchForm, SearchNav, pages
from openlibrary.plugins.openlibrary.code import changequery as templetor_changequery
from openlibrary.plugins.worksearch import code as worksearch_code


@pytest.fixture
def client(site_page_app) -> TestClient:
    return TestClient(site_page_app(pages))


def test_concurrent_requests_each_get_only_their_own_page(site_page_app, webpy_leftovers, fetch_concurrently):
    """The form and search tabs come from this request: never another request's, or web.py's leftovers."""
    n = 12
    responses = fetch_concurrently(site_page_app(pages), [(f"/advancedsearch?q=query-{i}", {}) for i in range(n)])
    for i, response in enumerate(responses):
        html = response.text
        assert response.status_code == 200
        assert webpy_leftovers not in html
        assert f'value="query-{i}"' in html
        assert f'href="/search?q=query-{i}"' in html
        assert not any(f'query-{j}"' in html for j in range(n) if j != i)


def test_advancedsearch_renders_form_and_escapes_input(client):
    payload = '"><script>alert(1)</script>'
    response = client.get(f"/advancedsearch?title={quote(payload)}&subject_facet=Fiction&subject=")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert "set-cookie" not in response.headers
    html = response.text
    assert "<script>alert(1)" not in html
    assert 'value="&#34;&gt;&lt;script&gt;alert(1)&lt;/script&gt;"' in html
    assert 'value="Fiction"' in html  # facet is the fallback for an empty field
    assert "<title>Advanced Search | Open Library</title>" in html


def _webpy_get(monkeypatch, path: str, query: str) -> None:
    for key, value in {"path": path, "env": {"QUERY_STRING": query, "REQUEST_METHOD": "GET"}}.items():
        monkeypatch.setattr(web.ctx, key, value, raising=False)


def _starlette_request(path: str, query: str) -> Request:
    return Request({"type": "http", "method": "GET", "path": path, "query_string": query.encode(), "headers": [], "root_path": ""})


@pytest.mark.parametrize(
    "query",
    ["", "q=a+b&page=3&q=c", "q=%C3%B1and%C3%BA&x=", "subject_facet=Fiction&page=2", "page=2"],
)
def test_search_nav_matches_templetor_on_both_servers(monkeypatch, query):
    """The Advanced Search tab link is what the Templetor ``changequery`` builds, from either server."""
    _webpy_get(monkeypatch, "/search", query)
    expected = templetor_changequery(_path="/advancedsearch", page=None)
    assert SearchNav.from_request(_starlette_request("/search", query)).advanced_href == expected
    assert SearchNav.from_query("/search", web.input(_method="get")).advanced_href == expected


def test_webpy_handler_renders_the_fastapi_body(monkeypatch, request_context_fixture):
    """Until web.py's handler is retired, both servers render the same page body."""
    request_context_fixture(lang="en")
    query = "q=tolkien&title=%3Cb%3E&subject_facet=Fiction&page=2"
    _webpy_get(monkeypatch, "/advancedsearch", query)
    result = worksearch_code.advancedsearch().GET()
    assert result.title == "Advanced Search"  # web.py's layout reads the title from here
    webpy_body = str(result)

    request = _starlette_request("/advancedsearch", query)
    form = AdvancedSearchForm.model_validate(dict(request.query_params))
    assert webpy_body == render_jinja_template("search/advancedsearch.html.jinja", form=form, nav=SearchNav.from_request(request))
    assert 'value="&lt;b&gt;"' in webpy_body
    assert 'value="Fiction"' in webpy_body


def test_advancedsearch_query_params(client):
    response = client.get("/advancedsearch?title=first&title=last&mode=everything&subject=Own&subject_facet=Fallback")
    assert response.status_code == 200
    html = response.text
    assert 'value="last"' in html  # repeated param: last value wins, as with web.input()
    assert 'value="first"' not in html
    assert 'value="Own"' in html  # a field given directly beats its facet fallback
    assert 'value="Fallback"' not in html
    assert 'href="/advancedsearch?title=last&amp;mode=everything&amp;subject=Own&amp;subject_facet=Fallback"' in html
