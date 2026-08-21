"""Tests for the FastAPI patron check-ins endpoints."""

from unittest.mock import patch

from openlibrary.core.bookshelves_events import BookshelfEvent


def test_create_checkin_success(fastapi_client, mock_authenticated_user):
    payload = {
        "event_type": BookshelfEvent.START,
        "year": 2026,
        "month": 5,
        "day": 10,
        "edition_key": "OL100M",
    }
    with patch("openlibrary.fastapi.checkins.BookshelvesEvents.create_event", return_value=123) as mock_create:
        response = fastapi_client.post("/works/OL1W/check-ins", json=payload)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "id": 123}
    mock_create.assert_called_once_with("testuser", 1, 100, "2026-05-10", event_type=BookshelfEvent.START)


def test_create_checkin_invalid_month_or_day(fastapi_client, mock_authenticated_user):
    payload = {
        "event_type": BookshelfEvent.START,
        "year": 2026,
        "month": 99,
        "day": 99,
    }
    response = fastapi_client.post("/works/OL1W/check-ins", json=payload)
    assert response.status_code == 422


def test_create_checkin_invalid_calendar_date(fastapi_client, mock_authenticated_user):
    # Feb 31st is an invalid calendar date
    payload = {
        "event_type": BookshelfEvent.START,
        "year": 2026,
        "month": 2,
        "day": 31,
    }
    response = fastapi_client.post("/works/OL1W/check-ins", json=payload)
    assert response.status_code == 422


def test_create_checkin_invalid_edition_key(fastapi_client, mock_authenticated_user):
    payload = {
        "event_type": BookshelfEvent.START,
        "year": 2026,
        "month": 5,
        "day": 10,
        "edition_key": "invalid_key",
    }
    response = fastapi_client.post("/works/OL1W/check-ins", json=payload)
    assert response.status_code == 422


def test_create_checkin_invalid_work_id(fastapi_client, mock_authenticated_user):
    payload = {
        "event_type": BookshelfEvent.START,
        "year": 2026,
    }
    response = fastapi_client.post("/works/OL0W/check-ins", json=payload)
    assert response.status_code == 422


def test_delete_checkin_invalid_id(fastapi_client, mock_authenticated_user):
    response = fastapi_client.delete("/check-ins/0")
    assert response.status_code == 422
