"""`/publishers` and `/publishers/<name>` pages on FastAPI, and their web.py handlers.

Both servers render the same Jinja templates until ops routes these paths to
FastAPI in production. The shell around the pages is tested in
`test_site_page.py`.
"""

from unittest.mock import AsyncMock

import pytest
import web
from fastapi.testclient import TestClient

from openlibrary.core.helpers import commify
from openlibrary.core.jinja import render_jinja_template
from openlibrary.fastapi.publishers import pages
from openlibrary.plugins.openlibrary.partials import query_carousel
from openlibrary.plugins.worksearch import publishers as publishers_code


@pytest.fixture
def client(site_page_app) -> TestClient:
    return TestClient(site_page_app(pages))


def publisher_subject(**overrides) -> web.storage:
    """The fields `publishers/view.html.jinja` reads, as `get_subject(details=True)` returns them."""
    subject = web.storage(
        key="/publishers/Penguin Books",
        name="Penguin Books",
        subject_type="publisher",
        solr_query='publisher_facet:"Penguin Books"',
        work_count=1234,
        ebook_count=3,
        publishing_history=[[1935, 2], [1936, 5]],
        subjects=[web.storage(key="/subjects/penguins", name="penguins", count=7)],
        places=[],
        people=[],
        times=[],
        authors=[web.storage(key="/authors/OL1A", name="A. Author", count=11)],
    )
    subject.update(overrides)
    return subject


def mock_subject(monkeypatch, subject) -> AsyncMock:
    get_subject = AsyncMock(return_value=subject)
    monkeypatch.setattr("openlibrary.fastapi.publishers.get_subject_async", get_subject)
    return get_subject


def test_index_page(client):
    response = client.get("/publishers")

    assert response.status_code == 200
    html = response.text
    assert "<h1>Publishers</h1>" in html
    # No explicit title, so the shell uses the path, as web.py does
    assert "<title>publishers | Open Library</title>" in html
    assert 'action="/search/publishers"' in html
    assert 'name="q"' in html


def test_publisher_page(client, monkeypatch):
    get_subject = mock_subject(monkeypatch, publisher_subject())
    response = client.get("/publishers/Penguin_Books")

    assert response.status_code == 200
    html = response.text
    get_subject.assert_awaited_once_with("/publishers/Penguin Books", details=True, request_label="SUBJECT_ENGINE_PAGE")
    assert "<title>Publisher: Penguin Books | Open Library</title>" in html
    assert "1234 works" in html
    assert "3 ebooks" in html
    # The chart data publishing-history.js reads
    assert 'id="graph-json-chartPubHistory">[[1935, 2], [1936, 5]]' in html
    # Subject chips and author counts come from the facets
    assert 'href="/subjects/penguins"' in html
    assert 'href="/authors/OL1A"' in html
    assert "11 books" in html
    # The carousel is the lazy placeholder the Templetor macro used to render
    assert 'class="lazy-carousel"' in html
    assert "publisher_facet" in html


def test_underscores_become_spaces_in_the_key(client, monkeypatch):
    get_subject = mock_subject(monkeypatch, publisher_subject())
    client.get("/publishers/Dover_Publications")

    assert get_subject.call_args.args == ("/publishers/Dover Publications",)


def test_publisher_without_works_is_404(client, monkeypatch):
    mock_subject(monkeypatch, publisher_subject(work_count=0))
    response = client.get("/publishers/Penguin_Books")

    assert response.status_code == 404
    html = response.text
    assert "no books published by Penguin Books" in html
    # No explicit title, so the shell uses the path, as web.py does
    assert "<title>publishers/Penguin_Books | Open Library</title>" in html


def test_webpy_handlers_render_the_fastapi_bodies(monkeypatch, request_context_fixture):
    """Until web.py's handlers are retired, both servers render the same page bodies."""
    request_context_fixture(lang="en")
    subject = publisher_subject()
    monkeypatch.setattr("openlibrary.plugins.worksearch.publishers.subjects.get_subject", lambda *args, **kwargs: subject)
    for key, value in {"path": "/publishers/Penguin_Books", "env": {"QUERY_STRING": "", "REQUEST_METHOD": "GET"}}.items():
        monkeypatch.setattr(web.ctx, key, value, raising=False)

    body = str(publishers_code.publishers().GET("/publishers/Penguin_Books"))
    expected = render_jinja_template("publishers/view.html.jinja", page=subject, commify=commify, query_carousel=query_carousel)
    assert body == expected
    assert "<title>" not in body  # the shell adds it, from the handler's title

    assert str(publishers_code.index().GET()) == render_jinja_template("publishers/index.html.jinja")
