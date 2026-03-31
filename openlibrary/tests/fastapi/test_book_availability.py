"""Tests for the /availability/v2 FastAPI endpoint (internal API)."""

from unittest.mock import patch

import pytest

MOCK_RETURN = {"OL1W": {"status": "open", "is_previewable": True}}


@pytest.fixture
def mock_get_availability():
    with patch("openlibrary.fastapi.internal.api.lending.get_availability") as mock:
        mock.return_value = MOCK_RETURN
        yield mock


class TestBookAvailabilityEndpoint:
    """Tests for GET and POST /availability/v2."""

    @pytest.mark.parametrize(
        ("id_type", "ids_str", "expected_ids"),
        [
            ("openlibrary_work", "OL1W", ["OL1W"]),
            ("openlibrary_edition", "OL1M,OL2M", ["OL1M", "OL2M"]),
            ("identifier", "isbn:9780140328721,ocaid:aliceinwonderla00carr", ["isbn:9780140328721", "ocaid:aliceinwonderla00carr"]),
        ],
    )
    def test_get_passes_ids_correctly(self, fastapi_client, mock_get_availability, id_type, ids_str, expected_ids):
        response = fastapi_client.get("/availability/v2", params={"type": id_type, "ids": ids_str})
        response.raise_for_status()
        mock_get_availability.assert_called_once_with(id_type, expected_ids)

    def test_post_passes_ids_correctly(self, fastapi_client, mock_get_availability):
        payload = {"ids": ["/books/OL1M", "/books/OL2M"]}
        response = fastapi_client.post("/availability/v2?type=openlibrary_edition", json=payload)
        response.raise_for_status()
        mock_get_availability.assert_called_once_with("openlibrary_edition", payload["ids"])
