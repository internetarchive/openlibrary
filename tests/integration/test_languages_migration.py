#!/usr/bin/env python3
"""
Test script to verify languages_json endpoint migration from web.py to FastAPI.
Makes real HTTP requests to localhost:8080 (web.py) and localhost:18080 (FastAPI).

Note: web.py returns database objects, FastAPI returns subject-style format.
This test verifies both endpoints work correctly.
"""

import json
import sys

import requests


class TestResult:
    """Track test results for colored output."""

    PASSED = "\033[0;32m✓\033[0m"
    FAILED = "\033[0;31m✗\033[0m"
    WARNING = "\033[1;33m⚠\033[0m"
    INFO = "\033[1;33m→\033[0m"


WEBPY_URL = "http://localhost:8080"
FASTAPI_URL = "http://localhost:18080"


def check_servers():
    """Check if both servers are running."""
    print("Checking if servers are running...")

    try:
        response = requests.get(f"{WEBPY_URL}/", timeout=5)
        if response.status_code in (200, 404):
            print(f"{TestResult.PASSED} web.py server running on port 8080")
        else:
            print(
                f"{TestResult.WARNING} web.py server returned unexpected status: {response.status_code}"
            )
    except requests.exceptions.RequestException:
        print(f"{TestResult.FAILED} web.py server not running on port 8080")
        print("Please start the web.py server first")
        sys.exit(1)

    try:
        response = requests.get(f"{FASTAPI_URL}/health", timeout=5)
        if response.status_code == 200:
            print(f"{TestResult.PASSED} FastAPI server running on port 18080")
        else:
            print(
                f"{TestResult.WARNING} FastAPI health check returned: {response.status_code}"
            )
    except requests.exceptions.RequestException:
        print(f"{TestResult.FAILED} FastAPI server not running on port 18080")
        print("Please start the FastAPI server first")
        sys.exit(1)

    print()


def test_endpoint(name: str, path: str, query: dict[str, str]) -> bool:
    """Test a single endpoint against both implementations.

    Note: web.py returns database objects, FastAPI returns subject-style format.
    Both should work correctly even though structures differ.
    """
    print(f"{TestResult.INFO} Testing: {name}")
    print(f"  Path: {path}")
    if query:
        query_string = "&".join(f"{k}={v}" for k, v in query.items())
        print(f"  Query: ?{query_string}")

    # Build URLs
    webpy_url = f"{WEBPY_URL}{path}.json"
    fastapi_url = f"{FASTAPI_URL}{path}.json"

    # Make requests
    try:
        webpy_response = requests.get(webpy_url, params=query, timeout=10)
        fastapi_response = requests.get(fastapi_url, params=query, timeout=10)
    except requests.exceptions.RequestException as e:
        print(f"  {TestResult.FAILED} Request failed: {e}")
        return False

    # Check both return 200
    if webpy_response.status_code != 200:
        print(f"  {TestResult.FAILED} web.py returned {webpy_response.status_code}")
        return False

    if fastapi_response.status_code != 200:
        print(f"  {TestResult.FAILED} FastAPI returned {fastapi_response.status_code}")
        return False

    # Check both return valid JSON
    try:
        webpy_json = webpy_response.json()
        fastapi_json = fastapi_response.json()
    except json.JSONDecodeError as e:
        print(f"  {TestResult.FAILED} Invalid JSON: {e}")
        return False

    # For FastAPI, check it has expected subject-style fields
    for field in ("key", "name", "work_count", "works"):
        if field not in fastapi_json:
            print(f"  {TestResult.FAILED} FastAPI missing required field: {field}")
            return False

    # For web.py, just check it has basic fields
    if "key" not in webpy_json or "name" not in webpy_json:
        print(f"  {TestResult.FAILED} web.py missing required fields (key or name)")
        return False

    print(
        f"  {TestResult.PASSED} Both endpoints return valid responses (different structures)"
    )
    print()
    return True


def main():
    """Run all tests."""
    print("=" * 50)
    print("Testing languages_json endpoint migration")
    print("=" * 50)
    print()

    # Check servers
    check_servers()

    # Test cases
    tests = [
        ("Basic language query", "/languages/eng", {}),
        ("With limit", "/languages/eng", {"limit": "5"}),
        ("With pagination (offset)", "/languages/eng", {"offset": "10", "limit": "5"}),
        ("With details=true", "/languages/eng", {"details": "true"}),
        ("With has_fulltext=true", "/languages/eng", {"has_fulltext": "true"}),
        ("With published_in range", "/languages/eng", {"published_in": "2000-2010"}),
        ("With published_in year", "/languages/eng", {"published_in": "2000"}),
        ("With sort=new", "/languages/eng", {"sort": "new"}),
    ]

    print("Running test cases...")
    print("=" * 50)
    print()

    passed = 0
    failed = 0

    for name, path, query in tests:
        if test_endpoint(name, path, query):
            passed += 1
        else:
            failed += 1

    # Error case test
    print(f"{TestResult.INFO} Testing: Excessive limit (should return non-200)")
    print("  Path: /languages/eng")
    print("  Query: ?limit=2001")
    print("  Note: FastAPI validates limit, web.py does not")

    try:
        requests.get(
            f"{WEBPY_URL}/languages/eng.json", params={"limit": 2001}, timeout=10
        )
        fastapi_response = requests.get(
            f"{FASTAPI_URL}/languages/eng.json", params={"limit": 2001}, timeout=10
        )

        # FastAPI should return error, web.py doesn't validate
        if fastapi_response.status_code != 200:
            print(
                f"  {TestResult.PASSED} FastAPI correctly returned error status {fastapi_response.status_code}"
            )
            passed += 1
        else:
            print(f"  {TestResult.FAILED} FastAPI returned 200 instead of error status")
            failed += 1
    except requests.exceptions.RequestException as e:
        print(f"  {TestResult.FAILED} Request failed: {e}")
        failed += 1

    print()
    print("=" * 50)
    print(f"All tests completed! Passed: {passed}, Failed: {failed}")
    print("=" * 50)
    print()

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
