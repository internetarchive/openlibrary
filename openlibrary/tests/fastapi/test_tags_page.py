"""`/tags` on FastAPI, and its web.py handler.

Both servers render the same Jinja templates until ops routes these paths to
FastAPI in production. The shell around the pages is tested in
`test_site_page.py`.
"""

import re
from unittest.mock import MagicMock, patch

import pytest
import web
from fastapi.testclient import TestClient

from openlibrary.core.jinja import render_jinja_template
from openlibrary.fastapi.tags import pages
from openlibrary.plugins.upstream import addtag


class FakeTag(web.storage):
    """The fields the tag templates read, without infobase."""

    def get_most_recent_change(self):
        return web.storage(author=None)

    def url(self, **params):
        query = "?" + "&".join(f"{k}={v}" for k, v in params.items()) if params else ""
        return f"{self.key}/{self.name}{query}"

    def is_fake_record(self):
        return False


def tag_doc(**overrides) -> FakeTag:
    tag = FakeTag(
        key="/tags/OL1T",
        type=web.storage(key="/type/tag"),
        name="Horror",
        tag_type="genre",
        slugs=["horror", "scary"],
        tag_description="Scary stories.",
        body="A *scary* story.",
        last_modified="",
    )
    tag.update(overrides)
    return tag


@pytest.fixture
def client(site_page_app) -> TestClient:
    return TestClient(site_page_app(pages))


def mock_site(**methods) -> MagicMock:
    """Patch the request-scoped site the page reads, returning the site itself."""
    current_site = MagicMock()
    for name, value in methods.items():
        getattr(current_site, name).return_value = value
    site_mock = MagicMock()
    site_mock.get.return_value = current_site
    patcher = patch("openlibrary.fastapi.tags.site", site_mock)
    patcher.start()
    return current_site


@pytest.fixture(autouse=True)
def stop_site_patches():
    yield
    patch.stopall()


def test_tags_index_lists_tags_and_their_subject_pages(client):
    current_site = mock_site(things=["/tags/OL1T"], get_many=[tag_doc()])

    response = client.get("/tags?type=genre&page=2")

    assert response.status_code == 200
    html = response.text
    assert "<title>Tags | Open Library</title>" in html
    assert '<a class="tag-list__name" href="/tags/OL1T">Horror</a>' in html
    assert '<a class="tag-list__subject-link" href="/subjects/genre:horror">' in html
    assert re.search(r'<a href="/tags\?type=genre"\s+class="selected">genre</a>', html)
    assert 'href="/tags?page=1&amp;type=genre">« Previous</a>' in html
    current_site.things.assert_called_once_with({"type": "/type/tag", "limit": 21, "offset": 20, "tag_type": "genre"})


def test_tags_index_ignores_an_unknown_type_and_a_non_numeric_page(client):
    current_site = mock_site(things=[], get_many=[])

    response = client.get("/tags?type=nope&page=abc")

    assert response.status_code == 200
    assert "No tags found." in response.text
    current_site.things.assert_called_once_with({"type": "/type/tag", "limit": 21, "offset": 0})


def test_tags_index_offers_the_next_page(client):
    mock_site(things=[f"/tags/OL{i}T" for i in range(21)], get_many=[tag_doc(key=f"/tags/OL{i}T") for i in range(20)])

    response = client.get("/tags")

    assert 'href="/tags?page=2">Next »</a>' in response.text


def test_webpy_tags_index_renders_the_same_body(monkeypatch, request_context_fixture):
    request_context_fixture(lang="en")
    current_site = MagicMock()
    current_site.things.return_value = ["/tags/OL1T"]
    current_site.get_many.return_value = [tag_doc()]
    monkeypatch.setattr(addtag, "site", MagicMock(get=MagicMock(return_value=current_site)))
    for key, value in {"path": "/tags", "env": {"QUERY_STRING": "", "REQUEST_METHOD": "GET"}}.items():
        monkeypatch.setattr(web.ctx, key, value, raising=False)

    result = addtag.tags_index().GET()

    assert str(result) == render_jinja_template(
        "type/tag/index.html.jinja",
        tags=[tag_doc()],
        page=1,
        has_next=False,
        tag_type=None,
        tag_types=addtag.TAG_TYPES,
        subject_tag_types=addtag.SUBJECT_SUB_TYPES,
    )
    assert result.title == "Tags"
