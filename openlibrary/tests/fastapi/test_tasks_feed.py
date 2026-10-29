"""Tests for the /tasks/feed.json endpoint."""

from __future__ import annotations

from unittest.mock import patch


def test_recent_feed_passes_the_offset_through(fastapi_client):
    with patch("openlibrary.fastapi.tasks.feed.recent_rows", return_value=[]) as recent_rows:
        response = fastapi_client.get("/tasks/feed.json", params={"offset": "40", "limit": 5})
    assert response.status_code == 200
    assert response.json() == {"rows": []}
    assert recent_rows.call_args.args == (5, 40)


def test_feed_rejects_oversize_limit(fastapi_client):
    assert fastapi_client.get("/tasks/feed.json", params={"limit": 500}).status_code == 422
