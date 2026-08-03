"""Tests for FastAPI authentication dependencies (openlibrary.fastapi.auth)."""

from __future__ import annotations

from typing import Annotated
from unittest.mock import MagicMock, patch

from fastapi import Depends, FastAPI
from fastapi.security import APIKeyCookie
from fastapi.testclient import TestClient

from openlibrary.fastapi.auth import (
    AuthenticatedUser,
    LibrarianDep,
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


# ---------------------------------------------------------------------------
# require_librarian tests
# ---------------------------------------------------------------------------


FAKE_AUTH_USER = AuthenticatedUser(
    username="testuser",
    user_key="/people/testuser",
    timestamp="2026-01-01T00:00:00",
)


def _build_librarian_app():
    """Create a minimal FastAPI app with one route protected by require_librarian."""
    app = FastAPI()

    @app.get("/librarian-only")
    async def librarian_route(_: LibrarianDep):
        return {"message": "access granted"}

    return app


def test_require_librarian_returns_401_with_no_cookie():
    """require_librarian must raise HTTP 401 when the user is not authenticated."""
    app = _build_librarian_app()
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/librarian-only")
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def test_require_librarian_returns_403_for_regular_user():
    """require_librarian must raise HTTP 403 when the user lacks librarian-level roles."""
    app = _build_librarian_app()
    app.dependency_overrides[require_authenticated_user] = lambda: FAKE_AUTH_USER

    with patch("openlibrary.fastapi.auth.get_current_user") as mock_get_user:
        user = MagicMock()
        user.is_librarian_or_higher.return_value = False
        mock_get_user.return_value = user

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/librarian-only")
        assert response.status_code == 403
        assert response.json()["detail"] == "Insufficient permissions"

    app.dependency_overrides.clear()


def test_require_librarian_allows_admin():
    """require_librarian allows access for admin users."""
    app = _build_librarian_app()
    app.dependency_overrides[require_authenticated_user] = lambda: FAKE_AUTH_USER

    with patch("openlibrary.fastapi.auth.get_current_user") as mock_get_user:
        user = MagicMock()
        user.is_librarian_or_higher.return_value = True
        mock_get_user.return_value = user

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/librarian-only")
        assert response.status_code == 200
        assert response.json() == {"message": "access granted"}

    app.dependency_overrides.clear()


def test_require_librarian_allows_librarian():
    """require_librarian allows access for librarian users."""
    app = _build_librarian_app()
    app.dependency_overrides[require_authenticated_user] = lambda: FAKE_AUTH_USER

    with patch("openlibrary.fastapi.auth.get_current_user") as mock_get_user:
        user = MagicMock()
        user.is_librarian_or_higher.return_value = True
        mock_get_user.return_value = user

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/librarian-only")
        assert response.status_code == 200
        assert response.json() == {"message": "access granted"}

    app.dependency_overrides.clear()


def test_require_librarian_allows_super_librarian():
    """require_librarian allows access for super-librarian users."""
    app = _build_librarian_app()
    app.dependency_overrides[require_authenticated_user] = lambda: FAKE_AUTH_USER

    with patch("openlibrary.fastapi.auth.get_current_user") as mock_get_user:
        user = MagicMock()
        user.is_librarian_or_higher.return_value = True
        mock_get_user.return_value = user

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/librarian-only")
        assert response.status_code == 200
        assert response.json() == {"message": "access granted"}

    app.dependency_overrides.clear()


def test_require_librarian_returns_403_when_user_is_none():
    """require_librarian returns 403 when get_current_user returns None."""
    app = _build_librarian_app()
    app.dependency_overrides[require_authenticated_user] = lambda: FAKE_AUTH_USER

    with patch("openlibrary.fastapi.auth.get_current_user") as mock_get_user:
        mock_get_user.return_value = None

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/librarian-only")
        assert response.status_code == 403
        assert response.json()["detail"] == "Insufficient permissions"

    app.dependency_overrides.clear()
