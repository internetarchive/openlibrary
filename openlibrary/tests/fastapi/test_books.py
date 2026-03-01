"""Basic tests for the FastAPI Books API endpoints."""

import json
from unittest.mock import patch

import pytest


@pytest.fixture
def client(fastapi_client):
    """Alias for backward compatibility with existing tests."""
    return fastapi_client


# -- Shared mock fixtures --


@pytest.fixture
def mock_dynlinks():
    """Mock dynlinks.dynlinks to avoid database/network calls."""
    with patch("openlibrary.fastapi.books.dynlinks.dynlinks", autospec=True) as mock:
        mock.return_value = json.dumps({"ISBN:059035342X": {"bib_key": "ISBN:059035342X", "info_url": "http://localhost/books/OL1M"}})
        yield mock


@pytest.fixture
def mock_readlinks():
    """Mock readlinks.readlinks to avoid database/network calls."""
    with patch("openlibrary.fastapi.books.readlinks.readlinks", autospec=True) as mock:
        mock.return_value = {
            "isbn:0452010586": {
                "records": {"/books/OL1M": {"data": {"title": "Test Book"}}},
                "items": [],
            }
        }
        yield mock


# -- Helpers --


def extract_jsonp(text: str, callback: str) -> dict:
    """Extract JSON data from a JSONP response string."""
    assert text.startswith(f"{callback}(")
    assert text.endswith(");")
    return json.loads(text[len(callback) + 1 : -2])


# -- /api/books.json --


class TestGetBooks:
    """Tests for the /api/books.json endpoint."""

    def test_calls_dynlinks_with_bibkeys(self, client, mock_dynlinks):
        """Verify the endpoint passes bibkeys and options to dynlinks."""
        response = client.get("/api/books.json?bibkeys=ISBN:059035342X")

        assert response.status_code == 200
        mock_dynlinks.assert_called_once()
        call_kwargs = mock_dynlinks.call_args
        assert "ISBN:059035342X" in call_kwargs[1]["bib_keys"]

    def test_passes_details_and_jscmd(self, client, mock_dynlinks):
        """Verify details and jscmd query params are forwarded to dynlinks options."""
        response = client.get("/api/books.json?bibkeys=ISBN:059035342X&details=true&jscmd=data")

        assert response.status_code == 200
        mock_dynlinks.assert_called_once()
        options = mock_dynlinks.call_args[1]["options"]
        assert options["details"] == "true"
        assert options["jscmd"] == "data"

    def test_jsonp_callback(self, client, mock_dynlinks):
        """Verify JSONP callback wrapping works for /api/books.json."""
        response = client.get("/api/books.json?bibkeys=ISBN:059035342X&callback=myCallback")

        assert response.status_code == 200
        data = extract_jsonp(response.text, "myCallback")
        assert "ISBN:059035342X" in data


# -- /api/volumes/brief/json/{req}.json  (multiget) --


class TestGetVolumesMultiget:
    """Tests for the /api/volumes/{brief_or_full}/json/{req}.json endpoint."""

    def test_calls_readlinks(self, client, mock_readlinks):
        """Verify the endpoint calls readlinks with the decoded request string."""
        response = client.get("/api/volumes/brief/json/isbn:0452010586.json")

        assert response.status_code == 200
        mock_readlinks.assert_called_once()

    def test_multiple_identifiers(self, client, mock_readlinks):
        """Verify pipe-separated identifiers are passed through."""
        response = client.get("/api/volumes/brief/json/isbn:0452010586|lccn:88037464.json")

        assert response.status_code == 200
        mock_readlinks.assert_called_once()

    def test_jsonp_callback(self, client, mock_readlinks):
        """Verify JSONP callback wrapping works for multiget endpoint."""
        response = client.get("/api/volumes/brief/json/isbn:0452010586.json?callback=jQueryCb")

        assert response.status_code == 200
        data = extract_jsonp(response.text, "jQueryCb")
        assert isinstance(data, dict)


# -- /api/volumes/brief/{idtype}/{idval}.json  (single volume) --


class TestGetVolume:
    """Tests for the /api/volumes/{brief_or_full}/{idtype}/{idval}.json endpoint."""

    def test_calls_readlinks_with_id(self, client, mock_readlinks):
        """Verify the endpoint builds 'idtype:idval' and calls readlinks."""
        response = client.get("/api/volumes/brief/isbn/0452010586.json")

        assert response.status_code == 200
        mock_readlinks.assert_called_once()
        req_arg = mock_readlinks.call_args[0][0]
        assert req_arg == "isbn:0452010586"

    def test_show_all_items_passed(self, client, mock_readlinks):
        """Verify show_all_items query param is forwarded in options."""
        response = client.get("/api/volumes/brief/isbn/0452010586.json?show_all_items=true")

        assert response.status_code == 200
        mock_readlinks.assert_called_once()
        options_arg = mock_readlinks.call_args[0][1]
        assert options_arg.get("show_all_items") is True

    def test_jsonp_callback(self, client, mock_readlinks):
        """Verify JSONP callback wrapping works for single-volume endpoint."""
        response = client.get("/api/volumes/brief/isbn/0452010586.json?callback=myFunc")

        assert response.status_code == 200
        data = extract_jsonp(response.text, "myFunc")
        assert isinstance(data, dict)
