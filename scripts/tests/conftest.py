from unittest.mock import MagicMock, patch

import pytest

REQUIRED_FIELDS = ["title", "source_records", "authors", "publishers", "publish_date"]


@pytest.fixture(autouse=True)
def mock_isbndb_schema_request():
    """
    Mock the network request to fetch the ISBNdb schema to avoid network dependency
    and prevent import-time errors when running tests locally without internet access.
    """
    mock_response = MagicMock()
    mock_response.json.return_value = {"required": REQUIRED_FIELDS}

    with patch("scripts.providers.isbndb.requests.get", return_value=mock_response):
        yield
