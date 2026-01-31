#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.31.0",
#     "pytest>=8.3.4",
# ]
# ///
"""
Compare legacy and FastAPI ReadingGoalProgressPartial endpoints.

This script makes HTTP requests to both localhost:8080 (legacy web.py)
and localhost:18080 (FastAPI) to verify they return identical results
for the same inputs.

Usage with uv:
    uv run test_reading_goal_progress_comparison.py

Or with pytest:
    pytest -m integration test_reading_goal_progress_comparison.py

Requirements:
    - Legacy OpenLibrary server running on localhost:8080
    - FastAPI server running on localhost:18080
"""

import json
import sys
from typing import Any

import pytest
import requests

LEGACY_URL = "http://localhost:8080/partials.json"
FASTAPI_URL = "http://localhost:18080/partials.json"

# Firefox-like headers for realistic requests
FIREFOX_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}


def normalize_html(html: str) -> str:
    """
    Normalize HTML for comparison by removing whitespace differences.

    Args:
        html: HTML string to normalize

    Returns:
        Normalized HTML string
    """
    lines = html.split('\n')
    lines = [line.strip() for line in lines if line.strip()]
    return ' '.join(lines)


def make_request(base_url: str, data: dict) -> dict[str, Any]:
    """
    Make a request to the ReadingGoalProgress endpoint.

    Args:
        base_url: Base URL for the endpoint
        data: The data payload to send

    Returns:
        Response dictionary or error dictionary
    """
    params = {'_component': 'ReadingGoalProgress', 'data': json.dumps(data)}

    try:
        response = requests.get(
            base_url, params=params, headers=FIREFOX_HEADERS, timeout=30
        )
        if response.status_code == 200:
            return response.json()
        else:
            return {'error': f'HTTP {response.status_code}', 'raw': response.text[:200]}
    except requests.exceptions.RequestException as e:
        return {'error': str(e)}


@pytest.mark.integration
def test_compare_reading_goal_progress_default_year():
    """Compare legacy and FastAPI endpoints with default year."""
    data = {}

    legacy_result = make_request(LEGACY_URL, data)
    fastapi_result = make_request(FASTAPI_URL, data)

    print(f"\n{'=' * 60}")
    print("Test: Compare with default year")
    print(f"{'=' * 60}")
    print(f"Data: {data}")

    # Check for errors
    assert 'error' not in legacy_result, f"Legacy error: {legacy_result.get('error')}"
    assert (
        'error' not in fastapi_result
    ), f"FastAPI error: {fastapi_result.get('error')}"

    # Compare response keys
    assert list(legacy_result.keys()) == list(
        fastapi_result.keys()
    ), f"Key mismatch: {legacy_result.keys()} vs {fastapi_result.keys()}"

    # Compare partials content (normalize HTML)
    if 'partials' in legacy_result:
        legacy_partials = normalize_html(str(legacy_result['partials']))
        fastapi_partials = normalize_html(str(fastapi_result['partials']))
        assert (
            legacy_partials == fastapi_partials
        ), f"Partials mismatch:\nLegacy: {legacy_partials[:200]}...\nFastAPI: {fastapi_partials[:200]}..."

    print("✓ Both endpoints returned identical results!")


@pytest.mark.integration
def test_compare_reading_goal_progress_specific_year():
    """Compare legacy and FastAPI endpoints with specific year."""
    data = {'year': 2024}

    legacy_result = make_request(LEGACY_URL, data)
    fastapi_result = make_request(FASTAPI_URL, data)

    print(f"\n{'=' * 60}")
    print("Test: Compare with specific year (2024)")
    print(f"{'=' * 60}")
    print(f"Data: {data}")

    # Check for errors
    assert 'error' not in legacy_result, f"Legacy error: {legacy_result.get('error')}"
    assert (
        'error' not in fastapi_result
    ), f"FastAPI error: {fastapi_result.get('error')}"

    # Compare response keys
    assert list(legacy_result.keys()) == list(
        fastapi_result.keys()
    ), f"Key mismatch: {legacy_result.keys()} vs {fastapi_result.keys()}"

    # Compare partials content (normalize HTML)
    if 'partials' in legacy_result:
        legacy_partials = normalize_html(str(legacy_result['partials']))
        fastapi_partials = normalize_html(str(fastapi_result['partials']))
        assert (
            legacy_partials == fastapi_partials
        ), f"Partials mismatch:\nLegacy: {legacy_partials[:200]}...\nFastAPI: {fastapi_partials[:200]}..."

    print("✓ Both endpoints returned identical results!")


@pytest.mark.integration
def test_compare_reading_goal_progress_future_year():
    """Compare legacy and FastAPI endpoints with future year."""
    data = {'year': 2025}

    legacy_result = make_request(LEGACY_URL, data)
    fastapi_result = make_request(FASTAPI_URL, data)

    print(f"\n{'=' * 60}")
    print("Test: Compare with future year (2025)")
    print(f"{'=' * 60}")
    print(f"Data: {data}")

    # Check for errors
    assert 'error' not in legacy_result, f"Legacy error: {legacy_result.get('error')}"
    assert (
        'error' not in fastapi_result
    ), f"FastAPI error: {fastapi_result.get('error')}"

    # Compare response keys
    assert list(legacy_result.keys()) == list(
        fastapi_result.keys()
    ), f"Key mismatch: {legacy_result.keys()} vs {fastapi_result.keys()}"

    # Compare partials content (normalize HTML)
    if 'partials' in legacy_result:
        legacy_partials = normalize_html(str(legacy_result['partials']))
        fastapi_partials = normalize_html(str(fastapi_result['partials']))
        assert (
            legacy_partials == fastapi_partials
        ), f"Partials mismatch:\nLegacy: {legacy_partials[:200]}...\nFastAPI: {fastapi_partials[:200]}..."

    print("✓ Both endpoints returned identical results!")


def run_all_tests():
    """Run all comparison tests and print summary."""
    tests = [
        ("Compare with default year", test_compare_reading_goal_progress_default_year),
        (
            "Compare with specific year (2024)",
            test_compare_reading_goal_progress_specific_year,
        ),
        (
            "Compare with future year (2025)",
            test_compare_reading_goal_progress_future_year,
        ),
    ]

    passed = 0
    failed = 0

    print("\n" + "=" * 60)
    print("COMPARISON TEST SUMMARY")
    print("=" * 60)

    for name, test_func in tests:
        try:
            test_func()
            passed += 1
            print(f"✓ {name}: PASSED")
        except AssertionError as e:
            failed += 1
            print(f"✗ {name}: FAILED - {e}")
        except (RuntimeError, ValueError, TypeError) as e:
            failed += 1
            print(f"✗ {name}: ERROR - {e}")

    print("=" * 60)
    print(f"Total: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("=" * 60)

    if passed == len(tests):
        print("\n✓ All endpoints return identical results!")
    else:
        print(f"\n✗ {failed} test(s) failed - endpoints may differ")

    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
