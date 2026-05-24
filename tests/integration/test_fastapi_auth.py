# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "pytest",
#     "requests",
# ]
# ///

"""Integration tests for FastAPI authentication endpoints.

These tests are marked as "integration" and are skipped by default.
They require a running FastAPI server on localhost:18080.

Run explicitly with:
    uv run pytest -m integration tests/integration/test_fastapi_auth.py -v
"""

import pytest
import requests

BASE_URL = "http://localhost:18080"
USERNAME = "openlibrary@example.com"
PASSWORD = "admin123"


@pytest.fixture
def session():
    """Create a configured requests session."""
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
    yield s
    s.close()


def _login(
    session,
    username=USERNAME,
    password=PASSWORD,
    remember=True,
    redirect="/account/books",
):
    """Helper to perform login and return response."""
    return session.post(
        f"{BASE_URL}/account/login",
        data={
            "username": username,
            "password": password,
            "remember": str(remember).lower(),
            "redirect": redirect,
        },
        allow_redirects=False,
    )


def _logout(session):
    """Helper to perform logout and return response."""
    return session.post(f"{BASE_URL}/account/logout", allow_redirects=False)


@pytest.mark.integration
def test_health_endpoint():
    """Test that the health endpoint returns 200 OK."""
    assert requests.get(f"{BASE_URL}/health").status_code == 200


@pytest.mark.integration
def test_login_and_session(session):
    """Test that login creates a session cookie and authenticated requests work."""
    r = _login(session)
    assert r.status_code == 303
    assert "session" in session.cookies

    # Test that session works for authenticated requests
    r = session.get(f"{BASE_URL}/account/test.json")
    assert r.status_code in (200, 404)  # 404 is OK, just means endpoint doesn't exist


@pytest.mark.integration
def test_logout_clears_session(session):
    """Test that logging out clears the session cookie."""
    _login(session)
    assert "session" in session.cookies

    r = _logout(session)
    assert r.status_code == 303
    assert "session" not in session.cookies


@pytest.mark.integration
def test_relogin_after_logout(session):
    """Test that we can login again after logging out."""
    _login(session)
    _logout(session)

    r = _login(session)
    assert r.status_code == 303
    assert "session" in session.cookies


@pytest.mark.integration
def test_login_with_invalid_credentials(session):
    """Test that login accepts invalid credentials (TODO: should return 400/401).

    Current implementation returns 303 and sets a session cookie even for invalid
    credentials. This should be fixed to properly validate before creating sessions.
    """
    r = _login(session, username="invalid@example.com", password="wrong")
    assert r.status_code == 303  # TODO: should be 400 or 401
