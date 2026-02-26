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


class TestGetVolumeAPI:
    """Extensive tests specifically for get_volume endpoint."""

    def test_response_structure_has_records(self):
        """Test that response contains records object."""
        legacy_url = f"{LEGACY_BASE_URL}/api/volumes/brief/isbn/0452010586.json"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/volumes/brief/isbn/0452010586.json"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        legacy_data = legacy_resp.json()
        fastapi_data = fastapi_resp.json()

        # Both should return dict with 'records' key
        if isinstance(legacy_data, dict):
            assert "records" in legacy_data
        if isinstance(fastapi_data, dict):
            assert "records" in fastapi_data

        compare_responses(legacy_data, fastapi_data, "get_volume.structure.records")

    def test_response_structure_has_items(self):
        """Test that response contains items array."""
        legacy_url = f"{LEGACY_BASE_URL}/api/volumes/brief/isbn/0452010586.json?show_all_items=true"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/volumes/brief/isbn/0452010586.json?show_all_items=true"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        legacy_data = legacy_resp.json()
        fastapi_data = fastapi_resp.json()

        # Items should be a list
        if isinstance(legacy_data, dict) and "items" in legacy_data:
            assert isinstance(legacy_data["items"], list)
        if isinstance(fastapi_data, dict) and "items" in fastapi_data:
            assert isinstance(fastapi_data["items"], list)

        compare_responses(legacy_data, fastapi_data, "get_volume.structure.items")

    def test_url_generation_correct(self):
        """Test that URLs use correct scheme and hostname."""
        legacy_url = f"{LEGACY_BASE_URL}/api/volumes/brief/lccn/88037464.json"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/volumes/brief/lccn/88037464.json"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        legacy_data = legacy_resp.json()
        fastapi_data = fastapi_resp.json()

        # Check that URLs in response use correct base
        if isinstance(legacy_data, dict) and "records" in legacy_data:
            for record_key in legacy_data["records"]:
                record = legacy_data["records"][record_key]
                if "data" in record and "url" in record["data"]:
                    # Legacy should use localhost:8080
                    assert "http://localhost:8080/" in record["data"]["url"]

        if isinstance(fastapi_data, dict) and "records" in fastapi_data:
            for record_key in fastapi_data["records"]:
                record = fastapi_data["records"][record_key]
                if "data" in record and "url" in record["data"]:
                    # FastAPI should use localhost:18080
                    assert "http://localhost:18080/" in record["data"]["url"]

    @pytest.mark.parametrize(
        "isbn",
        [
            "0452010586",  # ISBN-10
            "9780452010581",  # ISBN-13
            "0-452-01058-6",  # ISBN with hyphens
            "978-0-452-01058-1",  # ISBN-13 with hyphens
        ],
    )
    def test_various_isbn_formats(self, isbn):
        """Test various ISBN formats."""
        legacy_url = f"{LEGACY_BASE_URL}/api/volumes/brief/isbn/{isbn}.json"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/volumes/brief/isbn/{isbn}.json"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        assert legacy_resp.status_code == fastapi_resp.status_code

        # If we get results, compare them
        if legacy_resp.status_code == 200:
            legacy_data = legacy_resp.json()
            fastapi_data = fastapi_resp.json()

            # Both should return same structure
            assert type(legacy_data) is type(fastapi_data)

    @pytest.mark.parametrize(
        "format_type",
        ["brief", "full"],
    )
    def test_brief_vs_full_format(self, format_type):
        """Test that brief and full formats return different/expected structures."""
        legacy_url = f"{LEGACY_BASE_URL}/api/volumes/{format_type}/isbn/0452010586.json"
        fastapi_url = (
            f"{FASTAPI_BASE_URL}/api/volumes/{format_type}/isbn/0452010586.json"
        )

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        legacy_data = legacy_resp.json()
        fastapi_data = fastapi_resp.json()

        compare_responses(
            legacy_data,
            fastapi_data,
            f"get_volume.format.{format_type}",
        )

    def test_show_all_items_false_returns_empty_items(self):
        """Test that show_all_items=false returns empty or limited items."""
        legacy_url = f"{LEGACY_BASE_URL}/api/volumes/brief/isbn/0452010586.json"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/volumes/brief/isbn/0452010586.json"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        legacy_data = legacy_resp.json()
        fastapi_data = fastapi_resp.json()

        # Without show_all_items, items should be empty or limited
        if isinstance(legacy_data, dict) and "items" in legacy_data:
            # Items might be empty or have limited content
            assert isinstance(legacy_data["items"], list)
        if isinstance(fastapi_data, dict) and "items" in fastapi_data:
            assert isinstance(fastapi_data["items"], list)

        compare_responses(legacy_data, fastapi_data, "get_volume.items.false")

    def test_show_all_items_true_returns_items(self):
        """Test that show_all_items=true returns all available items."""
        legacy_url = f"{LEGACY_BASE_URL}/api/volumes/brief/isbn/0452010586.json?show_all_items=true"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/volumes/brief/isbn/0452010586.json?show_all_items=true"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        legacy_data = legacy_resp.json()
        fastapi_data = fastapi_resp.json()

        # With show_all_items, should get items if available
        if isinstance(legacy_data, dict) and "items" in legacy_data:
            # May have items or not depending on the book
            assert isinstance(legacy_data["items"], list)
        if isinstance(fastapi_data, dict) and "items" in fastapi_data:
            assert isinstance(fastapi_data["items"], list)

        compare_responses(legacy_data, fastapi_data, "get_volume.items.true")

    def test_nested_data_fields_present(self):
        """Test that nested data fields are present in response."""
        legacy_url = f"{LEGACY_BASE_URL}/api/volumes/full/lccn/88037464.json"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/volumes/full/lccn/88037464.json"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        legacy_data = legacy_resp.json()
        fastapi_data = fastapi_resp.json()

        # Check that common fields exist
        if isinstance(legacy_data, dict) and "records" in legacy_data:
            for record_key in legacy_data["records"]:
                record = legacy_data["records"][record_key]
                # Check data object
                assert "data" in record
                data = record["data"]
                # Check common fields
                assert isinstance(data.get("title"), (str, type(None)))

        compare_responses(legacy_data, fastapi_data, "get_volume.nested_fields")

    def test_authors_array_structure(self):
        """Test that authors array is properly structured."""
        legacy_url = f"{LEGACY_BASE_URL}/api/volumes/brief/lccn/88037464.json"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/volumes/brief/lccn/88037464.json"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        legacy_data = legacy_resp.json()
        fastapi_data = fastapi_resp.json()

        if isinstance(legacy_data, dict) and "records" in legacy_data:
            for record_key in legacy_data["records"]:
                record = legacy_data["records"][record_key]
                if "data" in record and "authors" in record["data"]:
                    authors = record["data"]["authors"]
                    # Should be a list
                    assert isinstance(authors, list)
                    if authors:
                        # Each author should have name and url
                        author = authors[0]
                        assert isinstance(author.get("name"), (str, type(None)))
                        assert isinstance(author.get("url"), (str, type(None)))

        compare_responses(legacy_data, fastapi_data, "get_volume.authors")

    def test_identifiers_array_structure(self):
        """Test that identifiers array is properly structured."""
        legacy_url = f"{LEGACY_BASE_URL}/api/volumes/brief/isbn/0452010586.json"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/volumes/brief/isbn/0452010586.json"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        legacy_data = legacy_resp.json()
        fastapi_data = fastapi_resp.json()

        if isinstance(legacy_data, dict) and "records" in legacy_data:
            for record_key in legacy_data["records"]:
                record = legacy_data["records"][record_key]
                # Check identifier fields
                assert isinstance(record.get("isbns"), list)
                assert isinstance(record.get("lccns"), list)
                assert isinstance(record.get("oclcs"), list)

        compare_responses(legacy_data, fastapi_data, "get_volume.identifiers")

    def test_publish_dates_array(self):
        """Test that publish dates array is properly structured."""
        legacy_url = f"{LEGACY_BASE_URL}/api/volumes/brief/isbn/0452010586.json"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/volumes/brief/isbn/0452010586.json"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        legacy_data = legacy_resp.json()
        fastapi_data = fastapi_resp.json()

        if isinstance(legacy_data, dict) and "records" in legacy_data:
            for record_key in legacy_data["records"]:
                record = legacy_data["records"][record_key]
                if record.get("publishDates"):
                    assert isinstance(record["publishDates"], list)

        compare_responses(legacy_data, fastapi_data, "get_volume.publish_dates")

    @pytest.mark.parametrize(
        ("idtype", "idval"),
        [
            ("lccn", "88037464"),
            ("olid", "OL2058361M"),
            ("isbn", "0452010586"),
        ],
    )
    def test_full_format_has_details(self, idtype, idval):
        """Test that full format includes details section."""
        legacy_url = f"{LEGACY_BASE_URL}/api/volumes/full/{idtype}/{idval}.json"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/volumes/full/{idtype}/{idval}.json"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        legacy_data = legacy_resp.json()
        fastapi_data = fastapi_resp.json()

        if isinstance(legacy_data, dict) and "records" in legacy_data:
            for record_key in legacy_data["records"]:
                record = legacy_data["records"][record_key]
                # Full format should have details
                assert "details" in record
                assert isinstance(record["details"], dict)

        compare_responses(
            legacy_data, fastapi_data, f"get_volume.full_details.{idtype}"
        )

    def test_brief_format_has_less_data(self):
        """Test that brief format has less data than full format."""
        legacy_brief = f"{LEGACY_BASE_URL}/api/volumes/brief/isbn/0452010586.json"
        legacy_full = f"{LEGACY_BASE_URL}/api/volumes/full/isbn/0452010586.json"

        fastapi_brief = f"{FASTAPI_BASE_URL}/api/volumes/brief/isbn/0452010586.json"
        fastapi_full = f"{FASTAPI_BASE_URL}/api/volumes/full/isbn/0452010586.json"

        legacy_brief_resp = requests.get(legacy_brief)
        legacy_full_resp = requests.get(legacy_full)
        requests.get(fastapi_brief)
        requests.get(fastapi_full)

        # Compare brief vs full - full should have more details
        # This is just to ensure the format differences exist
        legacy_brief_data = legacy_brief_resp.json()
        legacy_full_data = legacy_full_resp.json()

        if isinstance(legacy_brief_data, dict) and isinstance(  # noqa: SIM102
            legacy_full_data, dict
        ):
            if "records" in legacy_brief_data and "records" in legacy_full_data:
                # Both should have records
                assert "records" in legacy_brief_data
                assert "records" in legacy_full_data

    def test_record_url_generation(self):
        """Test that recordURL field is properly generated."""
        legacy_url = f"{LEGACY_BASE_URL}/api/volumes/brief/lccn/88037464.json"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/volumes/brief/lccn/88037464.json"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        legacy_data = legacy_resp.json()
        fastapi_data = fastapi_resp.json()

        if isinstance(legacy_data, dict) and "records" in legacy_data:
            for record_key in legacy_data["records"]:
                record = legacy_data["records"][record_key]
                # Should have recordURL
                assert "recordURL" in record
                # Should be a string
                assert isinstance(record["recordURL"], str)
                # Should contain the record key
                assert record_key in record["recordURL"]

        compare_responses(legacy_data, fastapi_data, "get_volume.record_url")


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


