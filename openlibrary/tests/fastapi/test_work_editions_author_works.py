"""Tests for the FastAPI work editions and author works endpoints."""

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import urlencode

import pytest
import web

from openlibrary.plugins.openlibrary import api as legacy_api


def make_doc(key: str, type_key: str, **attrs):
    return SimpleNamespace(key=key, type=SimpleNamespace(key=type_key), **attrs)


def make_site(doc, keys, entries):
    current_site = Mock()
    current_site.get.return_value = doc
    current_site.things.return_value = keys
    current_site.get_many.return_value = entries
    return current_site


def changequery(path: str, query: dict[str, str], **kw) -> str:
    updated = dict(query)
    for key, value in kw.items():
        if value is None:
            updated.pop(key, None)
        else:
            updated[key] = str(value)

    if updated:
        return f"{path}?{urlencode(updated)}"
    return path


def mock_web_input_func(data):
    def _mock_web_input(*args, **kwargs):
        return web.storage(kwargs | data)

    return _mock_web_input


def legacy_get_work_editions_json(current_site, data=None):
    data = data or {}
    path = "/works/OL123W/editions.json"
    fullpath = path if not data else f"{path}?{urlencode(data)}"
    ctx = web.storage(site=current_site, path=path, fullpath=fullpath)

    with (
        patch("openlibrary.plugins.openlibrary.api.web.ctx", ctx),
        patch("openlibrary.plugins.openlibrary.api.web.input", side_effect=mock_web_input_func(data)),
        patch("openlibrary.plugins.openlibrary.api.web.changequery", side_effect=lambda **kw: changequery(path, data, **kw)),
        pytest.deprecated_call(match="migrated to fastapi"),
    ):
        return json.loads(legacy_api.work_editions().GET("/works/OL123W")["rawtext"])


def legacy_get_author_works_json(current_site, data=None):
    data = data or {}
    path = "/authors/OL456A/works.json"
    fullpath = path if not data else f"{path}?{urlencode(data)}"
    ctx = web.storage(site=current_site, path=path, fullpath=fullpath)

    with (
        patch("openlibrary.plugins.openlibrary.api.web.ctx", ctx),
        patch("openlibrary.plugins.openlibrary.api.web.input", side_effect=mock_web_input_func(data)),
        patch("openlibrary.plugins.openlibrary.api.web.changequery", side_effect=lambda **kw: changequery(path, data, **kw)),
        pytest.deprecated_call(match="migrated to fastapi"),
    ):
        return json.loads(legacy_api.author_works().GET("/authors/OL456A")["rawtext"])


