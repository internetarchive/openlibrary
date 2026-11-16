"""Tests for the /stats/tasks.json endpoint."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch


def test_series_line_up_with_one_entry_per_calendar_day(fastapi_client):
    today = date.today()
    yesterday = today - timedelta(days=1)
    # The day before yesterday was never gathered; yesterday has the daily keys, today only some.
    docs = {
        yesterday.isoformat(): {
            "catalog_editors_1d": 140,
            "tasks_saves_1d": 3,
            "tasks_saves_by_field_1d": {"covers": 2, "lccn": 1},
            "initiative_slug": "most-read-2026-11",
            "initiative_open_gaps": 900,
        },
        today.isoformat(): {"catalog_editors_1d": 61, "initiatives": {"most-read-2026-11": {"open": 880}, "fiction-2026-11": {"open": 40}}},
    }
    with patch("openlibrary.fastapi.stats._count_docs_by_day", return_value=docs):
        response = fastapi_client.get("/stats/tasks.json", params={"days": 3})
    assert response.status_code == 200
    body = response.json()
    assert body["dates"] == [(today - timedelta(days=2)).isoformat(), yesterday.isoformat(), today.isoformat()]
    assert body["series"]["catalog_editors_1d"] == [None, 140, 61]
    assert body["series"]["tasks_saves_1d"] == [None, 3, None]
    assert body["series"]["catalog_edits"] == [None, None, None]
    assert body["saves_by_field"] == [None, {"covers": 2, "lccn": 1}, None]
    # Yesterday's doc predates per-initiative snapshots, so its flat keys still read as the headline initiative's.
    assert body["initiatives"] == {"most-read-2026-11": [None, 900, 880], "fiction-2026-11": [None, None, 40]}


def test_series_rejects_more_than_the_cached_range(fastapi_client):
    assert fastapi_client.get("/stats/tasks.json", params={"days": 401}).status_code == 422
    assert fastapi_client.get("/stats/tasks.json", params={"days": 0}).status_code == 422
