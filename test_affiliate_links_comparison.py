#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.31.0",
#     "pytest>=8.3.4",
# ]
# ///
"""
Test script for comparing AffiliateLinksPartial endpoints.

This script compares the legacy web.py endpoint (localhost:8080) with the
new FastAPI endpoint (localhost:18080) to ensure they return identical results.

Both endpoints now use the exact same interface:
    GET /partials.json?_component=AffiliateLinks&data={json}

Usage with uv:
    uv run test_affiliate_links_comparison.py

Requirements:
    - Legacy OpenLibrary server running on localhost:8080
    - FastAPI OpenLibrary server running on localhost:18080
"""

import json
import urllib.parse
from typing import Any

import pytest
import requests

# Base URLs for the endpoints - both use the same path now
LEGACY_URL = "http://localhost:8080/partials.json"
FASTAPI_URL = "http://localhost:18080/partials.json"

# Firefox-like headers to mimic a real browser
FIREFOX_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate, br',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
}


def build_url(base_url: str, data: dict) -> str:
    """Build the URL for the AffiliateLinks partial endpoint."""
    params = {'_component': 'AffiliateLinks', 'data': json.dumps(data)}
    query_string = urllib.parse.urlencode(params)
    return f"{base_url}?{query_string}"


def make_request(
    base_url: str, data: dict, description: str, endpoint_name: str
) -> dict[str, Any]:
    """Make a request to the endpoint and return the response."""
    url = build_url(base_url, data)

    print(f"\n{'=' * 60}")
    print(f"{endpoint_name} Test: {description}")
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
        print(f"Connection Error: Could not connect to {base_url}")
        print("Make sure the server is running")
        return {'error': 'connection_failed'}
    except requests.exceptions.RequestException as e:
        print(f"Request Error: {e}")
        return {'error': str(e)}


def normalize_html(html: str) -> str:
    """Normalize HTML for comparison by stripping whitespace and normalizing newlines."""
    # Replace various whitespace with single spaces
    lines = html.split('\n')
    # Strip each line and filter out empty lines
    lines = [line.strip() for line in lines if line.strip()]
    # Join with single space
    return ' '.join(lines)


def compare_responses(
    legacy_result: dict, fastapi_result: dict, description: str
) -> bool:
    """Compare the responses from both endpoints."""
    print(f"\n{'-' * 60}")
    print(f"Comparison: {description}")
    print(f"{'-' * 60}")

    # Check for errors
    if 'error' in legacy_result:
        print(f"Legacy Error: {legacy_result['error']}")
        if 'error' in fastapi_result:
            print(f"FastAPI Error: {fastapi_result['error']}")
            # Both have errors - consider this a match if status codes match
            match = legacy_result.get('status_code') == fastapi_result.get(
                'status_code'
            )
            print(f"Both have errors - Status codes match: {match}")
            return match
        return False

    if 'error' in fastapi_result:
        print(f"FastAPI Error: {fastapi_result['error']}")
        return False

    # Compare keys
    legacy_keys = set(legacy_result.keys())

    if legacy_keys != (fastapi_keys := set(fastapi_result.keys())):
        print("Key mismatch!")
        print(f"  Legacy keys: {legacy_keys}")
        print(f"  FastAPI keys: {fastapi_keys}")
        print(f"  Only in legacy: {legacy_keys - fastapi_keys}")
        print(f"  Only in FastAPI: {fastapi_keys - legacy_keys}")
        return False

    print(f"Keys match: {legacy_keys}")

    # Compare each field
    all_match = True
    for key in legacy_keys:
        legacy_val = legacy_result[key]
        fastapi_val = fastapi_result[key]

        if key == 'partials':
            # Compare partials HTML string
            legacy_normalized = normalize_html(str(legacy_val))
            fastapi_normalized = normalize_html(str(fastapi_val))

            if legacy_normalized != fastapi_normalized:
                all_match = False
                print(f"  {key}: MISMATCH")
                print(
                    f"    Legacy length: {len(legacy_val)} chars, normalized: {len(legacy_normalized)}"
                )
                print(
                    f"    FastAPI length: {len(fastapi_val)} chars, normalized: {len(fastapi_normalized)}"
                )

                # Find first difference
                for j, (lc, fc) in enumerate(
                    zip(legacy_normalized, fastapi_normalized)
                ):
                    if lc != fc:
                        start = max(0, j - 50)
                        end = min(len(legacy_normalized), j + 50)
                        print(f"    First diff at char {j}:")
                        print(f"    Legacy:  ...{legacy_normalized[start:end]}...")
                        print(f"    FastAPI: ...{fastapi_normalized[start:end]}...")
                        break
                else:
                    if len(legacy_normalized) > len(fastapi_normalized):
                        print(
                            f"    Legacy has extra: {legacy_normalized[len(fastapi_normalized):len(fastapi_normalized)+100]}"
                        )
                    else:
                        print(
                            f"    FastAPI has extra: {fastapi_normalized[len(legacy_normalized):len(legacy_normalized)+100]}"
                        )
            else:
                print(f"  {key}: MATCH (HTML content matches)")

        elif legacy_val == fastapi_val:
            print(f"  {key}: MATCH")
        else:
            print(f"  {key}: MISMATCH")
            print(f"    Legacy: {legacy_val}")
            print(f"    FastAPI: {fastapi_val}")
            all_match = False

    return all_match