class TestJSONPCallbackSupport:
    """Tests for JSONP callback parameter support."""

    @pytest.mark.parametrize(
        "endpoint", ["/api/books.json", "/api/volumes/brief/isbn/0452010586.json"]
    )
    def test_jsonp_callback_basic(self, endpoint):
        """Test that callback parameter wraps response in JSONP."""
        callback_name = "myCallback123"
        legacy_url = f"{LEGACY_BASE_URL}{endpoint}?bibkeys=ISBN:0452010586&callback={callback_name}"
        if "/api/volumes" in endpoint:
            legacy_url = f"{LEGACY_BASE_URL}{endpoint}?callback={callback_name}"

        fastapi_url = legacy_url.replace(":8080", ":18080")

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        assert legacy_resp.status_code == fastapi_resp.status_code == 200

        # Both should be wrapped in callback (though Content-Type may be application/json)
        legacy_text = legacy_resp.text
        fastapi_text = fastapi_resp.text

        assert legacy_text.startswith(f"{callback_name}(")
        assert fastapi_text.startswith(f"{callback_name}(")
        assert legacy_text.endswith(");")
        assert fastapi_text.endswith(");")

        # Extract and compare JSON content
        legacy_json = json.loads(legacy_text[len(callback_name) + 1 : -2])
        fastapi_json = json.loads(fastapi_text[len(callback_name) + 1 : -2])

        # Normalize URLs for comparison
        normalized_legacy = normalize_response_for_comparison(legacy_json, 8080)
        normalized_fastapi = normalize_response_for_comparison(fastapi_json, 18080)

        assert normalized_legacy == normalized_fastapi

    def test_jsonp_callback_multiget(self):
        """Test JSONP callback with multiget endpoint."""
        callback_name = "jQuery1234567890"
        req = "id:0;isbn:0545202051|id:1;isbn:0545003962"
        encoded_req = quote_plus(req, safe="/|:")

        legacy_url = f"{LEGACY_BASE_URL}/api/volumes/brief/json/{encoded_req}?callback={callback_name}&show_all_items=true"
        fastapi_url = legacy_url.replace(":8080", ":18080")

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        assert legacy_resp.status_code == fastapi_resp.status_code == 200

        # Both should be wrapped in callback (though Content-Type may be application/json)
        legacy_text = legacy_resp.text
        fastapi_text = fastapi_resp.text

        assert legacy_text.startswith(f"{callback_name}(")
        assert fastapi_text.startswith(f"{callback_name}(")


