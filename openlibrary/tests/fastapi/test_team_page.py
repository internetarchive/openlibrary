"""`/about/team` HTML page on FastAPI.

It renders `about/index.html.jinja`, as does the web.py handler until ops
routes /about/team to FastAPI in production. The shell around the page is
tested in `test_site_page.py`; these test the page's own body.
"""

import pytest
from fastapi.testclient import TestClient

from infogami.utils.context import context
from openlibrary.core.jinja import render_jinja_template
from openlibrary.fastapi.about import pages
from openlibrary.plugins.openlibrary import code as openlibrary_code
from openlibrary.utils.request_context import RequestContextVars, req_context


@pytest.fixture
def client(site_page_app) -> TestClient:
    return TestClient(site_page_app(pages))


@pytest.fixture
def english_request():
    """The template's gettext reads the language from the request context, which only a request sets."""
    token = req_context.set(RequestContextVars(None, None, "en", True, False))
    yield
    req_context.reset(token)


def test_team_page_renders_the_team_filters(client):
    response = client.get("/about/team")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    html = response.text
    assert "<title>The Open Library Team | Open Library</title>" in html
    assert '<link href="/static/build/css/page-team.css"' in html
    assert html.count("<h1>The Open Library Team</h1>") == 1
    assert '<div class="teamCards_container"></div>' in html
    # team.js writes the cards, the year choices and the section headings.
    assert '<option value="All" selected>All</option>' in html


def test_webpy_handler_renders_the_fastapi_body(monkeypatch, english_request):
    """Until web.py's handler is retired, both servers render the same page body."""
    monkeypatch.delitem(context, "cssfile", raising=False)  # unset, as at the start of a request

    result = openlibrary_code.team().GET()

    assert result.title == "The Open Library Team"  # web.py's layout reads the title from here
    assert context.cssfile == "team"
    assert str(result) == render_jinja_template("about/index.html.jinja")


def test_team_page_does_not_read_webpy_ctx(client, webpy_leftovers):
    """The page renders without web.py's request state, which a FastAPI request must not touch."""
    response = client.get("/about/team")

    assert response.status_code == 200
    assert webpy_leftovers not in response.text
