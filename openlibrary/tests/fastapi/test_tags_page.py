"""`/tags`, `/tag/add` and `/tags/OLnT` pages on FastAPI, and their web.py handlers.

Both servers render the same Jinja templates until ops routes these paths to
FastAPI in production. The shell around the pages is tested in
`test_site_page.py`.
"""

import re
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import web
from fastapi.testclient import TestClient

from openlibrary.core.jinja import render_jinja_template
from openlibrary.core.models import Tag
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


def test_tag_page_redirects_to_the_url_with_the_name(client):
    mock_site(get=tag_doc())

    response = client.get("/tags/OL1T", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/tags/OL1T/Horror"


def test_tag_page_renders_the_tag(client):
    current_site = mock_site(get=tag_doc())

    response = client.get("/tags/OL1T/Horror")

    assert response.status_code == 200
    html = response.text
    current_site.get.assert_called_once_with("/tags/OL1T")
    assert "<title>Horror | Open Library</title>" in html
    assert '<h1 itemprop="name">' in html
    assert "<strong>Type:</strong> genre" in html
    # The description and body are markdown, sanitized to HTML
    assert "Scary stories." in html
    assert "<em>scary</em>" in html
    assert "<strong>URL Slugs</strong>" in html
    assert "horror, scary" in html
    assert 'href="/subjects/genre:horror"' in html
    assert "View subject page for Horror." in html
    # The databar's edit link and history link
    assert 'href="/tags/OL1T?m=edit"' in html
    assert 'href="/tags/OL1T/Horror?m=history"' in html


def test_tag_page_redirects_a_wrong_name_to_the_canonical_one(client):
    mock_site(get=tag_doc())

    response = client.get("/tags/OL1T/nope?x=1", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/tags/OL1T/Horror?x=1"


def test_subject_tags_link_to_the_bare_subject_page(client):
    mock_site(get=tag_doc(tag_type="subject", name="Horror Fiction"))

    html = client.get("/tags/OL1T/Horror_Fiction").text

    assert 'href="/subjects/horror_fiction"' in html


def test_unknown_tag_is_404(client):
    mock_site(get=None)

    response = client.get("/tags/OL1T/Horror")

    assert response.status_code == 404
    assert "404 - Page Not Found" in response.text
    assert "<title>/tags/OL1T is not found | Open Library</title>" in response.text


def test_a_tag_search_redirects_to_the_match(client, monkeypatch):
    found = MagicMock(return_value=["/tags/OL1T"])
    monkeypatch.setattr(Tag, "find", found)

    response = client.get("/tags/-/genre:Horror", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/tags/OL1T"
    found.assert_called_once_with("Horror", tag_type="genre")


def test_a_tag_search_without_a_match_is_404(client, monkeypatch):
    monkeypatch.setattr(Tag, "find", MagicMock(return_value=[]))

    response = client.get("/tags/-/genre:Nope")

    assert response.status_code == 404
    assert "/tags/-/genre:Nope does not exist." in response.text


def test_add_tag_sends_a_visitor_to_login(client):
    response = client.get("/tag/add", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/account/login?redirect=/tag/add"


def test_add_tag_page_requires_a_curator(client, monkeypatch):
    monkeypatch.setattr("openlibrary.fastapi.tags.get_current_user", lambda: SimpleNamespace(is_admin=lambda: False, is_curator=lambda: False))

    response = client.get("/tag/add")

    assert response.status_code == 401


def test_add_tag_page_prefills_the_name(client, monkeypatch):
    monkeypatch.setattr("openlibrary.fastapi.tags.get_current_user", lambda: SimpleNamespace(is_admin=lambda: False, is_curator=lambda: True))

    response = client.get("/tag/add?name=Cooking")

    assert response.status_code == 200
    html = response.text
    assert "<title>Add a tag | Open Library</title>" in html
    assert 'content="noindex,nofollow"' in html
    assert 'value="Cooking"' in html
    assert '<option value="">Select</option>' in html
    # Nothing is being edited, so no databar and no delete button
    assert "Delete Record" not in html


def test_edit_form_fills_in_the_tag_and_its_delete_button(request_context_fixture):
    request_context_fixture(lang="en")
    body = addtag.render_tag_form(
        name="Horror",
        slugs="horror, scary",
        tag_description="Scary stories.",
        body="A scary story.",
        tag_type="genre",
        is_editing=True,
        key="/tags/OL1T",
        can_delete=True,
        comment="Adding a slug",
    )

    assert "<title>" not in body  # the layout adds it, from the handler's title
    assert 'value="horror, scary"' in body
    assert 'href="/tags/OL1T?m=history"' in body
    assert "Delete Record" in body
    assert 'value="Adding a slug"' in body
    assert "By saving a change to this wiki" in body


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


def test_webpy_tag_view_renders_the_same_body(monkeypatch, request_context_fixture):
    request_context_fixture(lang="en")
    current_site = MagicMock()
    current_site.get.return_value = tag_doc()
    monkeypatch.setattr(addtag, "site", MagicMock(get=MagicMock(return_value=current_site)))

    result = addtag.tag_view().GET("/tags/OL1T")

    assert str(result) == addtag.render_tag_view(tag_doc())
    assert result.title == "Horror"
