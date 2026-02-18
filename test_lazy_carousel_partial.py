#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.31.0",
#     "pytest>=8.3.4",
# ]
# ///
"""
Test script for LazyCarouselPartial endpoint.

This script makes HTTP requests to localhost:8080 to test the
/partials/LazyCarousel.json endpoint.  It helps understand how the
endpoint works and validates its behavior with various inputs.

Usage with uv:
    uv run test_lazy_carousel_partial.py

Or with Python directly (requires requests to be installed):
    python test_lazy_carousel_partial.py

Requirements:
    - OpenLibrary server running on localhost:8080
"""

import sys
import urllib.parse
from typing import Any

import pytest
import requests

# Base URL for the LazyCarousel partials endpoint
BASE_URL = "http://localhost:8080/partials/LazyCarousel.json"


def build_lazy_carousel_url(params: dict | None = None) -> str:
    """
    Build the URL for the LazyCarousel partial endpoint.

    Matches the JavaScript buildPartialsUrl function behavior:
        buildPartialsUrl('LazyCarousel', {...data})

    Args:
        params: Optional dict of query parameters

    Returns:
        Complete URL with query parameters
    """
    if params:
        query_string = urllib.parse.urlencode(params)
        return f"{BASE_URL}?{query_string}"
    return BASE_URL


def make_request(
    description: str,
    params: dict | None = None,
) -> dict[str, Any]:
    """
    Make a request to the LazyCarousel endpoint and return the response.

    Args:
        description: Description of the test case for logging
        params: Optional query parameters to include

    Returns:
        Parsed JSON response from the server, or dict with error info
    """
    url = build_lazy_carousel_url(params)

    print(f"\n{'=' * 60}")
    print(f"Test: {description}")
    print(f"{'=' * 60}")
    print(f"Request URL: {url}")

    try:
        response = requests.get(url, timeout=30)
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


@pytest.mark.integration
def test_no_params():
    """Test without any parameters (uses all defaults)."""
    result = make_request(description="No params (all defaults)")
    assert 'partials' in result
    assert isinstance(result['partials'], str)


@pytest.mark.integration
def test_with_query():
    """Test with a search query."""
    result = make_request(
        description="With search query",
        params={'query': 'python programming'},
    )
    assert 'partials' in result
    assert isinstance(result['partials'], str)


@pytest.mark.integration
def test_with_all_params():
    """Test with all parameters explicitly provided."""
    result = make_request(
        description="All params provided",
        params={
            'query': 'science fiction',
            'title': 'Science Fiction Books',
            'sort': 'new',
            'key': 'test-carousel',
            'limit': 10,
            'search': 'true',
            'has_fulltext_only': 'false',
            'layout': 'carousel',
        },
    )
    assert 'partials' in result
    assert isinstance(result['partials'], str)


@pytest.mark.integration
def test_search_boolean_true():
    """Test that search=true is accepted."""
    result = make_request(
        description="search=true",
        params={'query': 'history', 'search': 'true'},
    )
    assert 'partials' in result


@pytest.mark.integration
def test_search_boolean_false():
    """Test that search=false is accepted."""
    result = make_request(
        description="search=false",
        params={'query': 'history', 'search': 'false'},
    )
    assert 'partials' in result


@pytest.mark.integration
def test_has_fulltext_only_false():
    """Test that has_fulltext_only=false is accepted."""
    result = make_request(
        description="has_fulltext_only=false",
        params={'query': 'cooking', 'has_fulltext_only': 'false'},
    )
    assert 'partials' in result


@pytest.mark.integration
def test_with_limit():
    """Test with a custom limit."""
    result = make_request(
        description="Custom limit of 5",
        params={'query': 'travel', 'limit': 5},
    )
    assert 'partials' in result


def run_all_tests():
    """Run all test cases and summarize results."""
    print("\n" + "=" * 60)
    print("LazyCarouselPartial Endpoint Tests")
    print("=" * 60)
    print(f"Testing against: {BASE_URL}")
    print("Make sure your OpenLibrary server is running on localhost:8080")

    tests = [
        ("No params", lambda: make_request("No params")),
        (
            "With query",
            lambda: make_request("With query", {'query': 'python programming'}),
        ),
        (
            "search=true",
            lambda: make_request("search=true", {'query': 'history', 'search': 'true'}),
        ),
        (
            "search=false",
            lambda: make_request(
                "search=false", {'query': 'history', 'search': 'false'}
            ),
        ),
        (
            "has_fulltext_only=false",
            lambda: make_request(
                "has_fulltext_only=false",
                {'query': 'cooking', 'has_fulltext_only': 'false'},
            ),
        ),
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
