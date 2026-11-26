"""`/search/bulk` HTML page on FastAPI.

It renders `bulk_search/bulk_search.html.jinja`, as does the web.py handler until
ops routes /search/bulk to FastAPI in production. The shell around the page is
tested in `test_site_page.py`; these test the page's own body.
"""

import pytest
from fastapi.testclient import TestClient

from openlibrary.fastapi.search import pages


@pytest.fixture
def client(site_page_app) -> TestClient:
    return TestClient(site_page_app(pages))


def test_bulk_search_page_renders_the_component(client):
    response = client.get("/search/bulk")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    html = response.text
    assert "<title>Bulk Search (beta) | Open Library</title>" in html
    assert "<h1>Bulk Search (beta)</h1>" in html
    assert html.count("<ol-bulk-search>") == 1
    assert 'src="/static/build/components/production/ol-BulkSearch.js"' in html


def test_bulk_search_page_does_not_read_webpy_ctx(client, webpy_leftovers):
    """The page renders without web.py's request state, which a FastAPI request must not touch."""
    response = client.get("/search/bulk")

    assert response.status_code == 200
    assert webpy_leftovers not in response.text
