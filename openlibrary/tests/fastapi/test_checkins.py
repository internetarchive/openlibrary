"""Tests for the FastAPI patron check-ins endpoints."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from openlibrary.core.bookshelves_events import BookshelfEvent, CheckInEvent

_BOOKSHELVES_EVENTS = "openlibrary.fastapi.checkins.BookshelvesEvents"


def _check_in_event(username: str) -> CheckInEvent:
    return CheckInEvent(id=123, username=username, work_id=1, edition_id=1, event_type=BookshelfEvent.START, event_date="2026-05-10")


@pytest.fixture
def event_methods():
    """Replace the BookshelvesEvents DB calls the check-ins router makes with AsyncMocks."""
    with (
        patch(f"{_BOOKSHELVES_EVENTS}.create_event", new_callable=AsyncMock) as create_event,
        patch(f"{_BOOKSHELVES_EVENTS}.select_by_id", new_callable=AsyncMock) as select_by_id,
        patch(f"{_BOOKSHELVES_EVENTS}.update_event", new_callable=AsyncMock) as update_event,
        patch(f"{_BOOKSHELVES_EVENTS}.delete_by_id", new_callable=AsyncMock) as delete_by_id,
    ):
        yield SimpleNamespace(create_event=create_event, select_by_id=select_by_id, update_event=update_event, delete_by_id=delete_by_id)


@pytest.mark.parametrize("path", ["/works/OL1W/check-ins", "/works/OL1W/check-ins.json"])
def test_create_checkin_success(fastapi_client, mock_authenticated_user, event_methods, path):
    event_methods.create_event.return_value = 123
    payload = {
        "event_type": BookshelfEvent.START,
        "year": 2026,
        "month": 5,
        "day": 10,
        "edition_key": "OL100M",
    }
    response = fastapi_client.post(path, json=payload)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "id": 123}
    event_methods.create_event.assert_awaited_once_with("testuser", 1, 100, "2026-05-10", event_type=BookshelfEvent.START)


def test_update_checkin_success(fastapi_client, mock_authenticated_user, event_methods):
    event_methods.select_by_id.return_value = _check_in_event("testuser")
    payload = {
        "event_type": BookshelfEvent.UPDATE,
        "year": 2026,
        "month": 5,
        "day": 10,
        "edition_key": "OL100M",
        "event_id": 123,
    }
    response = fastapi_client.post("/works/OL1W/check-ins", json=payload)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "id": 123}
    event_methods.select_by_id.assert_awaited_once_with(123)
    event_methods.update_event.assert_awaited_once_with(123, event_date="2026-05-10", edition_id=100)


def test_update_checkin_missing_or_owned_by_another_user(fastapi_client, mock_authenticated_user, event_methods):
    event_methods.select_by_id.side_effect = [None, _check_in_event("another-user")]
    payload = {
        "event_type": BookshelfEvent.UPDATE,
        "year": 2026,
        "month": 5,
        "day": 10,
        "event_id": 123,
    }
    missing_response = fastapi_client.post("/works/OL1W/check-ins", json=payload)
    forbidden_response = fastapi_client.post("/works/OL1W/check-ins", json=payload)

    assert missing_response.status_code == 404
    assert forbidden_response.status_code == 403
    assert event_methods.select_by_id.await_count == 2
    event_methods.update_event.assert_not_awaited()


def test_delete_checkin_success(fastapi_client, mock_authenticated_user, event_methods):
    event_methods.select_by_id.return_value = _check_in_event("testuser")
    response = fastapi_client.delete("/check-ins/123")

    assert response.status_code == 200
    assert response.content == b""
    event_methods.select_by_id.assert_awaited_once_with(123)
    event_methods.delete_by_id.assert_awaited_once_with(123)


def test_delete_checkin_missing_or_owned_by_another_user(fastapi_client, mock_authenticated_user, event_methods):
    event_methods.select_by_id.side_effect = [None, _check_in_event("another-user")]
    missing_response = fastapi_client.delete("/check-ins/123")
    forbidden_response = fastapi_client.delete("/check-ins/123")

    assert missing_response.status_code == 404
    assert forbidden_response.status_code == 403
    assert event_methods.select_by_id.await_count == 2
    event_methods.delete_by_id.assert_not_awaited()


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
