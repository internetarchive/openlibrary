"""`/explore` HTML page on FastAPI.

It renders `library_explorer.html.jinja`, as does the web.py handler until ops
routes /explore to FastAPI in production. The shell around the page is tested in
`test_site_page.py`; these test the page's own body.
"""

import pytest
from fastapi.testclient import TestClient

from infogami.utils.context import context
from openlibrary.core.jinja import get_jinja_env, render_jinja_template
from openlibrary.fastapi.library_explorer import pages
from openlibrary.plugins.upstream import code as upstream_code


@pytest.fixture
def client(site_page_app) -> TestClient:
    return TestClient(site_page_app(pages))


def test_library_explorer_page_renders_the_component(client):
    response = client.get("/explore")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    html = response.text
    assert "<title>Library Explorer | Open Library</title>" in html
    assert '<body class="full-width library-explorer"' in html
    assert html.count("<ol-library-explorer>") == 1
    assert 'src="/static/build/components/production/ol-LibraryExplorer.js"' in html
    assert "body.library-explorer" in html


@pytest.fixture
def stubbed_static_url(monkeypatch) -> None:
    """``static_url`` hashes a file under ``static/``, which CI has no Vite build for."""
    monkeypatch.setitem(get_jinja_env().globals, "static_url", lambda p: f"/static/{p}")


def test_webpy_handler_renders_the_fastapi_body(monkeypatch, stubbed_static_url):
    """Until web.py's handler is retired, both servers render the same page body."""
    monkeypatch.setitem(context, "bodyclass", [])

    result = upstream_code.library_explorer().GET()

    assert result.title == "Library Explorer"  # web.py's layout reads the title from here
    assert context.bodyclass == ["full-width", "library-explorer"]
    assert str(result) == render_jinja_template("library_explorer.html.jinja")


def test_library_explorer_page_does_not_read_webpy_ctx(client, webpy_leftovers):
    """The page renders without web.py's request state, which a FastAPI request must not touch."""
    response = client.get("/explore")

    assert response.status_code == 200
    assert webpy_leftovers not in response.text
