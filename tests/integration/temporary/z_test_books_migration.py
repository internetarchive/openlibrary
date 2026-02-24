#!/usr/bin/env python3
"""Integration tests to verify Books API migration returns same results.

This script compares the old web.py endpoint with the new FastAPI endpoint
to ensure they return identical results.

These tests are marked as "integration" and are skipped by default.
Run explicitly with:
    uv run pytest -m integration tests/integration/temporary/z_test_books_migration.py -v
"""

# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "pytest",
#     "requests",
# ]
# ///


import pytest
import requests

OLD_BASE = "http://localhost:8080"
NEW_BASE = "http://localhost:18080"


def normalize_urls(data):
    """Normalize URLs by removing port numbers for comparison."""
    result = {}
    for key, value in data.items():
        if isinstance(value, dict) and 'info_url' in value:
            copy_val = value.copy()
            copy_val['info_url'] = (
                copy_val['info_url'].replace(':8080', '').replace(':18080', '')
            )
            result[key] = copy_val
        else:
            result[key] = value
    return result


@pytest.mark.integration
def test_books_api_single_isbn():
    """Test books API with single ISBN."""
    endpoint = "/api/books.json"
    params = {"bibkeys": "0452010586"}

    old_url = f"{OLD_BASE}{endpoint}"
    new_url = f"{NEW_BASE}{endpoint}"

    old_response = requests.get(old_url, params=params, timeout=5)
    new_response = requests.get(new_url, params=params, timeout=5)

    assert old_response.status_code == 200
    assert new_response.status_code == 200

    old_data = old_response.json()
    new_data = new_response.json()

    assert normalize_urls(old_data) == normalize_urls(new_data)


@pytest.mark.integration
def test_books_api_multiple_isbns():
    """Test books API with multiple ISBNs."""
    endpoint = "/api/books.json"
    params = {"bibkeys": "059035342X,0312368615"}

    old_url = f"{OLD_BASE}{endpoint}"
    new_url = f"{NEW_BASE}{endpoint}"

    old_response = requests.get(old_url, params=params, timeout=5)
    new_response = requests.get(new_url, params=params, timeout=5)

    assert old_response.status_code == 200
    assert new_response.status_code == 200

    old_data = old_response.json()
    new_data = new_response.json()

    assert normalize_urls(old_data) == normalize_urls(new_data)


@pytest.mark.integration
def test_books_api_with_details():
    """Test books API with details parameter."""
    endpoint = "/api/books.json"
    params = {"bibkeys": "059035342X", "details": "true"}

    old_url = f"{OLD_BASE}{endpoint}"
    new_url = f"{NEW_BASE}{endpoint}"

    old_response = requests.get(old_url, params=params, timeout=5)
    new_response = requests.get(new_url, params=params, timeout=5)

    assert old_response.status_code == 200
    assert new_response.status_code == 200

    old_data = old_response.json()
    new_data = new_response.json()

    assert normalize_urls(old_data) == normalize_urls(new_data)


@pytest.mark.integration
def test_books_api_empty_bibkeys():
    """Test books API with empty bibkeys."""
    endpoint = "/api/books.json"
    params = {"bibkeys": "", "details": "false"}

    old_url = f"{OLD_BASE}{endpoint}"
    new_url = f"{NEW_BASE}{endpoint}"

    old_response = requests.get(old_url, params=params, timeout=5)
    new_response = requests.get(new_url, params=params, timeout=5)

    assert old_response.status_code == 200
    assert new_response.status_code == 200

    old_data = old_response.json()
    new_data = new_response.json()

    assert normalize_urls(old_data) == normalize_urls(new_data)
