#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.31.0",
#     "pytest>=8.3.4",
# ]
# ///
"""
Test script for FullTextSuggestionsPartial endpoint.

This script makes HTTP requests to localhost:8080 to test the /partials.json
endpoint with the FullTextSuggestions component. It helps understand how the endpoint
works and validates its behavior with various inputs.

Usage with uv:
    uv run test_fulltext_suggestions_partial.py

Or with Python directly (requires requests to be installed):
    python test_fulltext_suggestions_partial.py

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

# Firefox-like headers for realistic requests
FIREFOX_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}


def build_fulltext_suggestions_url(data: dict) -> str:
    """
    Build the URL for the FulltextSearchSuggestion partial endpoint.

    Matches the JavaScript buildPartialsUrl function behavior.

    Args:
        data: Dictionary containing query string

    Returns:
        Complete URL with query parameters
    """
    params = {'_component': 'FulltextSearchSuggestion', 'data': json.dumps(data)}
    query_string = urllib.parse.urlencode(params)
    return f"{BASE_URL}?{query_string}"


def make_request(data: dict, description: str) -> dict[str, Any]:
    """
    Make a request to the FullTextSuggestions endpoint and return the response.

    Args:
        data: The data payload to send
        description: Description of the test case

    Returns:
        Response dictionary or error dictionary
    """
    url = build_fulltext_suggestions_url(data)

    print(f"\n{'=' * 60}")
    print(f"Test: {description}")
    print(f"{'=' * 60}")
    print(f"URL: {url}")

    try:
        response = requests.get(url, headers=FIREFOX_HEADERS, timeout=30)
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


@pytest.mark.integration
def test_fulltext_suggestions_with_query():
    """Test FullTextSuggestions with a search query."""
    data = {'query': 'python programming'}
    result = make_request(data, "Test with search query")
    assert 'error' not in result, f"Request failed: {result.get('error')}"
    assert 'partials' in result, "Response should contain 'partials' key"
    print("\n✓ Success! Got partials content")


@pytest.mark.integration
def test_fulltext_suggestions_empty_query():
    """Test FullTextSuggestions with empty query."""
    data = {'query': ''}
    result = make_request(data, "Test with empty query")
    assert 'error' not in result, f"Request failed: {result.get('error')}"
    assert 'partials' in result, "Response should contain 'partials' key"
    print("\n✓ Success! Got partials content")


@pytest.mark.integration
def test_fulltext_suggestions_simple_word():
    """Test FullTextSuggestions with a simple word."""
    data = {'query': 'shakespeare'}
    result = make_request(data, "Test with simple word")
    assert 'error' not in result, f"Request failed: {result.get('error')}"
    assert 'partials' in result, "Response should contain 'partials' key"
    print("\n✓ Success! Got partials content")


def run_all_tests():
    """Run all tests and print summary."""
    tests = [
        ("Test with search query", test_fulltext_suggestions_with_query),
        ("Test with empty query", test_fulltext_suggestions_empty_query),
        ("Test with simple word", test_fulltext_suggestions_simple_word),
    ]

    passed = 0
    failed = 0

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    for name, test_func in tests:
        try:
            test_func()
            passed += 1
            print(f"✓ {name}: PASSED")
        except AssertionError as e:
            failed += 1
            print(f"✗ {name}: FAILED - {e}")
        except (
            requests.exceptions.RequestException,
            json.JSONDecodeError,
            ValueError,
        ) as e:
            failed += 1
            print(f"✗ {name}: ERROR - {e}")

    print("=" * 60)
    print(f"Total: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("=" * 60)

    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
