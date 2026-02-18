#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.31.0",
#     "pytest>=8.3.4",
# ]
# ///
"""
Test script for CarouselLoadMorePartial endpoint.

This script makes HTTP requests to localhost:8080 to test the
/partials/CarouselLoadMore.json endpoint.  It helps understand how the
endpoint works and validates its behavior with various query types.

Usage with uv:
    uv run test_carousel_load_more_partial.py

Or with Python directly (requires requests to be installed):
    python test_carousel_load_more_partial.py

Requirements:
    - OpenLibrary server running on localhost:8080
"""

import sys
import urllib.parse
from typing import Any

import pytest
import requests

# Base URL for the CarouselLoadMore partials endpoint
BASE_URL = "http://localhost:8080/partials/CarouselLoadMore.json"


def build_url(params: dict | None = None) -> str:
    """
    Build the URL for the CarouselLoadMore partial endpoint.

    Matches the JavaScript buildPartialsUrl function behavior:
        buildPartialsUrl('CarouselLoadMore', {...})

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
    Make a request to the CarouselLoadMore endpoint and return the response.

    Args:
        description: Description of the test case for logging
        params: Optional query parameters to include

    Returns:
        Parsed JSON response from the server, or dict with error info
    """
    url = build_url(params)

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
                cards = result['partials']
                print(f"\nNumber of cards: {len(cards)}")
                if cards:
                    preview = cards[0][:200] if len(cards[0]) > 200 else cards[0]
                    print(f"First card HTML (first 200 chars):\n{preview}")

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
def test_search_query_type():
    """Test with SEARCH queryType."""
    result = make_request(
        description="SEARCH queryType",
        params={'queryType': 'SEARCH', 'q': 'python programming', 'limit': 5},
    )
    assert 'partials' in result
    assert isinstance(result['partials'], list)


@pytest.mark.integration
def test_trending_query_type():
    """Test with TRENDING queryType."""
    result = make_request(
        description="TRENDING queryType",
        params={'queryType': 'TRENDING', 'limit': 5},
    )
    assert 'partials' in result
    assert isinstance(result['partials'], list)


@pytest.mark.integration
def test_subjects_query_type():
    """Test with SUBJECTS queryType."""
    result = make_request(
        description="SUBJECTS queryType",
        params={'queryType': 'SUBJECTS', 'q': '/subjects/science', 'limit': 5},
    )
    assert 'partials' in result
    assert isinstance(result['partials'], list)


@pytest.mark.integration
def test_response_is_list_of_html_strings():
    """Test that the partials response is a list of HTML strings."""
    result = make_request(
        description="Verify partials is a list of HTML strings",
        params={'queryType': 'TRENDING', 'limit': 3},
    )
    assert 'partials' in result
    cards = result['partials']
    assert isinstance(cards, list)
    for card in cards:
        assert isinstance(card, str)


@pytest.mark.integration
def test_has_fulltext_only_true():
    """Test with hasFulltextOnly=true."""
    result = make_request(
        description="hasFulltextOnly=true",
        params={
            'queryType': 'SEARCH',
            'q': 'history',
            'limit': 5,
            'hasFulltextOnly': 'true',
        },
    )
    assert 'partials' in result


@pytest.mark.integration
def test_pagination():
    """Test with page parameter."""
    result = make_request(
        description="Page 2",
        params={'queryType': 'TRENDING', 'limit': 5, 'page': 2},
    )
    assert 'partials' in result
    assert isinstance(result['partials'], list)


def run_all_tests():
    """Run all test cases and summarize results."""
    print("\n" + "=" * 60)
    print("CarouselLoadMorePartial Endpoint Tests")
    print("=" * 60)
    print(f"Testing against: {BASE_URL}")
    print("Make sure your OpenLibrary server is running on localhost:8080")

    tests = [
        (
            "SEARCH queryType",
            lambda: make_request(
                "SEARCH queryType",
                {'queryType': 'SEARCH', 'q': 'python programming', 'limit': 5},
            ),
        ),
        (
            "TRENDING queryType",
            lambda: make_request(
                "TRENDING queryType",
                {'queryType': 'TRENDING', 'limit': 5},
            ),
        ),
        (
            "SUBJECTS queryType",
            lambda: make_request(
                "SUBJECTS queryType",
                {'queryType': 'SUBJECTS', 'q': '/subjects/science', 'limit': 5},
            ),
        ),
        (
            "hasFulltextOnly=true",
            lambda: make_request(
                "hasFulltextOnly=true",
                {
                    'queryType': 'SEARCH',
                    'q': 'history',
                    'limit': 5,
                    'hasFulltextOnly': 'true',
                },
            ),
        ),
        (
            "Page 2",
            lambda: make_request(
                "Page 2",
                {'queryType': 'TRENDING', 'limit': 5, 'page': 2},
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
