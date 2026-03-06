"""Tests for the /trending/{period}.json FastAPI endpoint (internal API)."""

import os
from unittest.mock import patch

import pytest

MOCK_WORKS = [
    {"key": "/works/OL1W", "title": "Popular Book 1", "author_name": ["Author A"]},
    {"key": "/works/OL2W", "title": "Popular Book 2", "author_name": ["Author B"]},
]


@pytest.fixture
def mock_get_trending_books():
    with patch("openlibrary.fastapi.internal.api.get_trending_books", return_value=MOCK_WORKS) as mock:
        yield mock


class TestTrendingBooksEndpoint:
    """Tests for GET /trending/{period}.json."""

    @pytest.mark.parametrize(
        ("period", "expected_days"),
        [
            ("daily", 1),
            ("weekly", 7),
            ("monthly", 30),
            ("yearly", 365),
            ("forever", None),
            ("now", 0),
        ],
    )
    def test_valid_periods(self, fastapi_client, mock_get_trending_books, period, expected_days):
        response = fastapi_client.get(f"/trending/{period}.json")
        response.raise_for_status()
        data = response.json()
        assert data["query"] == f"/trending/{period}"
        # When expected_days is None (forever), 'days' shouldn't be in the response because of response_model_exclude_none=True
        if expected_days is None:
            assert "days" not in data
        else:
            assert data["days"] == expected_days
        assert isinstance(data["works"], list)

    def test_forever_omits_days_when_none(self, fastapi_client, mock_get_trending_books):
        """Forever passes since_days=None and omits days from response."""
        response = fastapi_client.get("/trending/forever.json")
        response.raise_for_status()
        data = response.json()
        assert "days" not in data  # omitted when None
        assert data["hours"] == 0

    def test_empty_works_list(self, fastapi_client, mock_get_trending_books):
        """An empty works list is returned as [] when get_trending_books returns nothing."""
        mock_get_trending_books.return_value = []
        response = fastapi_client.get("/trending/now.json")
        response.raise_for_status()
        assert response.json()["works"] == []

    @pytest.mark.parametrize(
        ("query_string", "expected_kwargs"),
        [
            ("hours=12", {"since_hours": 12}),
            ("minimum=3", {"minimum": 3}),
            ("fields=key,title", {"fields": ["key", "title"]}),
            ("sort_by_count=false", {"sort_by_count": False}),
            ("page=2&limit=10", {"page": 2, "limit": 10}),
            ("fields=key,%20title", {"fields": ["key", "title"]}),
            ("", {"sort_by_count": True, "fields": None}),
            (
                "page=3&limit=50&hours=6&sort_by_count=false&minimum=10&fields=key,title",
                {"page": 3, "limit": 50, "since_hours": 6, "sort_by_count": False, "minimum": 10, "fields": ["key", "title"]},
            ),
        ],
    )
    def test_query_params_forwarded(self, fastapi_client, mock_get_trending_books, query_string, expected_kwargs):
        """Query parameters must be forwarded to get_trending_books correctly."""
        response = fastapi_client.get(f"/trending/daily.json?{query_string}")
        response.raise_for_status()
        for k, v in expected_kwargs.items():
            assert mock_get_trending_books.call_args.kwargs[k] == v

    def test_invalid_period_returns_422(self, fastapi_client, mock_get_trending_books):
        """If someone asks for a bizarre period, we should bounce them with a 422."""
        assert fastapi_client.get("/trending/badperiod.json").status_code == 422
        mock_get_trending_books.assert_not_called()

    def test_sort_by_count_invalid_returns_422(self, fastapi_client, mock_get_trending_books):
        """Non-boolean sort_by_count value is rejected with 422."""
        response = fastapi_client.get("/trending/daily.json?sort_by_count=maybe")
        assert response.status_code == 422
        mock_get_trending_books.assert_not_called()

    def test_hours_present_in_response(self, fastapi_client, mock_get_trending_books):
        """hours value is echoed back in the response body."""
        response = fastapi_client.get("/trending/daily.json?hours=6")
        response.raise_for_status()
        assert response.json()["hours"] == 6

    def test_hours_defaults_to_zero_in_response(self, fastapi_client, mock_get_trending_books):
        """If hours is not specified, it defaults to 0 in the response."""
        response = fastapi_client.get("/trending/daily.json")
        response.raise_for_status()
        assert response.json()["hours"] == 0

    def test_page_zero_returns_422(self, fastapi_client, mock_get_trending_books):
        """page=0 is rejected — page must be >= 1."""
        assert fastapi_client.get("/trending/daily.json?page=0").status_code == 422
        mock_get_trending_books.assert_not_called()

    def test_trending_period_literal_matches_since_days(self):
        """Ensure TrendingPeriod Literal keys exactly match views.loanstats.SINCE_DAYS keys."""
        from typing import get_args

        from openlibrary.fastapi.internal.api import TrendingPeriod
        from openlibrary.views.loanstats import SINCE_DAYS

        literal_keys = set(get_args(TrendingPeriod))
        since_days_keys = set(SINCE_DAYS.keys())

        assert literal_keys == since_days_keys, (
            "TrendingPeriod Literal must stay in sync with views.loanstats.SINCE_DAYS keys. "
            f"Missing in Literal: {since_days_keys - literal_keys}. "
            f"Extra in Literal: {literal_keys - since_days_keys}."
        )

    def test_works_content_in_response(self, fastapi_client, mock_get_trending_books):
        """Works from get_trending_books are mapped through SolrWork and appear in response."""
        response = fastapi_client.get("/trending/daily.json")
        response.raise_for_status()
        works = response.json()["works"]
        assert len(works) == 2
        assert works[0]["key"] == "/works/OL1W"
        assert works[1]["key"] == "/works/OL2W"

    def test_get_trending_books_exception_returns_502(self, fastapi_client, mock_get_trending_books):
        """If get_trending_books raises, return 502."""
        mock_get_trending_books.side_effect = Exception("db error")
        response = fastapi_client.get("/trending/daily.json")
        assert response.status_code == 502


@pytest.mark.skipif(
    os.getenv("LOCAL_DEV") is None,
    reason="Trending endpoint is excluded from OpenAPI schema outside LOCAL_DEV (include_in_schema=False)",
)
class TestOpenAPIDocumentation:
    """Verify the trending endpoint is correctly described in the OpenAPI schema."""

    def test_openapi_contains_trending_endpoint(self, fastapi_client):
        """The endpoint must appear in /openapi.json so API consumers can discover it."""
        response = fastapi_client.get("/openapi.json")
        assert response.status_code == 200
        paths = response.json()["paths"]
        assert "/trending/{period}.json" in paths

    def test_openapi_trending_params_have_descriptions(self, fastapi_client):
        """Key parameters must carry descriptions (validates our Field/Query metadata)."""
        response = fastapi_client.get("/openapi.json")
        assert response.status_code == 200
        params = response.json()["paths"]["/trending/{period}.json"]["get"]["parameters"]
        by_name = {p["name"]: p for p in params}
        assert by_name["period"]["description"]
        assert by_name["hours"]["description"]
