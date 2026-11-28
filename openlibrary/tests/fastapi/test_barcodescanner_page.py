"""`/barcodescanner` HTML page on FastAPI.

It renders `barcodescanner.html.jinja`, as does the web.py handler until ops
routes /barcodescanner to FastAPI in production. The shell around the page is
tested in `test_site_page.py`; these test the page's own body.
"""

import pytest
from fastapi.testclient import TestClient

from infogami.utils.context import context
from openlibrary.core.jinja import render_jinja_template
from openlibrary.fastapi.barcodescanner import pages
from openlibrary.plugins.upstream import code as upstream_code
from openlibrary.plugins.upstream.utils import vue_component_html
from openlibrary.plugins.worksearch.code import scan


@pytest.fixture
def client(site_page_app) -> TestClient:
    return TestClient(site_page_app(pages))


def test_barcodescanner_page_renders_the_component(client):
    response = client.get("/barcodescanner")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    html = response.text
    assert "<title>Barcode Scanner (Beta) | Open Library</title>" in html
    assert html.count("<ol-barcode-scanner></ol-barcode-scanner>") == 1
    assert 'src="/static/build/components/production/ol-BarcodeScanner.js"' in html
    assert 'id="test-body-mobile"' not in html  # the scanner draws its own chrome, without the site header


@pytest.fixture
def stubbed_static_url(monkeypatch) -> None:
    """``static_url`` hashes a file under ``static/``, which CI has no Vite build for."""
    monkeypatch.setattr(upstream_code, "static_url", lambda p: f"/static/{p}")


def test_webpy_handler_renders_the_fastapi_body(monkeypatch, stubbed_static_url):
    """Until web.py's handler is retired, both servers render the same page body."""
    monkeypatch.delitem(context, "show_ol_shell", raising=False)

    result = scan().GET()

    assert result.title == "Barcode Scanner (Beta)"  # web.py's layout reads the title from here
    assert context["show_ol_shell"] is False
    assert str(result) == render_jinja_template("barcodescanner.html.jinja", vue_component_html=vue_component_html)


def test_barcodescanner_page_does_not_read_webpy_ctx(client, webpy_leftovers):
    """The page renders without web.py's request state, which a FastAPI request must not touch."""
    response = client.get("/barcodescanner")

    assert response.status_code == 200
    assert webpy_leftovers not in response.text
