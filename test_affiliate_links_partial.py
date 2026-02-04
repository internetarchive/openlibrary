#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.31.0",
#     "pytest>=8.3.4",
# ]
# ///
"""
Test script for AffiliateLinksPartial endpoint.

This script makes HTTP requests to localhost:8080 to test the /partials.json
endpoint with the AffiliateLinks component. It helps understand how the endpoint
works and validates its behavior with various inputs.

Usage with uv:
    uv run test_affiliate_links_partial.py

Or with Python directly (requires requests to be installed):
    python test_affiliate_links_partial.py

Requirements:
    - OpenLibrary server running on localhost:8080
"""

import json
import urllib.parse
from typing import Any

import pytest
import requests

# Base URL for the partials endpoint
BASE_URL = "http://localhost:8080/partials.json"


def build_affiliate_links_url(data: dict) -> str:
    """
    Build the URL for the AffiliateLinks partial endpoint.

    Matches the JavaScript buildPartialsUrl function behavior.

    Args:
        data: Dictionary containing args with book info

    Returns:
        Complete URL with query parameters
    """
    params = {'_component': 'AffiliateLinks', 'data': json.dumps(data)}
    query_string = urllib.parse.urlencode(params)
    return f"{BASE_URL}?{query_string}"


def make_request(data: dict, description: str) -> dict[str, Any]:
    """
    Make a request to the AffiliateLinks endpoint and return the response.

    Args:
        data: The data payload to send
        description: Description of the test case

    Returns:
        Response dictionary or error dictionary
    """
    url = build_affiliate_links_url(data)

    print(f"\n{'=' * 60}")
    print(f"Test: {description}")
    print(f"{'=' * 60}")
    print(f"URL: {url}")

    try:
        response = requests.get(url, timeout=30)
        print(f"Status Code: {response.status_code}")
        print(f"Content-Type: {response.headers.get('content-type', 'unknown')}")

        if response.status_code == 200:
            try:
                result = response.json()
                print(f"Response keys: {list(result.keys())}")
                if 'partials' in result:
                    partials = result['partials']
                    print(f"Partials length: {len(partials)} chars")
                    print("Partials preview (first 500 chars):")
                    print(partials[:500])
                return result
            except json.JSONDecodeError as e:
                print(f"JSON Decode Error: {e}")
                print(f"Response text (first 500 chars): {response.text[:500]}")
                return {
                    'error': f'json_decode_error: {e}',
                    'status_code': response.status_code,
                }
        else:
            print(f"Error Response (first 500 chars): {response.text[:500]}")
            return {'error': response.text, 'status_code': response.status_code}

    except requests.exceptions.ConnectionError:
        print(f"Connection Error: Could not connect to {BASE_URL}")
        print("Make sure the server is running on localhost:8080")
        return {'error': 'connection_failed'}
    except requests.exceptions.RequestException as e:
        print(f"Request Error: {e}")
        return {'error': str(e)}


@pytest.mark.integration
def test_affiliate_links_with_isbn():
    """Test AffiliateLinks with ISBN and title."""
    data = {
        'args': [
            'Pride and Prejudice',  # title string
            {'isbn': ['9780141439518']},  # opts dict
        ]
    }
    result = make_request(data, "AffiliateLinks with ISBN")
    assert 'error' not in result, f"Request failed: {result.get('error')}"
    assert 'partials' in result, "Response missing 'partials' key"
    return result


@pytest.mark.integration
def test_affiliate_links_without_isbn():
    """Test AffiliateLinks without ISBN (only title and work ID)."""
    data = {
        'args': [
            'Pride and Prejudice',  # title string
            {},  # empty opts dict
        ]
    }
    result = make_request(data, "AffiliateLinks without ISBN")
    assert 'error' not in result, f"Request failed: {result.get('error')}"
    assert 'partials' in result, "Response missing 'partials' key"
    return result


@pytest.mark.integration
def test_affiliate_links_empty_args():
    """Test AffiliateLinks with empty args (should error)."""
    data = {'args': []}
    result = make_request(data, "AffiliateLinks with empty args")
    # This should return an error since we need at least 2 args
    assert 'error' in result or result.get('status_code', 200) != 200
    return result


@pytest.mark.integration
def test_affiliate_links_single_arg():
    """Test AffiliateLinks with single arg (should error)."""
    data = {
        'args': [
            'Pride and Prejudice',  # title string
        ]
    }
    result = make_request(data, "AffiliateLinks with single arg")
    # This should return an error since we need at least 2 args
    assert 'error' in result or result.get('status_code', 200) != 200
    return result


def run_tests():
    """Run all AffiliateLinks tests."""
    print("\n" + "=" * 60)
    print("AffiliateLinksPartial Endpoint Tests")
    print("=" * 60)
    print(f"Base URL: {BASE_URL}")
    print("\nMake sure the server is running on localhost:8080")

    tests = [
        ("With ISBN", test_affiliate_links_with_isbn),
        ("Without ISBN", test_affiliate_links_without_isbn),
        ("Empty args", test_affiliate_links_empty_args),
        ("Single arg", test_affiliate_links_single_arg),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            success = 'error' not in result or name in ("Empty args", "Single arg")
            results.append((name, success))
        except (KeyError, ValueError, TypeError, AssertionError) as e:
            print(f"\nTest '{name}' raised exception: {e}")
            import traceback

            traceback.print_exc()
            results.append((name, False))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠️ {total - passed} test(s) failed")

    return results


if __name__ == '__main__':
    run_tests()
