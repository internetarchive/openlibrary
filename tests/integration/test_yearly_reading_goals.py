# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "pytest",
#     "requests",
# ]
# ///

"""Integration tests for yearly reading goals endpoints.

These tests verify that both the FastAPI and web.py endpoints return identical
responses for reading goal operations.

These tests are marked as "integration" and are skipped by default.
They require a running OpenLibrary server on localhost:18080 (FastAPI)
and the legacy web.py server on localhost (typically port 80 or 8080).

Run explicitly with:
    uv run pytest -m integration tests/integration/test_yearly_reading_goals.py -v
"""

import pytest
import requests

BASE_URL_FASTAPI = "http://localhost:18080"
BASE_URL_WEBPY = "http://localhost:8080"  # Adjust if your web.py runs on different port
USERNAME = "openlibrary@example.com"
PASSWORD = "admin123"


@pytest.fixture
def session():
    """Create a configured requests session."""
    s = requests.Session()
    s.allow_redirects = False
    s.headers.update(
        {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    )
    yield s
    s.close()


def _login(session, base_url, username=USERNAME, password=PASSWORD):
    """Helper to perform login and return response."""
    return session.post(
        f"{base_url}/account/login",
        data={
            "username": username,
            "password": password,
            "remember": "true",
            "redirect": "/",
        },
        allow_redirects=False,
    )


def _logout(session, base_url):
    """Helper to perform logout and return response."""
    return session.post(f"{base_url}/account/logout", allow_redirects=False)


@pytest.mark.integration
def test_fastapi_get_reading_goals_requires_auth(session):
    """Test that FastAPI GET /reading-goal requires authentication."""
    r = session.get(f"{BASE_URL_FASTAPI}/reading-goal.json")
    assert r.status_code == 401


@pytest.mark.integration
def test_webpy_get_reading_goals_requires_auth(session):
    """Test that web.py GET /reading-goal requires authentication."""
    r = session.get(f"{BASE_URL_WEBPY}/reading-goal.json")
    # web.py returns 401 with message, FastAPI returns 401
    assert r.status_code == 401


@pytest.mark.integration
def test_fastapi_create_and_get_reading_goal(session):
    """Test creating and getting a reading goal via FastAPI."""
    # Login via FastAPI
    r = _login(session, BASE_URL_FASTAPI)
    assert r.status_code == 303
    assert "session" in session.cookies

    test_year = 2025
    test_goal = 10

    try:
        # Create a reading goal
        r = session.post(
            f"{BASE_URL_FASTAPI}/reading-goal.json",
            data={"goal": test_goal, "year": test_year},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"

        # Get all reading goals
        r = session.get(f"{BASE_URL_FASTAPI}/reading-goal.json")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert isinstance(data["goal"], list)
        # Should have at least one goal
        assert len(data["goal"]) >= 1

        # Get specific year
        r = session.get(f"{BASE_URL_FASTAPI}/reading-goal.json?year={test_year}")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert len(data["goal"]) >= 1
        assert data["goal"][0]["year"] == test_year
        assert data["goal"][0]["goal"] == test_goal

    finally:
        # Cleanup: delete the test goal
        session.post(
            f"{BASE_URL_FASTAPI}/reading-goal.json",
            data={"goal": 0, "year": test_year, "is_update": "true"},
        )
        _logout(session, BASE_URL_FASTAPI)


@pytest.mark.integration
def test_webpy_create_and_get_reading_goal(session):
    """Test creating and getting a reading goal via web.py."""
    # Login via web.py
    r = _login(session, BASE_URL_WEBPY)
    assert r.status_code == 303
    assert "session" in session.cookies

    test_year = 2025
    test_goal = 10

    try:
        # Create a reading goal
        r = session.post(
            f"{BASE_URL_WEBPY}/reading-goal.json",
            data={"goal": test_goal, "year": test_year},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"

        # Get all reading goals
        r = session.get(f"{BASE_URL_WEBPY}/reading-goal.json")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert isinstance(data["goal"], list)

        # Get specific year
        r = session.get(f"{BASE_URL_WEBPY}/reading-goal.json?year={test_year}")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert len(data["goal"]) >= 1
        assert data["goal"][0]["year"] == test_year
        assert data["goal"][0]["goal"] == test_goal

    finally:
        # Cleanup: delete the test goal
        session.post(
            f"{BASE_URL_WEBPY}/reading-goal.json",
            data={"goal": 0, "year": test_year, "is_update": "true"},
        )
        _logout(session, BASE_URL_WEBPY)


@pytest.mark.integration
def test_fastapi_update_reading_goal(session):
    """Test updating a reading goal via FastAPI."""
    _login(session, BASE_URL_FASTAPI)

    test_year = 2025
    initial_goal = 5
    updated_goal = 15

    try:
        # Create initial goal
        session.post(
            f"{BASE_URL_FASTAPI}/reading-goal.json",
            data={"goal": initial_goal, "year": test_year},
        )

        # Update the goal
        r = session.post(
            f"{BASE_URL_FASTAPI}/reading-goal.json",
            data={"goal": updated_goal, "year": test_year, "is_update": "true"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"

        # Verify the update
        r = session.get(f"{BASE_URL_FASTAPI}/reading-goal.json?year={test_year}")
        data = r.json()
        assert data["goal"][0]["goal"] == updated_goal

    finally:
        # Cleanup
        session.post(
            f"{BASE_URL_FASTAPI}/reading-goal.json",
            data={"goal": 0, "year": test_year, "is_update": "true"},
        )
        _logout(session, BASE_URL_FASTAPI)


@pytest.mark.integration
def test_webpy_update_reading_goal(session):
    """Test updating a reading goal via web.py."""
    _login(session, BASE_URL_WEBPY)

    test_year = 2025
    initial_goal = 5
    updated_goal = 15

    try:
        # Create initial goal
        session.post(
            f"{BASE_URL_WEBPY}/reading-goal.json",
            data={"goal": initial_goal, "year": test_year},
        )

        # Update the goal
        r = session.post(
            f"{BASE_URL_WEBPY}/reading-goal.json",
            data={"goal": updated_goal, "year": test_year, "is_update": "true"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"

        # Verify the update
        r = session.get(f"{BASE_URL_WEBPY}/reading-goal.json?year={test_year}")
        data = r.json()
        assert data["goal"][0]["goal"] == updated_goal

    finally:
        # Cleanup
        session.post(
            f"{BASE_URL_WEBPY}/reading-goal.json",
            data={"goal": 0, "year": test_year, "is_update": "true"},
        )
        _logout(session, BASE_URL_WEBPY)


@pytest.mark.integration
def test_fastapi_validation_errors(session):
    """Test FastAPI validation error handling."""
    _login(session, BASE_URL_FASTAPI)

    try:
        # Test negative goal on create
        r = session.post(
            f"{BASE_URL_FASTAPI}/reading-goal.json",
            data={"goal": -1, "year": 2025},
        )
        assert r.status_code == 422

        # Test goal = 0 on create (not update)
        r = session.post(
            f"{BASE_URL_FASTAPI}/reading-goal.json",
            data={"goal": 0, "year": 2025},
        )
        assert r.status_code == 422

        # Test update without year
        r = session.post(
            f"{BASE_URL_FASTAPI}/reading-goal.json",
            data={"goal": 5, "is_update": "true"},
        )
        assert r.status_code == 422

    finally:
        _logout(session, BASE_URL_FASTAPI)


@pytest.mark.integration
def test_webpy_validation_errors(session):
    """Test web.py validation error handling."""
    _login(session, BASE_URL_WEBPY)

    try:
        # Test negative goal on create
        r = session.post(
            f"{BASE_URL_WEBPY}/reading-goal.json",
            data={"goal": -1, "year": 2025},
        )
        assert r.status_code == 400

        # Test goal = 0 on create (not update)
        r = session.post(
            f"{BASE_URL_WEBPY}/reading-goal.json",
            data={"goal": 0, "year": 2025},
        )
        assert r.status_code == 400

        # Test update without year
        r = session.post(
            f"{BASE_URL_WEBPY}/reading-goal.json",
            data={"goal": 5, "is_update": "true"},
        )
        assert r.status_code == 400

    finally:
        _logout(session, BASE_URL_WEBPY)


@pytest.mark.integration
def test_compare_fastapi_and_webpy_responses(session):
    """Compare responses between FastAPI and web.py endpoints."""
    # Create sessions for both
    session_fastapi = requests.Session()
    session_webpy = requests.Session()

    try:
        # Login to both
        _login(session_fastapi, BASE_URL_FASTAPI)
        _login(session_webpy, BASE_URL_WEBPY)

        # Use different years for each API to avoid database conflicts
        test_year_fastapi = 2025
        test_year_webpy = 2026
        test_goal = 20

        # Create goal in FastAPI
        r_fastapi = session_fastapi.post(
            f"{BASE_URL_FASTAPI}/reading-goal.json",
            data={"goal": test_goal, "year": test_year_fastapi},
        )
        assert r_fastapi.status_code == 200

        # Create goal in web.py
        r_webpy = session_webpy.post(
            f"{BASE_URL_WEBPY}/reading-goal.json",
            data={"goal": test_goal, "year": test_year_webpy},
        )
        assert r_webpy.status_code == 200

        # Compare response structure (both should have same format)
        assert r_fastapi.json() == r_webpy.json()

        # Get specific year from each API
        r_fastapi = session_fastapi.get(
            f"{BASE_URL_FASTAPI}/reading-goal.json?year={test_year_fastapi}"
        )
        r_webpy = session_webpy.get(f"{BASE_URL_WEBPY}/reading-goal.json?year={test_year_webpy}")

        assert r_fastapi.status_code == r_webpy.status_code == 200
        data_fastapi = r_fastapi.json()
        data_webpy = r_webpy.json()

        # Compare structure
        assert data_fastapi["status"] == data_webpy["status"] == "ok"
        assert isinstance(data_fastapi["goal"], list)
        assert isinstance(data_webpy["goal"], list)

        # Compare response formats (same goal value, different years)
        assert data_fastapi["goal"][0]["goal"] == data_webpy["goal"][0]["goal"]
        assert data_fastapi["goal"][0]["year"] == test_year_fastapi
        assert data_webpy["goal"][0]["year"] == test_year_webpy

    finally:
        # Cleanup
        session_fastapi.post(
            f"{BASE_URL_FASTAPI}/reading-goal.json",
            data={"goal": 0, "year": test_year_fastapi, "is_update": "true"},
        )
        session_webpy.post(
            f"{BASE_URL_WEBPY}/reading-goal.json",
            data={"goal": 0, "year": test_year_webpy, "is_update": "true"},
        )
        _logout(session_fastapi, BASE_URL_FASTAPI)
        _logout(session_webpy, BASE_URL_WEBPY)
        session_fastapi.close()
        session_webpy.close()