@pytest.mark.integration
def test_case(data: dict, description: str) -> bool:
    """Run a test case against both endpoints and compare results."""
    legacy_result = make_request(LEGACY_URL, data, description, "Legacy")
    fastapi_result = make_request(FASTAPI_URL, data, description, "FastAPI")

    return compare_responses(legacy_result, fastapi_result, description)


def run_comparison_tests():
    """Run all comparison tests."""
    print("\n" + "=" * 60)
    print("AffiliateLinksPartial Endpoint Comparison")
    print("=" * 60)
    print(f"Legacy:  {LEGACY_URL}")
    print(f"FastAPI: {FASTAPI_URL}")
    print("\nBoth endpoints use the same interface:")
    print("  GET /partials.json?_component=AffiliateLinks&data={json}")
    print("\nMake sure both servers are running:")
    print("  - Legacy on localhost:8080")
    print("  - FastAPI on localhost:18080")

    test_cases = [
        (
            "With ISBN and title",
            {
                'args': [
                    {'isbn': ['9780141439518'], 'title': 'Pride and Prejudice'},
                    'OL53924W',
                ]
            },
        ),
        (
            "Without ISBN (title only)",
            {
                'args': [
                    {'title': 'Pride and Prejudice'},
                    'OL53924W',
                ]
            },
        ),
        (
            "With multiple ISBNs",
            {
                'args': [
                    {
                        'isbn': ['9780141439518', '9780141199078'],
                        'title': 'Pride and Prejudice',
                    },
                    'OL53924W',
                ]
            },
        ),
        (
            "Empty book info",
            {
                'args': [
                    {},
                    'OL53924W',
                ]
            },
        ),
        (
            "Empty args (should error)",
            {
                'args': [],
            },
        ),
        (
            "Single arg (should error)",
            {
                'args': [
                    {'isbn': ['9780141439518']},
                ]
            },
        ),
    ]

    results = []
    for description, data in test_cases:
        try:
            match = test_case(data, description)
            results.append((description, match))
        except (KeyError, ValueError, TypeError, json.JSONDecodeError) as e:
            print(f"\nTest '{description}' raised exception: {e}")
            import traceback

            traceback.print_exc()
            results.append((description, False))

    # Summary
    print("\n" + "=" * 60)
    print("Comparison Summary")
    print("=" * 60)

    passed = sum(1 for _, match in results if match)
    total = len(results)

    for description, match in results:
        status = "✓ MATCH" if match else "✗ DIFFER"
        print(f"{status}: {description}")

    print(f"\nTotal: {passed}/{total} tests matched")

    if passed == total:
        print("\n🎉 All endpoints return identical results!")
    else:
        print(f"\n⚠️ {total - passed} endpoint(s) returned different results")

    return results


if __name__ == '__main__':
    run_comparison_tests()
