#!/usr/bin/env python3
"""
TODO: Delete before merge
Test script to verify publishers_json endpoint migration from web.py to FastAPI.
Makes real HTTP requests to localhost:8080 (web.py) and localhost:18080 (FastAPI).
Compares responses to ensure parity.
"""

import json
import sys
from typing import TypedDict

import requests


class TestResult:
    """Track test results for colored output."""

    PASSED = "\033[0;32m✓\033[0m"
    FAILED = "\033[0;31m✗\033[0m"
    WARNING = "\033[1;33m⚠\033[0m"
    INFO = "\033[1;33m→\033[0m"


class PublisherTestConfig(TypedDict):
    """Configuration for a single test case."""

    name: str
    path: str
    query: dict[str, str]


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


def check_endpoint(name: str, path: str, query: dict[str, str]) -> bool:
    """Test a single endpoint against both implementations."""
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

    # Compare status codes
    if webpy_response.status_code != fastapi_response.status_code:
        print(
            f"  {TestResult.FAILED} Status code mismatch: webpy={webpy_response.status_code}, fastapi={fastapi_response.status_code}"
        )
        return False

    # For 200 responses, compare JSON structure
    if webpy_response.status_code == 200:
        try:
            webpy_json = webpy_response.json()
            fastapi_json = fastapi_response.json()
        except json.JSONDecodeError as e:
            print(f"  {TestResult.FAILED} Invalid JSON: {e}")
            return False

        # Compare top-level keys
        webpy_keys = set(webpy_json.keys())
        fastapi_keys = set(fastapi_json.keys())

        if webpy_keys != fastapi_keys:
            print(f"  {TestResult.FAILED} Top-level keys mismatch")
            print(f"    webpy: {sorted(webpy_keys)}")
            print(f"    fastapi: {sorted(fastapi_keys)}")
            return False

        # Check required fields
        for field in ("key", "name", "work_count", "works"):
            if field not in webpy_json or field not in fastapi_json:
                print(
                    f"  {TestResult.FAILED} Field '{field}' missing from one or both responses"
                )
                return False

        print(f"  {TestResult.PASSED} Response structures match")
    else:
        print(f"  {TestResult.PASSED} Both returned {webpy_response.status_code}")

    print()
    return True


def main():
    """Run all tests."""
    print("=" * 50)
    print("Testing publishers_json endpoint migration")
    print("=" * 50)
    print()

    # Check servers
    check_servers()

    # Test cases
    tests = [
        ("Basic publisher query", "/publishers/Penguin_Books", {}),
        ("With limit", "/publishers/Penguin_Books", {"limit": "5"}),
        (
            "With pagination (offset)",
            "/publishers/Penguin_Books",
            {"offset": "10", "limit": "5"},
        ),
        ("With details=true", "/publishers/Penguin_Books", {"details": "true"}),
        (
            "With has_fulltext=true",
            "/publishers/Penguin_Books",
            {"has_fulltext": "true"},
        ),
        (
            "With published_in range",
            "/publishers/Penguin_Books",
            {"published_in": "2000-2010"},
        ),
        (
            "With published_in year",
            "/publishers/Penguin_Books",
            {"published_in": "2000"},
        ),
        ("With sort=new", "/publishers/Penguin_Books", {"sort": "new"}),
    ]

    print("Running test cases...")
    print("=" * 50)
    print()

    passed = 0
    failed = 0

    for name, path, query in tests:
        if check_endpoint(name, path, query):
            passed += 1
        else:
            failed += 1

    # Error case test
    print(f"{TestResult.INFO} Testing: Excessive limit (should return non-200)")
    print("  Path: /publishers/Penguin_Books")
    print("  Query: ?limit=2001")

    try:
        webpy_response = requests.get(
            f"{WEBPY_URL}/publishers/Penguin_Books.json",
            params={"limit": 2001},
            timeout=10,
        )
        fastapi_response = requests.get(
            f"{FASTAPI_URL}/publishers/Penguin_Books.json",
            params={"limit": 2001},
            timeout=10,
        )

        if webpy_response.status_code != 200 and fastapi_response.status_code != 200:
            print(
                f"  {TestResult.PASSED} Both correctly returned error statuses (webpy={webpy_response.status_code}, fastapi={fastapi_response.status_code})"
            )
            passed += 1
        else:
            print(
                f"  {TestResult.FAILED} One or both returned 200: webpy={webpy_response.status_code}, fastapi={fastapi_response.status_code}"
            )
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
