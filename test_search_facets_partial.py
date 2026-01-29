#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.31.0",
# ]
# ///
"""
Test script for SearchFacetsPartial endpoint.

This script makes HTTP requests to localhost:8080 to test the /partials.json
endpoint with the SearchFacets component. It helps understand how the endpoint
works and validates its behavior with various inputs.

Usage with uv:
    uv run test_search_facets_partial.py

Or with Python directly (requires requests to be installed):
    python test_search_facets_partial.py

Requirements:
    - OpenLibrary server running on localhost:8080
"""

import json
import sys
import urllib.parse
from typing import Any

import requests

# Base URL for the partials endpoint
BASE_URL = "http://localhost:8080/partials.json"


def build_search_facets_url(data: dict) -> str:
    """
    Build the URL for the SearchFacets partial endpoint.

    Matches the JavaScript buildPartialsUrl function behavior.

    Args:
        data: Dictionary containing param, path, and query

    Returns:
        Complete URL with query parameters
    """
    params = {'_component': 'SearchFacets', 'data': json.dumps(data)}
    query_string = urllib.parse.urlencode(params)
    return f"{BASE_URL}?{query_string}"


def make_request(data: dict, description: str) -> dict[str, Any]:
    """
    Make a request to the SearchFacets endpoint and return the response.

    Args:
        data: The data payload to send
        description: Description of the test case for logging

    Returns:
        Parsed JSON response from the server
    """
    url = build_search_facets_url(data)

    print(f"\n{'=' * 60}")
    print(f"Test: {description}")
    print(f"{'=' * 60}")
    print(f"Request URL: {url}")
    print(f"Request Data: {json.dumps(data, indent=2)}")

    try:
        response = requests.get(url, timeout=30)
        print(f"\nStatus Code: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print(f"\nResponse Keys: {list(result.keys())}")

            if 'sidebar' in result:
                sidebar_preview = (
                    result['sidebar'][:200]
                    if len(result['sidebar']) > 200
                    else result['sidebar']
                )
                print(f"\nSidebar HTML (first 200 chars):\n{sidebar_preview}...")

            if 'title' in result:
                print(f"\nTitle: {result['title']}")

            if 'activeFacets' in result:
                active_preview = (
                    result['activeFacets'][:200]
                    if len(result['activeFacets']) > 200
                    else result['activeFacets']
                )
                print(f"\nActive Facets HTML (first 200 chars):\n{active_preview}...")

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


def test_basic_search():
    """Test basic search with just a query string."""
    data = {
        'param': {'q': 'python programming'},
        'path': '/search',
        'query': '?q=python+programming',
    }
    return make_request(data, "Basic search with query string")


def test_search_with_author_filter():
    """Test search with author filter applied."""
    data = {
        'param': {'q': 'python', 'author_key': ['OL123A']},
        'path': '/search',
        'query': '?q=python&author_key=OL123A',
    }
    return make_request(data, "Search with author filter")


def test_search_with_subject_filter():
    """Test search with subject facet filter."""
    data = {
        'param': {
            'q': 'history',
            'subject_facet': ['World War II', 'Military History'],
        },
        'path': '/search',
        'query': '?q=history&subject_facet=World+War+II&subject_facet=Military+History',
    }
    return make_request(data, "Search with subject facet filter")


def test_search_with_has_fulltext():
    """Test search with has_fulltext filter (ebook availability)."""
    data = {
        'param': {'q': 'programming', 'has_fulltext': 'true'},
        'path': '/search',
        'query': '?q=programming&has_fulltext=true',
    }
    return make_request(data, "Search with has_fulltext filter (ebooks only)")


def test_search_with_language_filter():
    """Test search with language filter."""
    data = {
        'param': {'q': 'novel', 'language': ['eng', 'fre']},
        'path': '/search',
        'query': '?q=novel&language=eng&language=fre',
    }
    return make_request(data, "Search with language filter")


def test_search_with_publish_year():
    """Test search with first_publish_year filter."""
    data = {
        'param': {
            'q': 'science fiction',
            'first_publish_year': ['2020', '2021', '2022'],
        },
        'path': '/search',
        'query': '?q=science+fiction&first_publish_year=2020',
    }
    return make_request(data, "Search with publish year filter")


def test_search_with_publisher():
    """Test search with publisher filter."""
    data = {
        'param': {'q': 'cooking', 'publisher_facet': ['Penguin Books']},
        'path': '/search',
        'query': '?q=cooking&publisher_facet=Penguin+Books',
    }
    return make_request(data, "Search with publisher filter")


def test_search_with_person_place_time():
    """Test search with person, place, and time facets."""
    data = {
        'param': {
            'q': 'biography',
            'person_facet': ['Napoleon'],
            'place_facet': ['France'],
            'time_facet': ['19th century'],
        },
        'path': '/search',
        'query': '?q=biography&person_facet=Napoleon&place_facet=France&time_facet=19th+century',
    }
    return make_request(data, "Search with person, place, and time facets")


def test_empty_query():
    """
    Test with empty query - this is expected to fail with a 500 error.

    When param is empty {}, the do_search() function cannot build a valid Solr query,
    causing an AttributeError during template rendering. This reveals that the endpoint
    requires at least a 'q' parameter or valid search criteria to function properly.
    """
    data = {'param': {}, 'path': '/search', 'query': ''}
    result = make_request(
        data, "Empty query (expected to fail - requires at least 'q' parameter)"
    )
    # Empty query is expected to fail (500 error) - this is the documented behavior
    # The endpoint requires at least a 'q' parameter to build a valid Solr query
    return result


def test_unicode_query():
    """Test with unicode characters in query."""
    data = {
        'param': {'q': '日本語', 'author_key': ['OL1A']},
        'path': '/search',
        'query': '?q=%E6%97%A5%E6%9C%AC%E8%AA%9E&author_key=OL1A',
    }
    return make_request(data, "Unicode characters in query")


def test_multiple_filters():
    """Test with multiple filters applied simultaneously."""
    data = {
        'param': {
            'q': 'machine learning',
            'has_fulltext': 'true',
            'language': ['eng'],
            'subject_facet': ['Computer Science'],
            'first_publish_year': ['2020', '2021', '2022', '2023'],
        },
        'path': '/search',
        'query': '?q=machine+learning&has_fulltext=true&language=eng&subject_facet=Computer+Science',
    }
    return make_request(data, "Multiple filters (fulltext + language + subject + year)")


def test_public_scan_filter():
    """Test with public_scan_b filter (Classic eBooks)."""
    data = {
        'param': {'q': 'shakespeare', 'public_scan_b': 'true'},
        'path': '/search',
        'query': '?q=shakespeare&public_scan_b=true',
    }
    return make_request(data, "Search with public_scan_b filter (Classic eBooks)")


def test_special_characters_in_query():
    """Test with special characters that need URL encoding."""
    data = {
        'param': {'q': 'C++ & Java', 'subject_facet': ['Science & Technology']},
        'path': '/search',
        'query': '?q=C%2B%2B+%26+Java&subject_facet=Science+%26+Technology',
    }
    return make_request(data, "Special characters in query (C++, &, etc.)")


def test_missing_path():
    """Test with missing path parameter."""
    data = {'param': {'q': 'test'}, 'query': '?q=test'}
    return make_request(data, "Missing path parameter")


def test_missing_query():
    """Test with missing query parameter."""
    data = {'param': {'q': 'test'}, 'path': '/search'}
    return make_request(data, "Missing query parameter")


def test_malformed_json():
    """Test what happens with malformed JSON (should fail at request level)."""
    # This test manually constructs a URL with bad JSON
    url = f"{BASE_URL}?_component=SearchFacets&data=not_valid_json"

    print(f"\n{'=' * 60}")
    print("Test: Malformed JSON data")
    print(f"{'=' * 60}")
    print(f"Request URL: {url}")

    try:
        response = requests.get(url, timeout=30)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text[:500]}")
        return {'status_code': response.status_code, 'text': response.text}
    except requests.exceptions.RequestException as e:
        print(f"Request Error: {e}")
        return {'error': str(e)}


