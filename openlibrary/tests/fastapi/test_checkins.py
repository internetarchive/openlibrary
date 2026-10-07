"""Tests for the FastAPI patron check-ins endpoints."""

from unittest.mock import AsyncMock, patch

import pytest

from openlibrary.core.bookshelves_events import BookshelfEvent


@pytest.mark.parametrize("path", ["/works/OL1W/check-ins", "/works/OL1W/check-ins.json"])
def test_create_checkin_success(fastapi_client, mock_authenticated_user, path):
    payload = {
        "event_type": BookshelfEvent.START,
        "year": 2026,
        "month": 5,
        "day": 10,
        "edition_key": "OL100M",
    }
    with patch("openlibrary.fastapi.checkins.BookshelvesEvents.create_event", new_callable=AsyncMock, return_value=123) as mock_create:
        response = fastapi_client.post(path, json=payload)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "id": 123}
    mock_create.assert_awaited_once_with("testuser", 1, 100, "2026-05-10", event_type=BookshelfEvent.START)


def test_update_checkin_success(fastapi_client, mock_authenticated_user):
    payload = {
        "event_type": BookshelfEvent.UPDATE,
        "year": 2026,
        "month": 5,
        "day": 10,
        "edition_key": "OL100M",
        "event_id": 123,
    }
    event = {"username": "testuser"}
    with (
        patch("openlibrary.fastapi.checkins.BookshelvesEvents.select_by_id", new_callable=AsyncMock, return_value=[event]) as mock_select,
        patch("openlibrary.fastapi.checkins.BookshelvesEvents.update_event", new_callable=AsyncMock) as mock_update,
    ):
        response = fastapi_client.post("/works/OL1W/check-ins", json=payload)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "id": 123}
    mock_select.assert_awaited_once_with(123)
    mock_update.assert_awaited_once_with(123, event_date="2026-05-10", edition_id=100)


def test_update_checkin_missing_or_owned_by_another_user(fastapi_client, mock_authenticated_user):
    payload = {
        "event_type": BookshelfEvent.UPDATE,
        "year": 2026,
        "month": 5,
        "day": 10,
        "event_id": 123,
    }
    with (
        patch(
            "openlibrary.fastapi.checkins.BookshelvesEvents.select_by_id",
            new_callable=AsyncMock,
            side_effect=[[], [{"username": "another-user"}]],
        ) as mock_select,
        patch("openlibrary.fastapi.checkins.BookshelvesEvents.update_event", new_callable=AsyncMock) as mock_update,
    ):
        missing_response = fastapi_client.post("/works/OL1W/check-ins", json=payload)
        forbidden_response = fastapi_client.post("/works/OL1W/check-ins", json=payload)

    assert missing_response.status_code == 404
    assert forbidden_response.status_code == 403
    assert mock_select.await_count == 2
    mock_update.assert_not_awaited()


def test_delete_checkin_success(fastapi_client, mock_authenticated_user):
    event = {"username": "testuser"}
    with (
        patch("openlibrary.fastapi.checkins.BookshelvesEvents.select_by_id", new_callable=AsyncMock, return_value=[event]) as mock_select,
        patch("openlibrary.fastapi.checkins.BookshelvesEvents.delete_by_id", new_callable=AsyncMock) as mock_delete,
    ):
        response = fastapi_client.delete("/check-ins/123")

    assert response.status_code == 200
    assert response.content == b""
    mock_select.assert_awaited_once_with(123)
    mock_delete.assert_awaited_once_with(123)


def test_delete_checkin_missing_or_owned_by_another_user(fastapi_client, mock_authenticated_user):
    with (
        patch(
            "openlibrary.fastapi.checkins.BookshelvesEvents.select_by_id",
            new_callable=AsyncMock,
            side_effect=[[], [{"username": "another-user"}]],
        ) as mock_select,
        patch("openlibrary.fastapi.checkins.BookshelvesEvents.delete_by_id", new_callable=AsyncMock) as mock_delete,
    ):
        missing_response = fastapi_client.delete("/check-ins/123")
        forbidden_response = fastapi_client.delete("/check-ins/123")

    assert missing_response.status_code == 404
    assert forbidden_response.status_code == 403
    assert mock_select.await_count == 2
    mock_delete.assert_not_awaited()


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
