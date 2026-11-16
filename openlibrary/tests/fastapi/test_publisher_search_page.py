"""`/search/publishers` HTML page on FastAPI, and its web.py handler while that still exists.

It renders `search/publishers.html.jinja`; the web.py handler renders the same
template until ops routes /search/publishers to FastAPI in production. The
shell around the page is tested in `test_site_page.py`.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
import web
from fastapi.testclient import TestClient

from openlibrary.core.jinja import render_jinja_template
from openlibrary.fastapi.search import pages, publisher_results
from openlibrary.plugins.worksearch import publishers as publishers_code


@pytest.fixture
def client(site_page_app) -> TestClient:
    return TestClient(site_page_app(pages))


def solr_result(*facets: tuple[str, int]) -> web.storage:
    """The shape `Solr.select_async` returns: a `facets` dict of `name`/`value`/`count` storages."""
    return web.storage(
        facets={"publisher_facet": [web.storage(name="publisher_facet", value=value, count=count) for value, count in facets]},
    )


def mock_solr(result: web.storage) -> MagicMock:
    solr = MagicMock()
    solr.select_async = AsyncMock(return_value=result)
    solr.select = MagicMock(return_value=result)
    return solr


def test_page_without_query(client, monkeypatch):
    solr = mock_solr(solr_result())
    monkeypatch.setattr("openlibrary.fastapi.search.get_solr", lambda: solr)
    response = client.get("/search/publishers")

    assert response.status_code == 200
    html = response.text
    assert "<title>Publisher search | Open Library</title>" in html
    assert "<h1>Publishers Search</h1>" in " ".join(html.split())
    # The form submits back to this page
    assert 'action=""' in html
    assert 'name="q"' in html
    # It reuses the shared search box, as the lists and subjects search pages do
    assert 'class="searchbox"' in html
    # A query still runs, but matches nothing, so there are no rows
    solr.select_async.assert_awaited_once_with(
        query={"publisher": "", "type": "work"},
        facets=["publisher_facet"],
        facet_mincount=1,
        facet_limit=25,
        facet_contains="",
        facet_contains_ignoreCase="true",
        rows=0,
    )


def test_page_title_leads_with_the_query(client, monkeypatch):
    solr = mock_solr(solr_result())
    monkeypatch.setattr("openlibrary.fastapi.search.get_solr", lambda: solr)
    response = client.get("/search/publishers?q=penguin+%3Cstuff%3E")

    assert response.status_code == 200
    assert "<title>penguin &lt;stuff&gt; - Publisher search | Open Library</title>" in response.text


def test_page_results(client, monkeypatch):
    solr = mock_solr(solr_result(("Penguin Books", 3), ("Solo Press", 1)))
    monkeypatch.setattr("openlibrary.fastapi.search.get_solr", lambda: solr)
    response = client.get("/search/publishers?q=penguin")

    assert response.status_code == 200
    html = response.text
    assert 'href="/publishers/Penguin_Books">Penguin Books</a>' in html
    assert 'href="/publishers/Solo_Press">Solo Press</a>' in html
    assert "3 books" in html
    assert "1 book" in html
    assert 'value="penguin"' in html
    solr.select_async.assert_awaited_once_with(
        query={"publisher": "penguin", "type": "work"},
        facets=["publisher_facet"],
        facet_mincount=1,
        facet_limit=25,
        facet_contains="penguin",
        facet_contains_ignoreCase="true",
        rows=0,
    )


def test_page_escapes_the_query_but_queries_solr_raw(client, monkeypatch):
    solr = mock_solr(solr_result())
    monkeypatch.setattr("openlibrary.fastapi.search.get_solr", lambda: solr)
    response = client.get("/search/publishers?q=%22%3E%3Cscript%3E")

    assert response.status_code == 200
    assert 'value="&#34;&gt;&lt;script&gt;"' in response.text
    assert solr.select_async.call_args.kwargs["facet_contains"] == '"><script>'


def test_webpy_handler_renders_the_fastapi_body(monkeypatch, request_context_fixture):
    """Until web.py's handler is retired, both servers render the same page body."""
    request_context_fixture(lang="en")
    result = solr_result(("Penguin Books", 3))
    monkeypatch.setattr("openlibrary.plugins.worksearch.publishers.search.get_solr", lambda: mock_solr(result))
    for key, value in {"path": "/search/publishers", "env": {"QUERY_STRING": "q=penguin", "REQUEST_METHOD": "GET"}}.items():
        monkeypatch.setattr(web.ctx, key, value, raising=False)

    webpy_result = publishers_code.publisher_search().GET()
    webpy_body = str(webpy_result)
    assert str(webpy_result.title) == "penguin - Publisher search"

    expected = render_jinja_template("search/publishers.html.jinja", q="penguin", publishers=publisher_results(result.facets["publisher_facet"]))
    assert webpy_body == expected
    assert 'href="/publishers/Penguin_Books">Penguin Books</a>' in webpy_body
    assert "3 books" in webpy_body
