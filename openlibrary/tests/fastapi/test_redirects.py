"""Tests for redirect document handling in the FastAPI catch-all route.

These tests exercise the real _lookup_redirect_location() from
openlibrary/asgi_app.py, mocking only the async DB fetch helpers.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.importorskip("openlibrary.asgi_app", reason="openlibrary deps not installed")

from openlibrary.asgi_app import _lookup_redirect_location


@pytest.fixture(autouse=True)
def reset_redirect_cache():
    """Reset the redirect type ID cache before each test."""
    from openlibrary import asgi_app

    asgi_app._redirect_type_id = None


async def test_redirect_relative_path_returns_location():
    """A /type/redirect with a relative path returns the location."""
    redirect_type_id = 42
    with (
        patch(
            "openlibrary.asgi_app.fetch_val",
            new_callable=AsyncMock,
            return_value=redirect_type_id,
        ),
        patch(
            "openlibrary.asgi_app.fetch_one",
            new_callable=AsyncMock,
            return_value={"type_id": redirect_type_id, "data_json": '{"location": "/works/OL1W"}'},
        ),
    ):
        location = await _lookup_redirect_location("/olcc2026")
    assert location == "/works/OL1W"


async def test_redirect_https_target_returns_location():
    """A /type/redirect with an https:// target returns the location."""
    redirect_type_id = 42
    with (
        patch(
            "openlibrary.asgi_app.fetch_val",
            new_callable=AsyncMock,
            return_value=redirect_type_id,
        ),
        patch(
            "openlibrary.asgi_app.fetch_one",
            new_callable=AsyncMock,
            return_value={
                "type_id": redirect_type_id,
                "data_json": '{"location": "https://slides.google.com/abc"}',
            },
        ),
    ):
        location = await _lookup_redirect_location("/booktalks")
    assert location == "https://slides.google.com/abc"


async def test_redirect_http_location_returns_none():
    """A /type/redirect with an http:// location returns None."""
    redirect_type_id = 42
    with (
        patch(
            "openlibrary.asgi_app.fetch_val",
            new_callable=AsyncMock,
            return_value=redirect_type_id,
        ),
        patch(
            "openlibrary.asgi_app.fetch_one",
            new_callable=AsyncMock,
            return_value={
                "type_id": redirect_type_id,
                "data_json": '{"location": "http://example.com"}',
            },
        ),
    ):
        location = await _lookup_redirect_location("/some-path")
    assert location is None


async def test_redirect_colon_colon_location_returns_none():
    """A /type/redirect with a :// location returns None."""
    redirect_type_id = 42
    with (
        patch(
            "openlibrary.asgi_app.fetch_val",
            new_callable=AsyncMock,
            return_value=redirect_type_id,
        ),
        patch(
            "openlibrary.asgi_app.fetch_one",
            new_callable=AsyncMock,
            return_value={"type_id": redirect_type_id, "data_json": '{"location": "://example.com"}'},
        ),
    ):
        location = await _lookup_redirect_location("/some-path")
    assert location is None


async def test_non_redirect_document_returns_none():
    """A non-redirect document returns None."""
    with (
        patch(
            "openlibrary.asgi_app.fetch_val",
            new_callable=AsyncMock,
            return_value=99,
        ),
        patch(
            "openlibrary.asgi_app.fetch_one",
            new_callable=AsyncMock,
            return_value={"type_id": 99, "data_json": '{"location": "/works/OL1W"}'},
        ),
    ):
        location = await _lookup_redirect_location("/works/OL1W")
    assert location is None


async def test_unknown_path_returns_none():
    """An unknown path returns None."""
    with (
        patch(
            "openlibrary.asgi_app.fetch_val",
            new_callable=AsyncMock,
            return_value=42,
        ),
        patch(
            "openlibrary.asgi_app.fetch_one",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        location = await _lookup_redirect_location("/nonexistent-path")
    assert location is None


async def test_redirect_no_location_returns_none():
    """A /type/redirect with no location returns None."""
    redirect_type_id = 42
    with (
        patch(
            "openlibrary.asgi_app.fetch_val",
            new_callable=AsyncMock,
            return_value=redirect_type_id,
        ),
        patch(
            "openlibrary.asgi_app.fetch_one",
            new_callable=AsyncMock,
            return_value={"type_id": redirect_type_id, "data_json": "{}"},
        ),
    ):
        location = await _lookup_redirect_location("/some-path")
    assert location is None
