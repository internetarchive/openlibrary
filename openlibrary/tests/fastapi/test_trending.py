"""Tests for the /trending/{period}.json FastAPI endpoint (internal API)."""

from typing import get_args
from unittest.mock import patch

import pytest

from openlibrary.fastapi.internal.api import TrendingPeriod
from openlibrary.views.loanstats import SINCE_DAYS

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

    def test_empty_works_list(self, fastapi_client, mock_get_trending_books):
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
            (
                "fields=key,title,subtitle,author_name,author_key,cover_i,cover_edition_key",
                {"fields": ["key", "title", "subtitle", "author_name", "author_key", "cover_i", "cover_edition_key"]},
            ),
            (
                "fields=key,title,ia,ia_collection",
                {"fields": ["key", "title", "ia", "ia_collection"]},
            ),
        ],
    )
    def test_query_params_forwarded(self, fastapi_client, mock_get_trending_books, query_string, expected_kwargs):
        response = fastapi_client.get(f"/trending/daily.json?{query_string}")
        response.raise_for_status()
        for k, v in expected_kwargs.items():
            assert mock_get_trending_books.call_args.kwargs[k] == v

    @pytest.mark.parametrize(
        ("url", "description"),
        [
            ("/trending/badperiod.json", "invalid period"),
            ("/trending/daily.json?sort_by_count=maybe", "invalid boolean"),
            ("/trending/daily.json?page=0", "page zero"),
            ("/trending/daily.json?limit=1001", "limit exceeds max"),
        ],
    )
    def test_validation_errors(self, fastapi_client, mock_get_trending_books, url, description):
        assert fastapi_client.get(url).status_code == 422
        mock_get_trending_books.assert_not_called()

    @pytest.mark.parametrize(
        ("hours_param", "expected_hours"),
        [("6", 6), (None, 0)],
    )
    def test_hours_in_response(self, fastapi_client, mock_get_trending_books, hours_param, expected_hours):
        url = "/trending/daily.json"
        if hours_param:
            url += f"?hours={hours_param}"
        response = fastapi_client.get(url)
        response.raise_for_status()
        assert response.json()["hours"] == expected_hours

    def test_limit_defaults_to_100(self, fastapi_client, mock_get_trending_books):
        response = fastapi_client.get("/trending/daily.json")
        response.raise_for_status()
        assert mock_get_trending_books.call_args.kwargs["limit"] == 100

    def test_trending_period_literal_matches_since_days(self):
        literal_keys = set(get_args(TrendingPeriod))
        since_days_keys = set(SINCE_DAYS.keys())

        assert literal_keys == since_days_keys, (
            "TrendingPeriod Literal must stay in sync with views.loanstats.SINCE_DAYS keys. "
            f"Missing in Literal: {since_days_keys - literal_keys}. "
            f"Extra in Literal: {literal_keys - since_days_keys}."
        )

    def test_works_content_in_response(self, fastapi_client, mock_get_trending_books):
        response = fastapi_client.get("/trending/daily.json")
        response.raise_for_status()
        works = response.json()["works"]
        assert len(works) == 2
        assert works[0]["key"] == "/works/OL1W"
        assert works[1]["key"] == "/works/OL2W"
