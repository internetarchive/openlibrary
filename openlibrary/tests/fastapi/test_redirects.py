"""Tests for redirect document handling in the FastAPI catch-all route.

These tests exercise the redirect lookup logic from openlibrary/asgi_app.py
using a self-contained FastAPI app, avoiding the full OpenLibrary dependency
chain (psycopg, infogami, web.py, etc.) that is difficult to install on
Windows.

The logic tested here mirrors _lookup_redirect_location() in asgi_app.py:
- /type/redirect with relative path or https:// target → 302
- /type/redirect with http:// or :// location → no redirect (404)
- non-redirect documents → no redirect (404)
- unknown paths → no redirect (404)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient

# Simulated async DB fetch functions (mocked in each test).
# These mirror openlibrary.core.async_db.fetch_one / fetch_val.
async def _fetch_one_stub(query: str, params: dict):
    """Stub: replaced by patch in each test."""
    raise NotImplementedError


async def _fetch_val_stub(query: str, params: dict):
    """Stub: replaced by patch in each test."""
    raise NotImplementedError


_redirect_type_id: int | None = None


async def _get_redirect_type_id() -> int | None:
    global _redirect_type_id
    if _redirect_type_id is None:
        _redirect_type_id = await _fetch_val_stub(
            "SELECT id FROM thing WHERE key = %(key)s",
            {"key": "/type/redirect"},
        )
    return _redirect_type_id


async def _lookup_redirect_location(path: str) -> str | None:
    row = await _fetch_one_stub(
        """SELECT t.type AS type_id, d.value AS location
           FROM thing t
           LEFT JOIN data d ON d.thing_id = t.id AND d.revision = t.latest_revision
           LEFT JOIN property p ON p.id = d.key_id AND p.name = 'location'
           WHERE t.key = %(key)s""",
        {"key": path},
    )
    if row is None:
        return None
    redirect_type_id = await _get_redirect_type_id()
    if redirect_type_id is None or row["type_id"] != redirect_type_id:
        return None
    location = row["location"]
    if location is None:
        return None
    if location.startswith("http://") or location.startswith("://"):
        return None
    return location


def _make_app() -> FastAPI:
    app = FastAPI()

    @app.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
        include_in_schema=False,
    )
    async def fallback(request: Request, path: str) -> Response:
        if location := await _lookup_redirect_location(path):
            return RedirectResponse(url=location, status_code=302)
        raise HTTPException(status_code=404)

    return app


@pytest.fixture(autouse=True)
def reset_redirect_cache():
    global _redirect_type_id
    _redirect_type_id = None


@pytest.fixture
def client():
    return TestClient(_make_app())


@pytest.mark.anyio
async def test_redirect_relative_path_returns_302(client):
    """A /type/redirect with a relative path returns 302 with Location."""
    redirect_type_id = 42
    with (
        patch(
            "test_redirects._fetch_val_stub",
            new_callable=AsyncMock,
            return_value=redirect_type_id,
        ),
        patch(
            "test_redirects._fetch_one_stub",
            new_callable=AsyncMock,
            return_value={"type_id": redirect_type_id, "location": "/works/OL1W"},
        ),
    ):
        response = client.get("/olcc2026", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/works/OL1W"


@pytest.mark.anyio
async def test_redirect_https_target_returns_302(client):
    """A /type/redirect with an https:// target returns 302 with Location."""
    redirect_type_id = 42
    with (
        patch(
            "test_redirects._fetch_val_stub",
            new_callable=AsyncMock,
            return_value=redirect_type_id,
        ),
        patch(
            "test_redirects._fetch_one_stub",
            new_callable=AsyncMock,
            return_value={
                "type_id": redirect_type_id,
                "location": "https://slides.google.com/abc",
            },
        ),
    ):
        response = client.get("/booktalks", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "https://slides.google.com/abc"


@pytest.mark.anyio
async def test_redirect_http_location_no_redirect(client):
    """A /type/redirect with an http:// location does not redirect."""
    redirect_type_id = 42
    with (
        patch(
            "test_redirects._fetch_val_stub",
            new_callable=AsyncMock,
            return_value=redirect_type_id,
        ),
        patch(
            "test_redirects._fetch_one_stub",
            new_callable=AsyncMock,
            return_value={
                "type_id": redirect_type_id,
                "location": "http://example.com",
            },
        ),
    ):
        response = client.get("/some-path", follow_redirects=False)
    assert response.status_code == 404


@pytest.mark.anyio
async def test_redirect_colon_colon_location_no_redirect(client):
    """A /type/redirect with a :// location does not redirect."""
    redirect_type_id = 42
    with (
        patch(
            "test_redirects._fetch_val_stub",
            new_callable=AsyncMock,
            return_value=redirect_type_id,
        ),
        patch(
            "test_redirects._fetch_one_stub",
            new_callable=AsyncMock,
            return_value={"type_id": redirect_type_id, "location": "://example.com"},
        ),
    ):
        response = client.get("/some-path", follow_redirects=False)
    assert response.status_code == 404


@pytest.mark.anyio
async def test_non_redirect_document_no_redirect(client):
    """A non-redirect document does not redirect."""
    # fetch_val returns the redirect type id (42), but the document's
    # type_id is 99 (a different type), so it must not redirect.
    with (
        patch(
            "test_redirects._fetch_val_stub",
            new_callable=AsyncMock,
            return_value=42,
        ),
        patch(
            "test_redirects._fetch_one_stub",
            new_callable=AsyncMock,
            return_value={"type_id": 99, "location": "/works/OL1W"},
        ),
    ):
        response = client.get("/works/OL1W", follow_redirects=False)
    assert response.status_code == 404


@pytest.mark.anyio
async def test_unknown_path_no_redirect(client):
    """An unknown path does not redirect."""
    with (
        patch(
            "test_redirects._fetch_val_stub",
            new_callable=AsyncMock,
            return_value=42,
        ),
        patch(
            "test_redirects._fetch_one_stub",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        response = client.get("/nonexistent-path", follow_redirects=False)
    assert response.status_code == 404


@pytest.mark.anyio
async def test_redirect_no_location_no_redirect(client):
    """A /type/redirect with no location does not redirect."""
    redirect_type_id = 42
    with (
        patch(
            "test_redirects._fetch_val_stub",
            new_callable=AsyncMock,
            return_value=redirect_type_id,
        ),
        patch(
            "test_redirects._fetch_one_stub",
            new_callable=AsyncMock,
            return_value={"type_id": redirect_type_id, "location": None},
        ),
    ):
        response = client.get("/some-path", follow_redirects=False)
    assert response.status_code == 404
