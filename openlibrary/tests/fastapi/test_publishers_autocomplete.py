"""Tests for /publishers/_autocomplete, which ol-autocomplete asks for publisher names as someone types."""

from __future__ import annotations

from unittest.mock import patch

ROWS = [{"value": "Penguin Books", "count": 51}, {"value": "Penguin", "count": 19}]


def test_suggestions_come_back_as_a_list_with_counts(fastapi_client):
    with patch("openlibrary.fastapi.publishers.suggest_publishers", return_value=ROWS) as suggest:
        response = fastapi_client.get("/publishers/_autocomplete", params={"q": "peng", "limit": 5})
    assert response.status_code == 200
    assert response.json() == ROWS
    assert suggest.call_args.args == ("peng", 5)


def test_it_is_not_taken_for_a_publisher_page(fastapi_client):
    with patch("openlibrary.fastapi.publishers.suggest_publishers", return_value=[]):
        assert fastapi_client.get("/publishers/_autocomplete").json() == []


def test_an_overlong_query_or_limit_is_refused(fastapi_client):
    assert fastapi_client.get("/publishers/_autocomplete", params={"q": "p" * 101}).status_code == 422
    assert fastapi_client.get("/publishers/_autocomplete", params={"q": "peng", "limit": 500}).status_code == 422
