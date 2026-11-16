"""Tests for GET /partials/ReadersAlsoRead.json — the book page's "Readers also read" row."""

from unittest.mock import AsyncMock, patch

URL = "/partials/ReadersAlsoRead.json"


class TestReadersAlsoReadPartial:
    def test_takes_the_config_lazy_carousel_sends(self, fastapi_client):
        """lazy-carousel.js sends every config key, ``key`` included, as a query param."""
        with patch("openlibrary.fastapi.partials.ReadersAlsoReadPartial.generate_async", AsyncMock(return_value={"partials": "<div/>"})) as generate:
            response = fastapi_client.get(URL, params={"work_key": "/works/OL1W", "key": "readers-also-read"})

        assert response.status_code == 200
        assert response.json() == {"partials": "<div/>"}
        assert generate.await_args.kwargs["params"].work_key == "/works/OL1W"

    def test_a_work_without_related_works_is_empty_not_an_error(self, fastapi_client):
        with patch("openlibrary.plugins.openlibrary.partials.gather_readers_also_read_async", AsyncMock(return_value=[])):
            response = fastapi_client.get(URL, params={"work_key": "/works/OL1W"})

        assert response.status_code == 200
        assert response.json() == {"partials": ""}

    def test_rejects_anything_that_is_not_a_work_key(self, fastapi_client):
        response = fastapi_client.get(URL, params={"work_key": "/books/OL1M"})
        assert response.status_code == 422
