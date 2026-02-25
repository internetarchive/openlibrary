"""
Integration tests for Books API migration from web.py to FastAPI.

Tests compare responses between legacy web.py (localhost:8080) and
FastAPI (localhost:18080) endpoints to ensure they return identical results.
"""

import json
from urllib.parse import quote_plus

import pytest
import requests

LEGACY_BASE_URL = "http://localhost:8080"
FASTAPI_BASE_URL = "http://localhost:18080"


def normalize_response_for_comparison(data, port):
    """
    Normalize response data for comparison.

    URLs will differ by port, so we normalize them by replacing
    the port-specific base URL with a placeholder.
    """
    if isinstance(data, list):
        return data

    data_str = json.dumps(data)
    # Normalize URLs to account for port differences
    data_str = data_str.replace(f"http://localhost:{port}/", "http://BASE_URL/")
    return json.loads(data_str)


def compare_responses(legacy_data, fastapi_data, test_name):
    """Compare legacy and FastAPI responses after normalization."""
    # Normalize both responses
    normalized_legacy = normalize_response_for_comparison(legacy_data, 8080)
    normalized_fastapi = normalize_response_for_comparison(fastapi_data, 18080)

    # Compare structure
    assert type(normalized_legacy) is type(normalized_fastapi), (
        f"{test_name}: Response types differ - "
        f"legacy={type(normalized_legacy)}, fastapi={type(normalized_fastapi)}"
    )

    # Compare content
    assert normalized_legacy == normalized_fastapi, (
        f"{test_name}: Response content differs\n"
        f"Legacy: {json.dumps(normalized_legacy, indent=2)[:200]}\n"
        f"FastAPI: {json.dumps(normalized_fastapi, indent=2)[:200]}"
    )


class TestBooksAPI:
    """Tests for /api/books.json endpoint."""

    @pytest.mark.parametrize(
        "bibkeys",
        [
            "ISBN:059035342X",
            "ISBN:0452010586",
            "LCCN:88037464",
            "OL2058361M",
            "ISBN:059035342X,ISBN:0452010586",
        ],
    )
    def test_books_basic_lookup(self, bibkeys):
        """Test basic book lookup."""
        legacy_url = f"{LEGACY_BASE_URL}/api/books.json?bibkeys={bibkeys}"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/books.json?bibkeys={bibkeys}"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        assert legacy_resp.status_code == fastapi_resp.status_code

        legacy_data = legacy_resp.json()
        fastapi_data = fastapi_resp.json()

        compare_responses(legacy_data, fastapi_data, f"books.{bibkeys}")

    @pytest.mark.parametrize(
        "params",
        [
            "details=true",
            "jscmd=details",
            "high_priority=true",
            "details=true&jscmd=details",
        ],
    )
    def test_books_with_params(self, params):
        """Test books API with various parameters."""
        bibkeys = "ISBN:0452010586"
        legacy_url = f"{LEGACY_BASE_URL}/api/books.json?bibkeys={bibkeys}&{params}"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/books.json?bibkeys={bibkeys}&{params}"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        assert legacy_resp.status_code == fastapi_resp.status_code

        legacy_data = legacy_resp.json()
        fastapi_data = fastapi_resp.json()

        compare_responses(legacy_data, fastapi_data, f"books.params.{params}")

    def test_books_nonexistent_isbn(self):
        """Test books API with non-existent ISBN."""
        bibkeys = "ISBN:9999999999"
        legacy_url = f"{LEGACY_BASE_URL}/api/books.json?bibkeys={bibkeys}"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/books.json?bibkeys={bibkeys}"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        assert legacy_resp.status_code == fastapi_resp.status_code
        assert legacy_resp.json() == fastapi_resp.json()


