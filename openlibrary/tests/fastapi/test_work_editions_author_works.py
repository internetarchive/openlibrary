"""Tests for the FastAPI work editions and author works endpoints."""

from unittest.mock import Mock, patch

import pytest
from starlette.datastructures import URL

from openlibrary.plugins.openlibrary import api as legacy_api


def make_test_site(
    doc_key: str,
    doc_type: str,
    thing_keys: list[str] | None = None,
    entries: list[dict] | None = None,
    **doc_attrs,
) -> Mock:
    """Create a mock site with a doc, thing query results, and get_many entries."""
    doc = Mock(key=doc_key, type=Mock(key=doc_type), spec=[])
    for k, v in doc_attrs.items():
        setattr(doc, k, v)
    current_site = Mock()
    current_site.get.return_value = doc
    current_site.things.return_value = thing_keys or []
    current_site.get_many.return_value = entries or []
    return current_site


@pytest.fixture
def patched_site():
    with patch("openlibrary.plugins.openlibrary.api.site") as m:
        yield m


class TestWorkEditions:
    DOC_KEY = "/works/OL123W"
    DOC_TYPE = "/type/work"
    ENDPOINT = "/works/OL123W/editions.json"
    LINK_KEY = "work"

    def _things_query(self, limit, offset):
        return {
            "type": "/type/edition",
            "works": self.DOC_KEY,
            "limit": limit,
            "offset": offset,
        }

    def test_uses_default_pagination(self, fastapi_client, patched_site):
        entries = [{"key": "/books/OL1M", "title": "Test Edition"}]
        current_site = make_test_site(self.DOC_KEY, self.DOC_TYPE, edition_count=1, thing_keys=["/books/OL1M"], entries=entries)
        patched_site.get.return_value = current_site
        response = fastapi_client.get(self.ENDPOINT)

        assert response.status_code == 200
        assert response.json() == {
            "links": {"self": self.ENDPOINT, self.LINK_KEY: self.DOC_KEY},
            "size": 1,
            "entries": entries,
        }
        current_site.things.assert_called_once_with(self._things_query(50, 0))
        current_site.get_many.assert_called_once_with(["/books/OL1M"], raw=True)

    def test_caps_limit_and_preserves_legacy_links(self, fastapi_client, patched_site):
        entries = [{"key": "/books/OL1M"}]
        current_site = make_test_site(self.DOC_KEY, self.DOC_TYPE, edition_count=2000, thing_keys=["/books/OL1M"], entries=entries)
        patched_site.get.return_value = current_site
        response = fastapi_client.get(f"{self.ENDPOINT}?limit=1000&offset=25")

        assert response.status_code == 200
        assert response.json() == {
            "links": {
                "self": f"{self.ENDPOINT}?limit=1000&offset=25",
                self.LINK_KEY: self.DOC_KEY,
                "prev": f"{self.ENDPOINT}?limit=1000&offset=0",
                "next": f"{self.ENDPOINT}?limit=1000&offset=1025",
            },
            "size": 2000,
            "entries": entries,
        }
        current_site.things.assert_called_once_with(self._things_query(1000, 25))

    def test_rejects_invalid_pagination(self, fastapi_client, patched_site):
        current_site = make_test_site(self.DOC_KEY, self.DOC_TYPE, edition_count=0)
        patched_site.get.return_value = current_site
        response = fastapi_client.get(f"{self.ENDPOINT}?limit=abc&offset=xyz")

        assert response.status_code == 422
        current_site.get.assert_not_called()

    def test_zero_limit_defaults_to_50(self, fastapi_client, patched_site):
        entries = [{"key": "/books/OL1M"}]
        current_site = make_test_site(self.DOC_KEY, self.DOC_TYPE, edition_count=1, thing_keys=["/books/OL1M"], entries=entries)
        patched_site.get.return_value = current_site
        response = fastapi_client.get(f"{self.ENDPOINT}?limit=0")

        assert response.status_code == 200
        assert response.json() == {
            "links": {"self": f"{self.ENDPOINT}?limit=0", self.LINK_KEY: self.DOC_KEY},
            "size": 1,
            "entries": entries,
        }
        current_site.things.assert_called_once_with(self._things_query(50, 0))

    def test_rejects_negative_offset(self, fastapi_client, patched_site):
        current_site = make_test_site(self.DOC_KEY, self.DOC_TYPE, edition_count=0)
        patched_site.get.return_value = current_site
        response = fastapi_client.get(f"{self.ENDPOINT}?limit=10&offset=-5")

        assert response.status_code == 422
        current_site.get.assert_not_called()

    @pytest.mark.parametrize("doc_key", [None, "/authors/OL1A"])
    def test_returns_404_for_missing_or_wrong_type(self, fastapi_client, doc_key, patched_site):
        if doc_key is None:
            current_site = make_test_site(self.DOC_KEY, self.DOC_TYPE)
            current_site.get.return_value = None
        else:
            current_site = make_test_site(doc_key, "/type/author")
        patched_site.get.return_value = current_site
        response = fastapi_client.get(self.ENDPOINT)

        assert response.status_code == 404
        current_site.things.assert_not_called()

    def test_allows_zero_olid_but_returns_404(self, fastapi_client, patched_site):
        current_site = make_test_site(self.DOC_KEY, self.DOC_TYPE)
        current_site.get.return_value = None
        patched_site.get.return_value = current_site
        response = fastapi_client.get("/works/OL0W/editions.json")

        assert response.status_code == 404
        current_site.get.assert_called_once_with("/works/OL0W")
        current_site.things.assert_not_called()

    def test_response_matches_legacy(self, fastapi_client, patched_site):
        entries = [{"key": "/books/OL1M"}]

        legacy_site = make_test_site(self.DOC_KEY, self.DOC_TYPE, edition_count=2, thing_keys=["/books/OL1M"], entries=entries)
        patched_site.get.return_value = legacy_site
        legacy_response = legacy_api.work_editions.get_editions_data(
            self.DOC_KEY,
            url=URL(f"{self.ENDPOINT}?limit=1&offset=0"),
            limit=1,
            offset=0,
        )

        fastapi_site = make_test_site(self.DOC_KEY, self.DOC_TYPE, edition_count=2, thing_keys=["/books/OL1M"], entries=entries)
        patched_site.get.return_value = fastapi_site
        fastapi_response = fastapi_client.get(f"{self.ENDPOINT}?limit=1&offset=0")

        assert fastapi_response.status_code == 200
        assert fastapi_response.json() == legacy_response