class TestWorkEditions:
    def test_work_editions_uses_default_pagination(self, fastapi_client):
        work = make_doc("/works/OL123W", "/type/work", edition_count=1)
        entries = [{"key": "/books/OL1M", "title": "Test Edition"}]
        current_site = make_site(work, ["/books/OL1M"], entries)

        with patch("openlibrary.fastapi.internal.api.site") as site_context:
            site_context.get.return_value = current_site
            response = fastapi_client.get("/works/OL123W/editions.json")

        assert response.status_code == 200
        assert response.json() == {
            "links": {
                "self": "/works/OL123W/editions.json",
                "work": "/works/OL123W",
            },
            "size": 1,
            "entries": entries,
        }
        current_site.get.assert_called_once_with("/works/OL123W")
        current_site.things.assert_called_once_with(
            {
                "type": "/type/edition",
                "works": "/works/OL123W",
                "limit": 50,
                "offset": 0,
            }
        )
        current_site.get_many.assert_called_once_with(["/books/OL1M"], raw=True)

    def test_work_editions_caps_limit_and_preserves_legacy_links(self, fastapi_client):
        work = make_doc("/works/OL123W", "/type/work", edition_count=2000)
        entries = [{"key": "/books/OL1M"}]
        current_site = make_site(work, ["/books/OL1M"], entries)

        with patch("openlibrary.fastapi.internal.api.site") as site_context:
            site_context.get.return_value = current_site
            response = fastapi_client.get("/works/OL123W/editions.json?limit=5000&offset=25")

        assert response.status_code == 200
        assert response.json()["links"] == {
            "self": "/works/OL123W/editions.json?limit=5000&offset=25",
            "work": "/works/OL123W",
            "prev": "/works/OL123W/editions.json?limit=5000&offset=-975",
            "next": "/works/OL123W/editions.json?limit=5000&offset=1025",
        }
        current_site.things.assert_called_once_with(
            {
                "type": "/type/edition",
                "works": "/works/OL123W",
                "limit": 1000,
                "offset": 25,
            }
        )

    def test_work_editions_falls_back_for_invalid_pagination(self, fastapi_client):
        work = make_doc("/works/OL123W", "/type/work", edition_count=0)
        current_site = make_site(work, [], [])

        with patch("openlibrary.fastapi.internal.api.site") as site_context:
            site_context.get.return_value = current_site
            response = fastapi_client.get("/works/OL123W/editions.json?limit=abc&offset=xyz")

        assert response.status_code == 200
        current_site.things.assert_called_once_with(
            {
                "type": "/type/edition",
                "works": "/works/OL123W",
                "limit": 50,
                "offset": 0,
            }
        )

    @pytest.mark.parametrize("doc", [None, make_doc("/authors/OL1A", "/type/author")])
    def test_work_editions_returns_legacy_json_404(self, fastapi_client, doc):
        current_site = make_site(doc, [], [])

        with patch("openlibrary.fastapi.internal.api.site") as site_context:
            site_context.get.return_value = current_site
            response = fastapi_client.get("/works/OL123W/editions.json")

        assert response.status_code == 404
        assert response.json() == {}
        current_site.things.assert_not_called()
        current_site.get_many.assert_not_called()

    def test_work_editions_allows_zero_id_and_returns_legacy_json_404(self, fastapi_client):
        current_site = make_site(None, [], [])

        with patch("openlibrary.fastapi.internal.api.site") as site_context:
            site_context.get.return_value = current_site
            response = fastapi_client.get("/works/OL0W/editions.json")

        assert response.status_code == 404
        assert response.json() == {}
        current_site.get.assert_called_once_with("/works/OL0W")
        current_site.things.assert_not_called()
        current_site.get_many.assert_not_called()

    def test_work_editions_response_matches_legacy(self, fastapi_client):
        work = make_doc("/works/OL123W", "/type/work", edition_count=2)
        entries = [{"key": "/books/OL1M"}]
        data = {"limit": "1", "offset": "0"}

        legacy_site = make_site(work, ["/books/OL1M"], entries)
        legacy_response = legacy_get_work_editions_json(legacy_site, data)

        fastapi_site = make_site(work, ["/books/OL1M"], entries)
        with patch("openlibrary.fastapi.internal.api.site") as site_context:
            site_context.get.return_value = fastapi_site
            fastapi_response = fastapi_client.get("/works/OL123W/editions.json?limit=1&offset=0")

        assert fastapi_response.status_code == 200
        assert fastapi_response.json() == legacy_response


