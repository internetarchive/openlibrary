"""Tests for FastAPI authentication dependencies (openlibrary.fastapi.auth)."""

from __future__ import annotations

from typing import Annotated
from unittest.mock import patch

from fastapi import Depends, FastAPI
from fastapi.security import APIKeyCookie
from fastapi.testclient import TestClient

from openlibrary.fastapi.auth import (
    AuthenticatedUser,
    authenticate_user_from_cookie,
    get_authenticated_user,
    require_authenticated_user,
    session_cookie,
)


def test_session_cookie_is_apikeycookie():
    """session_cookie must be an APIKeyCookie instance so FastAPI registers it
    as an OpenAPI security scheme (the core requirement of issue #12683)."""
    assert isinstance(session_cookie, APIKeyCookie)


def test_session_cookie_auto_error_is_false():
    """auto_error must be False so that missing cookies yield None instead of
    raising 422, allowing optional authentication on mixed endpoints."""
    assert session_cookie.auto_error is False


def test_authenticate_user_from_cookie_returns_none_for_none():
    result = authenticate_user_from_cookie(None)
    assert result is None


def test_authenticate_user_from_cookie_returns_none_for_empty_string():
    result = authenticate_user_from_cookie("")
    assert result is None


def test_authenticate_user_from_cookie_returns_none_for_bad_format():
    # Only 2 parts instead of 3
    result = authenticate_user_from_cookie("/people/user,timestamp")
    assert result is None


def test_authenticate_user_from_cookie_returns_none_for_invalid_hash():
    """A cookie with a structurally valid format but wrong hash returns None."""
    with patch("openlibrary.fastapi.auth.get_secret_key", return_value="secret"), patch("openlibrary.fastapi.auth.verify_hash", return_value=False):
        result = authenticate_user_from_cookie("/people/testuser,2026-01-01T00:00:00,badsalt$badhash")
    assert result is None


def test_authenticate_user_from_cookie_returns_none_for_missing_people_prefix():
    """A cookie whose user_key doesn't start with /people/ is rejected."""
    with patch("openlibrary.fastapi.auth.get_secret_key", return_value="secret"), patch("openlibrary.fastapi.auth.verify_hash", return_value=True):
        result = authenticate_user_from_cookie("badkey,2026-01-01T00:00:00,salt$hash")
    assert result is None


def test_authenticate_user_from_cookie_returns_user_for_valid_cookie():
    """A structurally valid cookie with a passing hash returns an AuthenticatedUser."""
    with patch("openlibrary.fastapi.auth.get_secret_key", return_value="secret"), patch("openlibrary.fastapi.auth.verify_hash", return_value=True):
        result = authenticate_user_from_cookie("/people/testuser,2026-01-01T00:00:00,salt$hash")

    assert isinstance(result, AuthenticatedUser)
    assert result.username == "testuser"
    assert result.user_key == "/people/testuser"
    assert result.timestamp == "2026-01-01T00:00:00"


# ---------------------------------------------------------------------------
# Integration tests via a minimal FastAPI test client
# ---------------------------------------------------------------------------


def test_get_authenticated_user_returns_none_with_no_cookie():
    """Without a cookie, get_authenticated_user should return None (not raise)."""
    app = FastAPI()

    @app.get("/test-auth")
    async def test_route(user: Annotated[AuthenticatedUser | None, Depends(get_authenticated_user)]):
        return {"authenticated": user is not None}

    client = TestClient(app)
    response = client.get("/test-auth")
    assert response.status_code == 200
    assert response.json() == {"authenticated": False}


def test_require_authenticated_user_returns_401_with_no_cookie():
    """require_authenticated_user must raise HTTP 401 when the cookie is absent."""
    app = FastAPI()

    @app.get("/protected")
    async def protected_route(user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)]):
        return {"username": user.username}

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/protected")
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"