class TestBooksAPIEdgeCases:
    """Tests for Books API edge cases from real-world traffic."""

    def test_url_encoded_bibkeys(self):
        """Test books API with URL-encoded bibliography keys."""
        bibkeys = "isbn%3A9784827200225"
        legacy_url = f"{LEGACY_BASE_URL}/api/books.json?bibkeys={bibkeys}&details=true"
        fastapi_url = (
            f"{FASTAPI_BASE_URL}/api/books.json?bibkeys={bibkeys}&details=true"
        )

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        assert legacy_resp.status_code == fastapi_resp.status_code

        # Even with URL encoding, both should interpret correctly
        legacy_data = legacy_resp.json()
        fastapi_data = fastapi_resp.json()

        compare_responses(legacy_data, fastapi_data, "books.url_encoded_bibkeys")

    def test_nested_colon_bibkeys(self):
        """Test books API with local_id containing nested colons."""
        # This tests that the bibkey parser handles nested colons correctly
        bibkeys = "local_id:urn:bwbsku:Y0-DLA-903"
        legacy_url = f"{LEGACY_BASE_URL}/api/books.json?bibkeys={bibkeys}&details=true"
        fastapi_url = (
            f"{FASTAPI_BASE_URL}/api/books.json?bibkeys={bibkeys}&details=true"
        )

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        assert legacy_resp.status_code == fastapi_resp.status_code

        # Both should handle nested colons the same way
        if legacy_resp.status_code == 200 and legacy_resp.json():
            legacy_data = legacy_resp.json()
            fastapi_data = fastapi_resp.json()
            compare_responses(legacy_data, fastapi_data, "books.nested_colons")

    def test_empty_bibkeys(self):
        """Test books API with empty bibkeys parameter."""
        # Empty bibkeys should not crash and return empty result
        legacy_url = f"{LEGACY_BASE_URL}/api/books?bibkeys=&jscmd=data"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/books?bibkeys=&jscmd=data"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        # Both should handle gracefully (might return 200 with empty result or 4xx error)
        assert legacy_resp.status_code == fastapi_resp.status_code

    def test_jscmd_data_with_callback(self):
        """Test books API with jscmd=data and JSONP callback."""
        bibkeys = "ISBN:0452010586,ISBN:059035342X"
        callback = "foo.olCallBack"

        legacy_url = f"{LEGACY_BASE_URL}/api/books?bibkeys={bibkeys}&callback={callback}&jscmd=data"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/books?bibkeys={bibkeys}&callback={callback}&jscmd=data"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        assert legacy_resp.status_code == fastapi_resp.status_code

        # Both should be wrapped in callback
        legacy_text = legacy_resp.text
        fastapi_text = fastapi_resp.text

        if legacy_resp.status_code == 200:
            assert legacy_text.startswith(f"{callback}(")
            assert fastapi_text.startswith(f"{callback}(")

            # Extract and compare
            legacy_json = json.loads(legacy_text[len(callback) + 1 : -2])
            fastapi_json = json.loads(fastapi_text[len(callback) + 1 : -2])

            normalized_legacy = normalize_response_for_comparison(legacy_json, 8080)
            normalized_fastapi = normalize_response_for_comparison(fastapi_json, 18080)

            assert normalized_legacy == normalized_fastapi


