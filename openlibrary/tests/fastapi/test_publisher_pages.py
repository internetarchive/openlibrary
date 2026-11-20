"""`/publishers` and `/publishers/<name>` pages on FastAPI, and their web.py handlers.

Both servers render the same Jinja templates until ops routes these paths to
FastAPI in production. The shell around the pages is tested in
`test_site_page.py`.
"""

from unittest.mock import AsyncMock

import pytest
import web
from fastapi.testclient import TestClient

# The web.py plugin setup, which loads plugins.openlibrary.partials before
# fastapi.publishers imports its carousel helper from there.
import openlibrary.plugins.openlibrary.code  # noqa: F401
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
    assert "find any books published by Penguin Books" in html
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


def test_concurrent_requests_each_get_only_their_own_page(site_page_app, webpy_leftovers, fetch_concurrently, monkeypatch):
    """The publisher comes from this request: never another request's, or web.py's leftovers."""

    async def get_subject(key, **kwargs):
        name = key.removeprefix("/publishers/")
        return publisher_subject(key=key, name=name, solr_query=f'publisher_facet:"{name}"')

    monkeypatch.setattr("openlibrary.fastapi.publishers.get_subject_async", get_subject)
    n = 12
    responses = fetch_concurrently(site_page_app(pages), [(f"/publishers/Press_{i}", {}) for i in range(n)])
    for i, response in enumerate(responses):
        html = response.text
        assert response.status_code == 200
        assert webpy_leftovers not in html
        assert f"<title>Publisher: Press {i} | Open Library</title>" in html
        assert not any(f"Press {j}<" in html or f"Press {j} |" in html for j in range(n) if j != i)
