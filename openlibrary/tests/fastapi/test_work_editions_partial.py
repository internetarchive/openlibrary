"""Tests for GET /partials/WorkEditions.json — the editions that count as one book for lists."""

from unittest.mock import patch

URL = "/partials/WorkEditions.json"


class TestWorkEditionsPartial:
    def test_returns_the_works_edition_olids(self, fastapi_client):
        doc = {"/works/OL1W": {"key": "/works/OL1W", "edition_key": ["OL9M", "OL8M"]}}
        with patch("openlibrary.plugins.openlibrary.partials.get_solr_works", return_value=doc) as get_works:
            response = fastapi_client.get(URL, params={"work_id": "OL1W"})

        assert response.status_code == 200
        assert response.json() == {"editions": ["OL9M", "OL8M"]}
        get_works.assert_called_once_with({"/works/OL1W"}, fields={"key", "edition_key"})

    def test_a_work_with_no_editions_is_empty_not_an_error(self, fastapi_client):
        doc = {"/works/OL1W": {"key": "/works/OL1W"}}
        with patch("openlibrary.plugins.openlibrary.partials.get_solr_works", return_value=doc):
            response = fastapi_client.get(URL, params={"work_id": "OL1W"})

        assert response.status_code == 200
        assert response.json() == {"editions": []}

    def test_a_work_solr_does_not_have_is_empty_not_an_error(self, fastapi_client):
        with patch("openlibrary.plugins.openlibrary.partials.get_solr_works", return_value={}):
            response = fastapi_client.get(URL, params={"work_id": "OL1W"})

        assert response.status_code == 200
        assert response.json() == {"editions": []}

    def test_rejects_anything_that_is_not_a_work_olid(self, fastapi_client):
        response = fastapi_client.get(URL, params={"work_id": "OL2M"})
        assert response.status_code == 422
        assert "OL2M" in response.text

    def test_needs_no_reader(self, fastapi_client):
        """Not reader-specific: the same answer for everyone, signed in or not."""
        with patch("openlibrary.plugins.openlibrary.partials.get_solr_works", return_value={}):
            response = fastapi_client.get(URL, params={"work_id": "OL1W"})
        assert response.status_code == 200
