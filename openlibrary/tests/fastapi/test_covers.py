"""Tests for the cover manager endpoints in openlibrary/fastapi/covers.py."""

from unittest.mock import MagicMock

import pytest
import web

from openlibrary.utils.request_context import RequestContextVars, req_context, site

STATE: dict = {"key": "/books/OL1M", "current": None, "items": []}


@pytest.fixture
def doc(monkeypatch):
    """An edition the current (writing) user may edit."""
    fake_site = MagicMock()
    edition = MagicMock(key="/books/OL1M", type=web.storage(key="/type/edition"))
    fake_site.get.return_value = edition
    fake_site.can_write.return_value = True
    site.set(fake_site)
    req_context.set(RequestContextVars(x_forwarded_for="1.2.3.4", user_agent=None, lang="en", solr_editions=True, print_disabled=False))
    user = MagicMock(key="/people/testuser", displayname="Test User")
    user.is_read_only.return_value = False
    monkeypatch.setattr("openlibrary.fastapi.covers.get_current_user", lambda: user)
    monkeypatch.setattr("openlibrary.fastapi.covers.cover_manager_state", lambda d: STATE)
    return edition


def test_requires_login(fastapi_client, doc):
    assert fastapi_client.get("/books/OL1M/covers.json").status_code == 401


def test_lists_images(fastapi_client, mock_authenticated_user, doc):
    response = fastapi_client.get("/books/OL1M/covers.json")
    assert response.status_code == 200
    assert response.json() == STATE


def test_only_books_works_and_authors(fastapi_client, mock_authenticated_user, doc):
    doc.type = web.storage(key="/type/page")
    assert fastapi_client.get("/books/OL1M/covers.json").status_code == 404


def test_read_only_patrons_cannot_save(fastapi_client, mock_authenticated_user, doc, monkeypatch):
    user = MagicMock()
    user.is_read_only.return_value = True
    monkeypatch.setattr("openlibrary.fastapi.covers.get_current_user", lambda: user)
    assert fastapi_client.post("/books/OL1M/covers.json", json={"selected": "img:1"}).status_code == 403


def test_save(fastapi_client, mock_authenticated_user, doc, monkeypatch):
    calls = []
    monkeypatch.setattr("openlibrary.fastapi.covers.apply_cover_changes", lambda *args: calls.append(args) or 7)
    response = fastapi_client.post("/books/OL1M/covers.json", json={"selected": "img:7", "added": [7], "removed": [3]})
    assert response.status_code == 200
    assert response.json() == {"cover_id": 7, "state": STATE}
    assert calls[0][1:4] == ("img:7", [7], [3])
    assert calls[0][5] == "1.2.3.4"


@pytest.mark.parametrize(("error", "code"), [(ValueError("not this book's image"), 400), (RuntimeError("coverstore down"), 502)])
def test_save_errors(fastapi_client, mock_authenticated_user, doc, monkeypatch, error, code):
    def fail(*args):
        raise error

    monkeypatch.setattr("openlibrary.fastapi.covers.apply_cover_changes", fail)
    response = fastapi_client.post("/books/OL1M/covers.json", json={"selected": "img:7"})
    assert response.status_code == code
    assert response.json()["detail"] == str(error)


def test_upload_rejects_non_images(fastapi_client, mock_authenticated_user, doc):
    response = fastapi_client.post("/books/OL1M/covers/upload.json", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported file extension"