class TestAuthorWorks:
    def test_author_works_uses_default_pagination_and_work_count(self, fastapi_client):
        author = make_doc("/authors/OL456A", "/type/author", get_work_count=Mock(return_value=1))
        entries = [{"key": "/works/OL1W", "title": "Test Work"}]
        current_site = make_site(author, ["/works/OL1W"], entries)

        with patch("openlibrary.fastapi.internal.api.site") as site_context:
            site_context.get.return_value = current_site
            response = fastapi_client.get("/authors/OL456A/works.json")

        assert response.status_code == 200
        assert response.json() == {
            "links": {
                "self": "/authors/OL456A/works.json",
                "author": "/authors/OL456A",
            },
            "size": 1,
            "entries": entries,
        }
        current_site.get.assert_called_once_with("/authors/OL456A")
        current_site.things.assert_called_once_with(
            {
                "type": "/type/work",
                "authors": {"author": {"key": "/authors/OL456A"}},
                "limit": 50,
                "offset": 0,
            }
        )
        current_site.get_many.assert_called_once_with(["/works/OL1W"], raw=True)
        author.get_work_count.assert_called_once_with()

    def test_author_works_caps_limit_and_preserves_legacy_links(self, fastapi_client):
        author = make_doc("/authors/OL456A", "/type/author", get_work_count=Mock(return_value=2000))
        entries = [{"key": "/works/OL1W"}]
        current_site = make_site(author, ["/works/OL1W"], entries)

        with patch("openlibrary.fastapi.internal.api.site") as site_context:
            site_context.get.return_value = current_site
            response = fastapi_client.get("/authors/OL456A/works.json?limit=5000&offset=25")

        assert response.status_code == 200
        assert response.json()["links"] == {
            "self": "/authors/OL456A/works.json?limit=5000&offset=25",
            "author": "/authors/OL456A",
            "prev": "/authors/OL456A/works.json?limit=5000&offset=-975",
            "next": "/authors/OL456A/works.json?limit=5000&offset=1025",
        }
        current_site.things.assert_called_once_with(
            {
                "type": "/type/work",
                "authors": {"author": {"key": "/authors/OL456A"}},
                "limit": 1000,
                "offset": 25,
            }
        )

    def test_author_works_accepts_zero_limit_like_legacy(self, fastapi_client):
        author = make_doc("/authors/OL456A", "/type/author", get_work_count=Mock(return_value=0))
        current_site = make_site(author, [], [])

        with patch("openlibrary.fastapi.internal.api.site") as site_context:
            site_context.get.return_value = current_site
            response = fastapi_client.get("/authors/OL456A/works.json?limit=0&offset=0")

        assert response.status_code == 200
        current_site.things.assert_called_once_with(
            {
                "type": "/type/work",
                "authors": {"author": {"key": "/authors/OL456A"}},
                "limit": 0,
                "offset": 0,
            }
        )

    @pytest.mark.parametrize("doc", [None, make_doc("/works/OL1W", "/type/work")])
    def test_author_works_returns_legacy_json_404(self, fastapi_client, doc):
        current_site = make_site(doc, [], [])

        with patch("openlibrary.fastapi.internal.api.site") as site_context:
            site_context.get.return_value = current_site
            response = fastapi_client.get("/authors/OL456A/works.json")

        assert response.status_code == 404
        assert response.json() == {}
        current_site.things.assert_not_called()
        current_site.get_many.assert_not_called()

    def test_author_works_allows_zero_id_and_returns_legacy_json_404(self, fastapi_client):
        current_site = make_site(None, [], [])

        with patch("openlibrary.fastapi.internal.api.site") as site_context:
            site_context.get.return_value = current_site
            response = fastapi_client.get("/authors/OL0A/works.json")

        assert response.status_code == 404
        assert response.json() == {}
        current_site.get.assert_called_once_with("/authors/OL0A")
        current_site.things.assert_not_called()
        current_site.get_many.assert_not_called()

    def test_author_works_response_matches_legacy(self, fastapi_client):
        author = make_doc("/authors/OL456A", "/type/author", get_work_count=Mock(return_value=2))
        entries = [{"key": "/works/OL1W"}]
        data = {"limit": "1", "offset": "0"}

        legacy_site = make_site(author, ["/works/OL1W"], entries)
        legacy_response = legacy_get_author_works_json(legacy_site, data)

        fastapi_site = make_site(author, ["/works/OL1W"], entries)
        with patch("openlibrary.fastapi.internal.api.site") as site_context:
            site_context.get.return_value = fastapi_site
            fastapi_response = fastapi_client.get("/authors/OL456A/works.json?limit=1&offset=0")

        assert fastapi_response.status_code == 200
        assert fastapi_response.json() == legacy_response