class TestVolumeAPI:
    """Tests for /api/volumes/{brief_or_full}/{idtype}/{idval}.json endpoint."""

    @pytest.mark.parametrize("format_type", ["brief", "full"])
    @pytest.mark.parametrize(
        ("idtype", "idval"),
        [
            ("isbn", "0452010586"),
            ("lccn", "88037464"),
            ("olid", "OL2058361M"),
        ],
    )
    def test_volume_single_lookup(self, format_type, idtype, idval):
        """Test single volume lookup."""
        legacy_url = (
            f"{LEGACY_BASE_URL}/api/volumes/{format_type}/{idtype}/{idval}.json"
        )
        fastapi_url = (
            f"{FASTAPI_BASE_URL}/api/volumes/{format_type}/{idtype}/{idval}.json"
        )

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        assert legacy_resp.status_code == fastapi_resp.status_code

        legacy_data = legacy_resp.json()
        fastapi_data = fastapi_resp.json()

        compare_responses(
            legacy_data,
            fastapi_data,
            f"volume.single.{format_type}.{idtype}.{idval}",
        )

    def test_volume_with_params(self):
        """Test volume API with show_all_items query parameter."""
        legacy_url = f"{LEGACY_BASE_URL}/api/volumes/brief/isbn/0452010586.json?show_all_items=true"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/volumes/brief/isbn/0452010586.json?show_all_items=true"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        assert legacy_resp.status_code == fastapi_resp.status_code

        legacy_data = legacy_resp.json()
        fastapi_data = fastapi_resp.json()

        compare_responses(legacy_data, fastapi_data, "volume.params.show_all_items")

    def test_volume_nonexistent_isbn(self):
        """Test volume API with non-existent ISBN."""
        legacy_url = f"{LEGACY_BASE_URL}/api/volumes/brief/isbn/9999999999.json"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/volumes/brief/isbn/9999999999.json"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        assert legacy_resp.status_code == fastapi_resp.status_code
        assert legacy_resp.json() == fastapi_resp.json()
        # Both should return empty array for non-existent records
        assert legacy_resp.json() == []

    @pytest.mark.parametrize(
        ("idtype", "idval"),
        [
            ("oclc", "263858"),
            ("issn", "00000000"),
            ("htid", "nonexistent"),
        ],
    )
    def test_various_identifier_types(self, idtype, idval):
        """Test various identifier types."""
        legacy_url = f"{LEGACY_BASE_URL}/api/volumes/brief/{idtype}/{idval}.json"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/volumes/brief/{idtype}/{idval}.json"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        assert legacy_resp.status_code == fastapi_resp.status_code

        legacy_data = legacy_resp.json()
        fastapi_data = fastapi_resp.json()

        compare_responses(
            legacy_data,
            fastapi_data,
            f"volume.types.{idtype}.{idval}",
        )


