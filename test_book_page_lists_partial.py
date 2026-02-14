#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.31.0",
#     "pytest>=8.3.4",
# ]
# ///
"""
Test script for BookPageListsPartial endpoint.

This script makes HTTP requests to localhost:8080 to test the /partials.json
endpoint with the BPListsSection component. It helps understand how the endpoint
works and validates its behavior with various inputs.

Usage with uv:
    uv run test_book_page_lists_partial.py

Or with Python directly (requires requests to be installed):
    python test_book_page_lists_partial.py

Requirements:
    - OpenLibrary server running on localhost:8080
"""

import sys
import urllib.parse
from typing import Any

import pytest
import requests

# Base URL for the BPListsSection partials endpoint
BASE_URL = "http://localhost:8080/partials/BPListsSection.json"


def build_book_lists_url(workId: str, editionId: str) -> str:
    """
    Build the URL for the BPListsSection partial endpoint.

    Matches the JavaScript buildPartialsUrl function behavior,
    which uses separate query parameters (not JSON data).

    Args:
        workId: The work ID (e.g., '/works/OL53924W')
        editionId: The edition ID (e.g., '/books/OL7353617M')

    Returns:
        Complete URL with query parameters
    """
    params = {'workId': workId, 'editionId': editionId}
    query_string = urllib.parse.urlencode(params)
    return f"{BASE_URL}?{query_string}"


def make_request(workId: str, editionId: str, description: str) -> dict[str, Any]:
    """
    Make a request to the BPListsSection endpoint and return the response.

    Args:
        workId: The work ID
        editionId: The edition ID
        description: Description of the test case for logging

    Returns:
        Parsed JSON response from the server
    """
    url = build_book_lists_url(workId, editionId)

    print(f"\n{'=' * 60}")
    print(f"Test: {description}")
    print(f"{'=' * 60}")
    print(f"Request URL: {url}")
    print(f"workId: {workId}")
    print(f"editionId: {editionId}")

    try:
        response = requests.get(url, timeout=30)
        print(f"\nStatus Code: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print(f"\nResponse Keys: {list(result.keys())}")

            if 'hasLists' in result:
                print(f"\nhasLists: {result['hasLists']}")

            if 'partials' in result:
                partials = result['partials']
                if isinstance(partials, list) and len(partials) > 0:
                    partial_preview = (
                        partials[0][:200] if len(partials[0]) > 200 else partials[0]
                    )
                    print(f"\nPartials HTML (first 200 chars):\n{partial_preview}...")
                else:
                    print(f"\nPartials: {partials}")

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
def test_with_work_id():
    """Test with a work ID."""
    return make_request(
        workId='/works/OL54120W',
        editionId='',
        description="Book page lists with work ID",
    )


@pytest.mark.integration
def test_with_edition_id():
    """Test with an edition ID."""
    return make_request(
        workId='',
        editionId='/books/OL2058361M',
        description="Book page lists with edition ID",
    )


@pytest.mark.integration
def test_with_both_ids():
    """Test with both work and edition IDs."""
    return make_request(
        workId='/works/OL54120W',
        editionId='/books/OL2058361M',
        description="Book page lists with both work and edition IDs",
    )


@pytest.mark.integration
def test_with_empty_ids():
    """Test with empty IDs (should return no lists)."""
    return make_request(
        workId='', editionId='', description="Book page lists with empty IDs"
    )


@pytest.mark.integration
def test_with_nonexistent_work():
    """Test with a non-existent work ID."""
    return make_request(
        workId='/works/OL99999999W',
        editionId='',
        description="Book page lists with non-existent work ID",
    )


def run_all_tests():
    """Run all test cases and summarize results."""
    print("\n" + "=" * 60)
    print("BookPageListsPartial Endpoint Tests")
    print("=" * 60)
    print(f"Testing against: {BASE_URL}")
    print("Make sure your OpenLibrary server is running on localhost:8080")

    tests = [
        ("Work ID", test_with_work_id),
        ("Edition ID", test_with_edition_id),
        ("Both IDs", test_with_both_ids),
        ("Empty IDs", test_with_empty_ids),
        ("Non-existent Work", test_with_nonexistent_work),
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