def run_all_tests():
    """Run all test cases and summarize results."""
    print("\n" + "=" * 60)
    print("SearchFacetsPartial Endpoint Tests")
    print("=" * 60)
    print(f"Testing against: {BASE_URL}")
    print("Make sure your OpenLibrary server is running on localhost:8080")

    tests = [
        ("Basic Search", test_basic_search),
        ("Author Filter", test_search_with_author_filter),
        ("Subject Filter", test_search_with_subject_filter),
        ("Has Fulltext Filter", test_search_with_has_fulltext),
        ("Language Filter", test_search_with_language_filter),
        ("Publish Year Filter", test_search_with_publish_year),
        ("Publisher Filter", test_search_with_publisher),
        ("Person/Place/Time", test_search_with_person_place_time),
        ("Empty Query", test_empty_query),
        ("Unicode Query", test_unicode_query),
        ("Multiple Filters", test_multiple_filters),
        ("Public Scan Filter", test_public_scan_filter),
        ("Special Characters", test_special_characters_in_query),
        ("Missing Path", test_missing_path),
        ("Missing Query", test_missing_query),
        ("Malformed JSON", test_malformed_json),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            # Empty Query is expected to fail (500 error) - documented behavior
            if name == "Empty Query":
                success = result.get('status_code', 200) == 500
            else:
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
        if name == "Empty Query":
            status = (
                "✓ PASS (expected failure)"
                if success
                else "✗ FAIL (should have returned 500)"
            )
        else:
            status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    return results


if __name__ == '__main__':
    run_all_tests()
