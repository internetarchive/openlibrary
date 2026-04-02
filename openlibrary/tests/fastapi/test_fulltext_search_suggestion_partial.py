"""Tests for GET /partials/FulltextSearchSuggestion.json (FastAPI)."""

from unittest.mock import AsyncMock, patch

import pytest

SAMPLE_SEARCH_RESPONSE_WITH_HITS = {
    "hits": {
        "hits": [
            {"fields": {"identifier": ["test-book"]}}
        ]
    }
}

SAMPLE_SEARCH_RESPONSE_NO_HITS: dict = {
    "hits": {
        "hits": []
    }
}


@pytest.fixture
def mock_fulltext_search_async():
    """Prevent real IA search calls for fulltext_search_async."""
    with patch(
        "openlibrary.plugins.openlibrary.partials.fulltext_search_async",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = SAMPLE_SEARCH_RESPONSE_NO_HITS
        yield mock


class TestFulltextSearchSuggestionPartial:
    def test_returns_partials_key(self, fastapi_client, mock_fulltext_search_async):
        response = fastapi_client.get(
            "/partials/FulltextSearchSuggestion.json",
            params={"data": "python"},
        )
        assert response.status_code == 200
        assert "partials" in response.json()
        mock_fulltext_search_async.assert_awaited_once_with("python")

    def test_no_hits_returns_empty_div(self, fastapi_client, mock_fulltext_search_async):
        mock_fulltext_search_async.return_value = SAMPLE_SEARCH_RESPONSE_NO_HITS
        response = fastapi_client.get(
            "/partials/FulltextSearchSuggestion.json",
            params={"data": "python"},
        )
        assert response.status_code == 200
        assert response.json()["partials"] == "<div></div>"

    def test_missing_data_returns_422(self, fastapi_client, mock_fulltext_search_async):
        response = fastapi_client.get("/partials/FulltextSearchSuggestion.json")
        assert response.status_code == 422
        mock_fulltext_search_async.assert_not_called()