class TestVolumeMultigetAPI:
    """Tests for /api/volumes/{brief_or_full}/json/{req}.json endpoint."""

    @pytest.mark.parametrize("format_type", ["brief", "full"])
    def test_multiget_single_identifier(self, format_type):
        """Test multiget with single identifier (no pipe separator)."""
        req = "isbn:0452010586"
        encoded_req = quote_plus(req, safe="/|:")
        legacy_url = (
            f"{LEGACY_BASE_URL}/api/volumes/{format_type}/json/{encoded_req}.json"
        )
        fastapi_url = (
            f"{FASTAPI_BASE_URL}/api/volumes/{format_type}/json/{encoded_req}.json"
        )

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        assert legacy_resp.status_code == fastapi_resp.status_code

        legacy_data = legacy_resp.json()
        fastapi_data = fastapi_resp.json()

        compare_responses(
            legacy_data,
            fastapi_data,
            f"multiget.single.{format_type}",
        )

    @pytest.mark.parametrize(
        "req",
        [
            "isbn:0452010586|lccn:88037464",
            "olid:OL2058361M|isbn:0452010586",
            "isbn:0452010586|olid:OL2058361M|lccn:88037464",
        ],
    )
    def test_multiget_multiple_identifiers(self, req):
        """Test multiget with multiple identifiers (pipe separator)."""
        encoded_req = quote_plus(req, safe="/|:")
        legacy_url = f"{LEGACY_BASE_URL}/api/volumes/brief/json/{encoded_req}.json"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/volumes/brief/json/{encoded_req}.json"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        assert legacy_resp.status_code == fastapi_resp.status_code

        legacy_data = legacy_resp.json()
        fastapi_data = fastapi_resp.json()

        compare_responses(
            legacy_data,
            fastapi_data,
            f"multiget.multiple.{req}",
        )

    def test_multiget_nonexistent_identifiers(self):
        """Test multiget with non-existent identifiers."""
        req = "isbn:9999999999|isbn:8888888888"
        encoded_req = quote_plus(req, safe="/|:")
        legacy_url = f"{LEGACY_BASE_URL}/api/volumes/brief/json/{encoded_req}.json"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/volumes/brief/json/{encoded_req}.json"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        assert legacy_resp.status_code == fastapi_resp.status_code
        assert legacy_resp.json() == fastapi_resp.json()
        # Both should return empty dict
        assert legacy_resp.json() == {}

    def test_multiget_mixed_results(self):
        """Test multiget with mix of existing and non-existent identifiers."""
        req = "isbn:0452010586|isbn:9999999999"
        encoded_req = quote_plus(req, safe="/|:")
        legacy_url = f"{LEGACY_BASE_URL}/api/volumes/brief/json/{encoded_req}.json"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/volumes/brief/json/{encoded_req}.json"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        assert legacy_resp.status_code == fastapi_resp.status_code

        legacy_data = legacy_resp.json()
        fastapi_data = fastapi_resp.json()

        compare_responses(
            legacy_data,
            fastapi_data,
            "multiget.mixed",
        )

    def test_multiget_with_semicolon(self):
        """Test multiget with semicolon separator (alternative syntax)."""
        req = "isbn:0452010586;olid:OL2058361M"
        encoded_req = quote_plus(req, safe="/|;")
        legacy_url = f"{LEGACY_BASE_URL}/api/volumes/brief/json/{encoded_req}.json"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/volumes/brief/json/{encoded_req}.json"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        assert legacy_resp.status_code == fastapi_resp.status_code

        legacy_data = legacy_resp.json()
        fastapi_data = fastapi_resp.json()

        compare_responses(
            legacy_data,
            fastapi_data,
            "multiget.semicolon",
        )

    @pytest.mark.parametrize(
        ("idtype", "idval"),
        [
            ("isbn", "0452010586"),
            ("lccn", "88037464"),
            ("olid", "OL2058361M"),
        ],
    )
    def test_multiget_single_identifier_various_types(self, idtype, idval):
        """Test multiget with various identifier types."""
        req = f"{idtype}:{idval}"
        encoded_req = quote_plus(req, safe="/|:")
        legacy_url = f"{LEGACY_BASE_URL}/api/volumes/full/json/{encoded_req}.json"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/volumes/full/json/{encoded_req}.json"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        assert legacy_resp.status_code == fastapi_resp.status_code

        legacy_data = legacy_resp.json()
        fastapi_data = fastapi_resp.json()

        compare_responses(
            legacy_data,
            fastapi_data,
            f"multiget.types.{idtype}",
        )


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_response_headers(self):
        """Test that both endpoints return same content-type."""
        url1 = f"{LEGACY_BASE_URL}/api/volumes/brief/isbn/0452010586.json"
        url2 = f"{FASTAPI_BASE_URL}/api/volumes/brief/isbn/0452010586.json"

        resp1 = requests.get(url1)
        resp2 = requests.get(url2)

        assert "application/json" in resp1.headers.get("content-type", "")
        assert "application/json" in resp2.headers.get("content-type", "")

    @pytest.mark.parametrize(
        "identifier",
        [
            "0452010586",  # ISBN without prefix
            "12345",  # Just a number
            "abc-def-ghi",  # Hyphenated
        ],
    )
    def test_invalid_identifier_formats(self, identifier):
        """Test behavior with potentially invalid identifiers."""
        url1 = f"{LEGACY_BASE_URL}/api/volumes/brief/isbn/{identifier}.json"
        url2 = f"{FASTAPI_BASE_URL}/api/volumes/brief/isbn/{identifier}.json"

        resp1 = requests.get(url1)
        resp2 = requests.get(url2)

        assert resp1.status_code == resp2.status_code

    def test_url_encoding(self):
        """Test that URLs are properly encoded and decoded."""
        # ISBN with special characters
        isbn = "0-452-01058-6"
        url1 = f"{LEGACY_BASE_URL}/api/volumes/brief/isbn/{isbn}.json"
        url2 = f"{FASTAPI_BASE_URL}/api/volumes/brief/isbn/{isbn}.json"

        resp1 = requests.get(url1)
        resp2 = requests.get(url2)

        assert resp1.status_code == resp2.status_code

    def test_empty_items_array(self):
        """Test that items array is correctly returned as empty."""
        # Use an identifier that should not have items
        url1 = f"{LEGACY_BASE_URL}/api/volumes/brief/isbn/0452010586.json"
        url2 = f"{FASTAPI_BASE_URL}/api/volumes/brief/isbn/0452010586.json"

        resp1 = requests.get(url1)
        resp2 = requests.get(url2)

        data1 = resp1.json()
        data2 = resp2.json()

        # If we get results, check items structure
        if isinstance(data1, dict) and "items" in data1:
            assert isinstance(data1["items"], list)
        if isinstance(data2, dict) and "items" in data2:
            assert isinstance(data2["items"], list)

        compare_responses(data1, data2, "edge.items_empty")
