"""Tests for the /tasks/feed.json endpoint."""

from __future__ import annotations

from unittest.mock import patch


def test_static_feed_rotates_the_fixture(fastapi_client):
    response = fastapi_client.get("/tasks/feed.json", params={"mode": "static", "limit": 2, "offset": 3})
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "static"
    assert [r["id"] for r in body["rows"]] == ["sample-3", "sample-4"]
    assert set(body["rows"][0]) == {"id", "key", "title", "authors", "cover_url", "kind", "action", "editor", "editor_key", "comment", "timestamp"}


def test_recent_feed_passes_the_offset_through(fastapi_client):
    with patch("openlibrary.fastapi.tasks.feed.recent_rows", return_value=[]) as recent_rows, patch("openlibrary.fastapi.tasks.site"):
        response = fastapi_client.get("/tasks/feed.json", params={"offset": "40", "limit": 5})
    assert response.status_code == 200
    assert response.json() == {"mode": "recent", "rows": []}
    assert recent_rows.call_args.args[1:] == (5, 40)


def test_feed_rejects_unknown_mode_and_oversize_limit(fastapi_client):
    assert fastapi_client.get("/tasks/feed.json", params={"mode": "fake"}).status_code == 422
    assert fastapi_client.get("/tasks/feed.json", params={"mode": "static", "limit": 500}).status_code == 422
