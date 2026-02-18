#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.31.0",
#     "pytest>=8.3.4",
# ]
# ///
"""
Test script for MyBooksDropperListsPartial endpoint.

This script makes HTTP requests to localhost:8080 to test the
/partials/MyBooksDropperLists.json endpoint.  It helps understand how the
endpoint works and validates its behavior.

Note: This endpoint requires an authenticated user to return meaningful data.
The test will log in using the default dev credentials before making requests.

Usage with uv:
    uv run test_my_books_dropper_lists_partial.py

Or with Python directly (requires requests to be installed):
    python test_my_books_dropper_lists_partial.py

Requirements:
    - OpenLibrary server running on localhost:8080
"""

import sys
from typing import Any

import pytest
import requests

# Base URL for the MyBooksDropperLists partials endpoint
BASE_URL = "http://localhost:8080/partials/MyBooksDropperLists.json"

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


def make_request(
    description: str,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """
    Make a request to the MyBooksDropperLists endpoint and return the response.

    Args:
        description: Description of the test case for logging
        session: Optional requests.Session with auth cookies

    Returns:
        Parsed JSON response from the server, or dict with error info
    """
    requester = session or requests

    print(f"\n{'=' * 60}")
    print(f"Test: {description}")
    print(f"{'=' * 60}")
    print(f"Request URL: {BASE_URL}")

    try:
        response = requester.get(BASE_URL, timeout=30)
        print(f"\nStatus Code: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print(f"\nResponse Keys: {list(result.keys())}")

            if 'dropper' in result:
                html = result['dropper']
                preview = html[:200] if len(html) > 200 else html
                print(f"\nDropper HTML (first 200 chars):\n{preview}")

            if 'listData' in result:
                print(f"\nlistData keys: {list(result['listData'].keys())}")

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
def test_unauthenticated_request_returns_401():
    """Test that an unauthenticated request returns 401."""
    response = requests.get(BASE_URL, timeout=30)
    assert response.status_code == 401


@pytest.mark.integration
def test_authenticated_request_succeeds(logged_in_session):
    """Test that an authenticated request returns 200 with expected keys."""
    result = make_request(
        description="Authenticated request for dropper lists",
        session=logged_in_session,
    )
    assert 'dropper' in result
    assert 'listData' in result


@pytest.mark.integration
def test_dropper_is_html_string(logged_in_session):
    """Test that the dropper field is an HTML string."""
    result = make_request(
        description="Verify dropper field is HTML string",
        session=logged_in_session,
    )
    assert isinstance(result['dropper'], str)


@pytest.mark.integration
def test_list_data_is_dict(logged_in_session):
    """Test that listData is a dictionary."""
    result = make_request(
        description="Verify listData is a dict",
        session=logged_in_session,
    )
    assert isinstance(result['listData'], dict)


@pytest.mark.integration
def test_list_data_entries_have_expected_fields(logged_in_session):
    """Test that each entry in listData has 'members' and 'listName' fields."""
    result = make_request(
        description="Verify listData entries have expected fields",
        session=logged_in_session,
    )
    for key, value in result['listData'].items():
        assert 'members' in value, f"Entry {key} missing 'members'"
        assert 'listName' in value, f"Entry {key} missing 'listName'"


def run_all_tests():
    """Run all test cases and summarize results."""
    print("\n" + "=" * 60)
    print("MyBooksDropperListsPartial Endpoint Tests")
    print("=" * 60)
    print(f"Testing against: {BASE_URL}")
    print("Make sure your OpenLibrary server is running on localhost:8080")

    # Test unauthenticated request first
    print("\n--- Testing unauthenticated request ---")
    response = requests.get(BASE_URL, timeout=30)
    unauth_ok = response.status_code == 401
    print(
        f"Status: {response.status_code} (expected 401) - {'PASS' if unauth_ok else 'FAIL'}"
    )

    # Log in for authenticated tests
    session = requests.Session()
    response = login(session)
    if response.status_code != 303:
        print(f"Warning: Login returned status {response.status_code} (expected 303)")
        print("Tests will run without authentication.")
        session = None  # type: ignore[assignment]
    else:
        print(f"Logged in as {USERNAME}")

    tests = [
        (
            "Authenticated request",
            lambda: make_request("Authenticated request", session),
        ),
    ]

    results = [("Unauthenticated → 401", unauth_ok, {})]
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
