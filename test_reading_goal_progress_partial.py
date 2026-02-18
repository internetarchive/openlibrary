#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.31.0",
#     "pytest>=8.3.4",
# ]
# ///
"""
Test script for ReadingGoalProgressPartial endpoint.

This script makes HTTP requests to localhost:8080 to test the
/partials/ReadingGoalProgress.json endpoint.  It helps understand how the
endpoint works and validates its behavior with various inputs.

Note: This endpoint requires an authenticated user to return meaningful data.
The test will log in using the default dev credentials before making requests.

Usage with uv:
    uv run test_reading_goal_progress_partial.py

Or with Python directly (requires requests to be installed):
    python test_reading_goal_progress_partial.py

Requirements:
    - OpenLibrary server running on localhost:8080
"""

import sys
import urllib.parse
from typing import Any

import pytest
import requests

# Base URL for the ReadingGoalProgress partials endpoint
BASE_URL = "http://localhost:8080/partials/ReadingGoalProgress.json"

# Default dev credentials
USERNAME = "openlibrary@example.com"
PASSWORD = "admin123"


def login(
    session: requests.Session, username: str = USERNAME, password: str = PASSWORD
) -> requests.Response:
    """
    Log in to OpenLibrary and store the session cookie.

    Args:
        session: A requests.Session to store the session cookie in
        username: OpenLibrary account email
        password: OpenLibrary account password

    Returns:
        The login response
    """
    return session.post(
        "http://localhost:8080/account/login",
        data={
            "username": username,
            "password": password,
            "remember": "true",
            "redirect": "/account/books",
        },
        allow_redirects=False,
    )


def build_reading_goal_url(year: int | None = None) -> str:
    """
    Build the URL for the ReadingGoalProgress partial endpoint.

    Matches the JavaScript buildPartialsUrl function behavior:
        buildPartialsUrl('ReadingGoalProgress', {year: goalYear})

    Args:
        year: The year to fetch the reading goal for (optional)

    Returns:
        Complete URL with query parameters
    """
    if year is not None:
        params = {'year': year}
        query_string = urllib.parse.urlencode(params)
        return f"{BASE_URL}?{query_string}"
    return BASE_URL


def make_request(
    year: int | None,
    description: str,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """
    Make a request to the ReadingGoalProgress endpoint and return the response.

    Args:
        year: The year to pass as a query parameter (None omits the parameter)
        description: Description of the test case for logging
        session: Optional requests.Session with auth cookies

    Returns:
        Parsed JSON response from the server
    """
    url = build_reading_goal_url(year)
    requester = session or requests

    print(f"\n{'=' * 60}")
    print(f"Test: {description}")
    print(f"{'=' * 60}")
    print(f"Request URL: {url}")
    if year is not None:
        print(f"year: {year}")
    else:
        print("year: (not provided, defaults to current year)")

    try:
        response = requester.get(url, timeout=30)
        print(f"\nStatus Code: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print(f"\nResponse Keys: {list(result.keys())}")

            if 'partials' in result:
                html = result['partials']
                preview = html[:200] if len(html) > 200 else html
                print(f"\nPartials HTML (first 200 chars):\n{preview}")

            return result
        else:
            print(f"Error Response: {response.text[:500]}")
            return {'error': response.text, 'status_code': response.status_code}

    except requests.exceptions.ConnectionError as e:
        print(f"Connection Error: Could not connect to {BASE_URL}")
        print("Make sure the OpenLibrary server is running on localhost:8080")
        print(f"Error details: {e}")
        sys.exit(1)
    except requests.exceptions.Timeout:
        print("Timeout Error: Request took longer than 30 seconds")
        return {'error': 'timeout'}
    except requests.exceptions.RequestException as e:
        print(f"Request Error: {e}")
        return {'error': str(e)}


@pytest.fixture
def logged_in_session():
    """Create a requests.Session that is logged in to OpenLibrary."""
    session = requests.Session()
    response = login(session)
    assert response.status_code == 303, (
        f"Login failed with status {response.status_code}. "
        "Make sure the server is running on localhost:8080."
    )
    yield session
    session.close()


@pytest.mark.integration
def test_no_year_param(logged_in_session):
    """Test without a year parameter (defaults to current year)."""
    result = make_request(
        year=None,
        description="Reading goal progress without year param (uses current year)",
        session=logged_in_session,
    )
    assert 'partials' in result
    assert isinstance(result['partials'], str)


@pytest.mark.integration
def test_with_current_year(logged_in_session):
    """Test with the current year explicitly provided."""
    from datetime import datetime

    current_year = datetime.now().year
    result = make_request(
        year=current_year,
        description=f"Reading goal progress for current year ({current_year})",
        session=logged_in_session,
    )
    assert 'partials' in result
    assert isinstance(result['partials'], str)


@pytest.mark.integration
def test_with_past_year(logged_in_session):
    """Test with a past year."""
    result = make_request(
        year=2023,
        description="Reading goal progress for past year (2023)",
        session=logged_in_session,
    )
    assert 'partials' in result
    assert isinstance(result['partials'], str)


@pytest.mark.integration
def test_response_contains_html(logged_in_session):
    """Test that the response contains HTML content."""
    result = make_request(
        year=None,
        description="Verify response contains HTML",
        session=logged_in_session,
    )
    assert 'partials' in result
    html = result['partials']
    # The template should return some HTML string
    assert isinstance(html, str)


def run_all_tests():
    """Run all test cases and summarize results."""
    print("\n" + "=" * 60)
    print("ReadingGoalProgressPartial Endpoint Tests")
    print("=" * 60)
    print(f"Testing against: {BASE_URL}")
    print("Make sure your OpenLibrary server is running on localhost:8080")

    # Log in once for all tests
    session = requests.Session()
    response = login(session)
    if response.status_code != 303:
        print(f"Warning: Login returned status {response.status_code} (expected 303)")
        print("Tests will run without authentication.")
        session = None  # type: ignore[assignment]
    else:
        print(f"Logged in as {USERNAME}")

    from datetime import datetime

    current_year = datetime.now().year

    tests = [
        ("No year param", lambda: make_request(None, "No year param", session)),
        (
            f"Current year ({current_year})",
            lambda: make_request(
                current_year, f"Current year ({current_year})", session
            ),
        ),
        ("Past year (2023)", lambda: make_request(2023, "Past year (2023)", session)),
        ("Past year (2024)", lambda: make_request(2024, "Past year (2024)", session)),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            success = 'error' not in result or result.get('status_code', 200) == 200
            results.append((name, success, result))
        except (KeyError, ValueError, TypeError) as e:
            print(f"\nTest '{name}' raised exception: {e}")
            results.append((name, False, {'error': str(e)}))

    if session:
        session.close()

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for _, success, _ in results if success)
    total = len(results)

    for name, success, result in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    return results


if __name__ == '__main__':
    run_all_tests()