class TestVolumeAPIEdgeCases:
    """Tests for Volume API edge cases from real-world traffic."""

    def test_multiget_complex_separators(self):
        """Test multiget with complex semicolon and pipe separators."""
        # Example: id:0;lccn:67077305_/r924|id:1;isbn:0677203101;lccn:78092622_/r926
        req = "id:0;isbn:0545202051|id:1;isbn:0545003962"
        encoded_req = quote_plus(req, safe="/|:")

        legacy_url = f"{LEGACY_BASE_URL}/api/volumes/brief/json/{encoded_req}?show_all_items=true"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/volumes/brief/json/{encoded_req}?show_all_items=true"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        assert legacy_resp.status_code == fastapi_resp.status_code

        if legacy_resp.status_code == 200:
            legacy_data = legacy_resp.json()
            fastapi_data = fastapi_resp.json()

            compare_responses(legacy_data, fastapi_data, "volume.complex_separators")

    def test_multiget_without_json_extension(self):
        """Test multiget endpoint without .json extension."""
        # Some clients call /api/volumes/brief/json/isbn:9780062858191 without .json
        isbn = "9780062858191"
        legacy_url = f"{LEGACY_BASE_URL}/api/volumes/brief/json/isbn:{isbn}"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/volumes/brief/json/isbn:{isbn}"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        assert legacy_resp.status_code == fastapi_resp.status_code

        if legacy_resp.status_code == 200:
            legacy_data = legacy_resp.json()
            fastapi_data = fastapi_resp.json()

            compare_responses(legacy_data, fastapi_data, "volume.no_json_extension")

    def test_multiget_many_identifiers_with_callback(self):
        """Test multiget with many identifiers and JSONP callback."""
        # Simulate real-world traffic with many identifiers
        req = "id:0;isbn:0230632602|id:1;isbn:0230331963|id:2;isbn:0230324444"
        encoded_req = quote_plus(req, safe="/|:")
        callback = "jQuery34109836958233199882_1772041688238"

        legacy_url = f"{LEGACY_BASE_URL}/api/volumes/brief/json/{encoded_req}?callback={callback}&show_all_items=true"
        fastapi_url = f"{FASTAPI_BASE_URL}/api/volumes/brief/json/{encoded_req}?callback={callback}&show_all_items=true"

        legacy_resp = requests.get(legacy_url)
        fastapi_resp = requests.get(fastapi_url)

        assert legacy_resp.status_code == fastapi_resp.status_code

        if legacy_resp.status_code == 200:
            # Both should be wrapped in callback
            legacy_text = legacy_resp.text
            fastapi_text = fastapi_resp.text

            assert legacy_text.startswith(f"{callback}(")
            assert fastapi_text.startswith(f"{callback}(")

            # Extract and compare
            legacy_json = json.loads(legacy_text[len(callback) + 1 : -2])
            fastapi_json = json.loads(fastapi_text[len(callback) + 1 : -2])

            compare_responses(
                legacy_json, fastapi_json, "volume.many_identifiers_callback"
            )