class TestAuthorWorks:
    DOC_KEY = "/authors/OL456A"
    DOC_TYPE = "/type/author"
    ENDPOINT = "/authors/OL456A/works.json"
    LINK_KEY = "author"

    def _things_query(self, limit, offset):
        return {
            "type": "/type/work",
            "authors": {"author": {"key": self.DOC_KEY}},
            "limit": limit,
            "offset": offset,
        }

    def test_uses_default_pagination(self, fastapi_client, patched_site):
        entries = [{"key": "/works/OL1W", "title": "Test Work"}]
        current_site = make_test_site(self.DOC_KEY, self.DOC_TYPE, get_work_count=Mock(return_value=1), thing_keys=["/works/OL1W"], entries=entries)
        patched_site.get.return_value = current_site
        response = fastapi_client.get(self.ENDPOINT)

        assert response.status_code == 200
        assert response.json() == {
            "links": {"self": self.ENDPOINT, self.LINK_KEY: self.DOC_KEY},
            "size": 1,
            "entries": entries,
        }
        current_site.things.assert_called_once_with(self._things_query(50, 0))
        current_site.get_many.assert_called_once_with(["/works/OL1W"], raw=True)
        current_site.get.return_value.get_work_count.assert_called_once_with()

    def test_caps_limit_and_preserves_legacy_links(self, fastapi_client, patched_site):
        entries = [{"key": "/works/OL1W"}]
        current_site = make_test_site(self.DOC_KEY, self.DOC_TYPE, get_work_count=Mock(return_value=2000), thing_keys=["/works/OL1W"], entries=entries)
        patched_site.get.return_value = current_site
        response = fastapi_client.get(f"{self.ENDPOINT}?limit=1000&offset=25")

        assert response.status_code == 200
        assert response.json() == {
            "links": {
                "self": f"{self.ENDPOINT}?limit=1000&offset=25",
                self.LINK_KEY: self.DOC_KEY,
                "prev": f"{self.ENDPOINT}?limit=1000&offset=0",
                "next": f"{self.ENDPOINT}?limit=1000&offset=1025",
            },
            "size": 2000,
            "entries": entries,
        }
        current_site.things.assert_called_once_with(self._things_query(1000, 25))

    def test_zero_limit_passed_through(self, fastapi_client, patched_site):
        entries = [{"key": "/works/OL1W"}]
        current_site = make_test_site(self.DOC_KEY, self.DOC_TYPE, get_work_count=Mock(return_value=1), thing_keys=["/works/OL1W"], entries=entries)
        patched_site.get.return_value = current_site
        response = fastapi_client.get(f"{self.ENDPOINT}?limit=0&offset=0")

        assert response.status_code == 200
        assert response.json() == {
            "links": {"self": f"{self.ENDPOINT}?limit=0&offset=0", self.LINK_KEY: self.DOC_KEY},
            "size": 1,
            "entries": entries,
        }
        current_site.things.assert_called_once_with(self._things_query(0, 0))

    def test_rejects_invalid_pagination(self, fastapi_client, patched_site):
        current_site = make_test_site(self.DOC_KEY, self.DOC_TYPE, get_work_count=Mock(return_value=0))
        patched_site.get.return_value = current_site
        response = fastapi_client.get(f"{self.ENDPOINT}?limit=abc&offset=xyz")

        assert response.status_code == 422
        current_site.get.assert_not_called()

    def test_rejects_negative_offset(self, fastapi_client, patched_site):
        current_site = make_test_site(self.DOC_KEY, self.DOC_TYPE, get_work_count=Mock(return_value=0))
        patched_site.get.return_value = current_site
        response = fastapi_client.get(f"{self.ENDPOINT}?limit=10&offset=-5")

        assert response.status_code == 422
        current_site.get.assert_not_called()

    @pytest.mark.parametrize("doc_key", [None, "/works/OL1W"])
    def test_returns_404_for_missing_or_wrong_type(self, fastapi_client, doc_key, patched_site):
        if doc_key is None:
            current_site = make_test_site(self.DOC_KEY, self.DOC_TYPE)
            current_site.get.return_value = None
        else:
            current_site = make_test_site(doc_key, "/type/work")
        patched_site.get.return_value = current_site
        response = fastapi_client.get(self.ENDPOINT)

        assert response.status_code == 404
        current_site.things.assert_not_called()

    def test_allows_zero_olid_but_returns_404(self, fastapi_client, patched_site):
        current_site = make_test_site(self.DOC_KEY, self.DOC_TYPE)
        current_site.get.return_value = None
        patched_site.get.return_value = current_site
        response = fastapi_client.get("/authors/OL0A/works.json")

        assert response.status_code == 404
        current_site.get.assert_called_once_with("/authors/OL0A")
        current_site.things.assert_not_called()

    def test_response_matches_legacy(self, fastapi_client, patched_site):
        entries = [{"key": "/works/OL1W"}]

        legacy_site = make_test_site(self.DOC_KEY, self.DOC_TYPE, get_work_count=Mock(return_value=2), thing_keys=["/works/OL1W"], entries=entries)
        patched_site.get.return_value = legacy_site
        legacy_response = legacy_api.author_works.get_works_data(
            self.DOC_KEY,
            url=URL(f"{self.ENDPOINT}?limit=1&offset=0"),
            limit=1,
            offset=0,
        )

        fastapi_site = make_test_site(self.DOC_KEY, self.DOC_TYPE, get_work_count=Mock(return_value=2), thing_keys=["/works/OL1W"], entries=entries)
        patched_site.get.return_value = fastapi_site
        fastapi_response = fastapi_client.get(f"{self.ENDPOINT}?limit=1&offset=0")

        assert fastapi_response.status_code == 200
        assert fastapi_response.json() == legacy_response
