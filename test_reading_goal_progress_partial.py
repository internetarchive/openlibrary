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

This script makes HTTP requests to localhost:8080 to test the /partials.json
endpoint with the ReadingGoalProgress component.

Usage with uv:
    uv run test_reading_goal_progress_partial.py

Or with Python directly (requires requests to be installed):
    python test_reading_goal_progress_partial.py

Requirements:
    - OpenLibrary server running on localhost:8080
"""

import json
import sys
import urllib.parse
from typing import Any

import pytest
import requests

# Base URL for the partials endpoint
BASE_URL = "http://localhost:8080/partials.json"
LOGIN_URL = "http://localhost:8080/account/login"

# Test credentials from tests/integration/test_fastapi_auth.py
USERNAME = "openlibrary@example.com"
PASSWORD = "admin123"

# Firefox-like headers for realistic requests
FIREFOX_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}


def login(session: requests.Session) -> bool:
    """Login to OpenLibrary and return True if successful."""
    # First get the login page to establish session
    session.get(LOGIN_URL, headers=FIREFOX_HEADERS)

    # Perform login
    response = session.post(
        LOGIN_URL,
        data={
            'username': USERNAME,
            'password': PASSWORD,
            'remember': 'true',
            'redirect': '/',
        },
        headers=FIREFOX_HEADERS,
        allow_redirects=False,
    )
    # Login redirects to home on success
    return response.status_code == 303 and 'session' in session.cookies


def build_reading_goal_progress_url(data: dict) -> str:
    """
    Build the URL for the ReadingGoalProgress partial endpoint.

    Args:
        data: Dictionary containing year parameter

    Returns:
        Complete URL with query parameters
    """
    # ReadingGoalProgress uses 'year' query param directly, not 'data'
    year = data.get('year', '')
    params = {'_component': 'ReadingGoalProgress', 'year': year}
    query_string = urllib.parse.urlencode(params)
    return f"{BASE_URL}?{query_string}"


def make_request(
    session: requests.Session, data: dict, description: str
) -> dict[str, Any]:
    """
    Make a request to the ReadingGoalProgress endpoint and return the response.

    Args:
        session: Authenticated requests session
        data: The data payload to send
        description: Description of the test case

    Returns:
        Response dictionary or error dictionary
    """
    url = build_reading_goal_progress_url(data)

    print(f"\n{'=' * 60}")
    print(f"Test: {description}")
    print(f"{'=' * 60}")
    print(f"URL: {url}")

    try:
        response = session.get(url, headers=FIREFOX_HEADERS, timeout=30)
        print(f"Status Code: {response.status_code}")
        print(f"Content-Type: {response.headers.get('content-type', 'unknown')}")

        if response.status_code == 200:
            try:
                result = response.json()
                print(f"Response keys: {list(result.keys())}")
                if 'partials' in result:
                    partials_preview = str(result['partials'])[:200]
                    print(f"Partials preview: {partials_preview}...")
                return result
            except json.JSONDecodeError as e:
                print(f"Failed to parse JSON: {e}")
                return {'error': f'JSON parse error: {e}', 'raw': response.text[:200]}
        else:
            print(f"Error response: {response.text[:200]}")
            return {'error': f'HTTP {response.status_code}', 'raw': response.text[:200]}

    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return {'error': str(e)}


@pytest.fixture
def session():
    """Create an authenticated session for testing."""
    s = requests.Session()
    s.headers.update(FIREFOX_HEADERS)

    # Login first
    if not login(s):
        pytest.skip("Could not login - skipping authenticated tests")

    yield s
    s.close()


@pytest.mark.integration
def test_reading_goal_progress_default_year(session):
    """Test ReadingGoalProgress with default year (current year)."""
    data = {}
    result = make_request(session, data, "Test with default year")
    assert 'error' not in result, f"Request failed: {result.get('error')}"
    assert 'partials' in result, "Response should contain 'partials' key"
    print("\n✓ Success! Got partials content")


@pytest.mark.integration
def test_reading_goal_progress_specific_year(session):
    """Test ReadingGoalProgress with a specific year."""
    data = {'year': 2024}
    result = make_request(session, data, "Test with specific year (2024)")
    assert 'error' not in result, f"Request failed: {result.get('error')}"
    assert 'partials' in result, "Response should contain 'partials' key"
    print("\n✓ Success! Got partials content")


@pytest.mark.integration
def test_reading_goal_progress_future_year(session):
    """Test ReadingGoalProgress with a future year."""
    data = {'year': 2025}
    result = make_request(session, data, "Test with future year (2025)")
    assert 'error' not in result, f"Request failed: {result.get('error')}"
    assert 'partials' in result, "Response should contain 'partials' key"
    print("\n✓ Success! Got partials content")


def run_all_tests():
    """Run all tests and print summary."""
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    # Create session and login
    s = requests.Session()
    s.headers.update(FIREFOX_HEADERS)

    if not login(s):
        print("✗ Could not login - tests cannot run")
        return False

    print("✓ Successfully logged in")

    tests = [
        ("Test with default year", test_reading_goal_progress_default_year),
        ("Test with specific year (2024)", test_reading_goal_progress_specific_year),
        ("Test with future year (2025)", test_reading_goal_progress_future_year),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            test_func(s)
            passed += 1
            print(f"✓ {name}: PASSED")
        except AssertionError as e:
            failed += 1
            print(f"✗ {name}: FAILED - {e}")
        except (RuntimeError, ValueError, TypeError) as e:
            failed += 1
            print(f"✗ {name}: ERROR - {e}")

    s.close()

    print("=" * 60)
    print(f"Total: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("=" * 60)

    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
