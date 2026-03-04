"""Exhaustive tests for the FastAPI Books API endpoints."""

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
    """Mock dynlinks.dynlinks to avoid database/network calls.

    This mock returns different formats based on the options passed:
    - When format="json" or callback is present: returns plain JSON
    - Otherwise: returns JS variable wrapper
    """

    def dynlinks_mock(bib_keys, options):
        base_data = json.dumps({"ISBN:059035342X": {"bib_key": "ISBN:059035342X", "info_url": "http://localhost/books/OL1M"}})
        if options.get("format") == "json" or "callback" in options:
            return base_data
        else:
            return f"var _OLBookInfo = {base_data};"

    with patch("openlibrary.fastapi.books.dynlinks.dynlinks", autospec=True, side_effect=dynlinks_mock) as mock:
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


class TestBooksAPIBibkeysFormats:
    """Test bibkeys parameter in various formats."""

    def test_plain_isbn(self, client, mock_dynlinks):
        """Plain ISBN without prefix."""
        response = client.get("/api/books.json?bibkeys=059035342X")

        assert response.status_code == 200
        call_kwargs = mock_dynlinks.call_args
        assert "059035342X" in call_kwargs[1]["bib_keys"]

    def test_isbn_with_prefix(self, client, mock_dynlinks):
        """ISBN with ISBN: prefix."""
        response = client.get("/api/books.json?bibkeys=ISBN:059035342X")

        assert response.status_code == 200
        call_kwargs = mock_dynlinks.call_args
        assert "ISBN:059035342X" in call_kwargs[1]["bib_keys"]

    def test_lccn_with_prefix(self, client, mock_dynlinks):
        """LCCN with LCCN: prefix."""
        response = client.get("/api/books.json?bibkeys=LCCN:88037464")

        assert response.status_code == 200
        call_kwargs = mock_dynlinks.call_args
        assert "LCCN:88037464" in call_kwargs[1]["bib_keys"]

    def test_oclc_with_prefix(self, client, mock_dynlinks):
        """OCLC with OCLC: prefix."""
        response = client.get("/api/books.json?bibkeys=OCLC:18983439")

        assert response.status_code == 200
        call_kwargs = mock_dynlinks.call_args
        assert "OCLC:18983439" in call_kwargs[1]["bib_keys"]

    def test_olid(self, client, mock_dynlinks):
        """Open Library ID (OLID)."""
        response = client.get("/api/books.json?bibkeys=OL2058361M")

        assert response.status_code == 200
        call_kwargs = mock_dynlinks.call_args
        assert "OL2058361M" in call_kwargs[1]["bib_keys"]

    def test_olid_with_prefix(self, client, mock_dynlinks):
        """Open Library ID with OLID: prefix."""
        response = client.get("/api/books.json?bibkeys=OLID:OL2058361M")

        assert response.status_code == 200
        call_kwargs = mock_dynlinks.call_args
        assert "OLID:OL2058361M" in call_kwargs[1]["bib_keys"]

    def test_multiple_bibkeys_comma_separated(self, client, mock_dynlinks):
        """Multiple bibkeys comma-separated."""
        response = client.get("/api/books.json?bibkeys=059035342X,0312368615")

        assert response.status_code == 200
        call_kwargs = mock_dynlinks.call_args
        bib_keys = call_kwargs[1]["bib_keys"]
        assert "059035342X" in bib_keys
        assert "0312368615" in bib_keys

    def test_mixed_bibkey_types(self, client, mock_dynlinks):
        """Mixed bibkey types (ISBN, LCCN, OCLC)."""
        response = client.get("/api/books.json?bibkeys=ISBN:059035342X,LCCN:88037464,OCLC:123456")

        assert response.status_code == 200
        call_kwargs = mock_dynlinks.call_args
        bib_keys = call_kwargs[1]["bib_keys"]
        assert "ISBN:059035342X" in bib_keys
        assert "LCCN:88037464" in bib_keys
        assert "OCLC:123456" in bib_keys


class TestBooksAPIOutputFormat:
    """Test output format variations based on URL path and parameters."""

    def test_books_json_path_returns_plain_json(self, client, mock_dynlinks):
        """Path ending in .json returns plain JSON."""
        response = client.get("/api/books.json?bibkeys=059035342X")

        assert response.status_code == 200
        assert response.text == '{"ISBN:059035342X": {"bib_key": "ISBN:059035342X", "info_url": "http://localhost/books/OL1M"}}'
        assert response.headers["content-type"] == "application/json"

    def test_books_path_returns_js_variable(self, client, mock_dynlinks):
        """Path without .json returns JavaScript variable wrapper."""
        response = client.get("/api/books?bibkeys=059035342X")

        assert response.status_code == 200
        expected = 'var _OLBookInfo = {"ISBN:059035342X": {"bib_key": "ISBN:059035342X", "info_url": "http://localhost/books/OL1M"}};'
        assert response.text == expected
        assert response.headers["content-type"] == "application/json"

    def test_format_json_parameter(self, client, mock_dynlinks):
        """format=json forces plain JSON output."""
        response = client.get("/api/books?bibkeys=059035342X&format=json")

        assert response.status_code == 200
        assert response.text == '{"ISBN:059035342X": {"bib_key": "ISBN:059035342X", "info_url": "http://localhost/books/OL1M"}}'

    def test_format_js_parameter(self, client, mock_dynlinks):
        """format=js forces JS variable wrapper even with .json path."""
        response = client.get("/api/books.json?bibkeys=059035342X&format=js")

        assert response.status_code == 200
        expected = 'var _OLBookInfo = {"ISBN:059035342X": {"bib_key": "ISBN:059035342X", "info_url": "http://localhost/books/OL1M"}};'
        assert response.text == expected


class TestBooksAPICallback:
    """Test JSONP callback parameter."""

    def test_callback_with_json_path_returns_plain_json_wrapped(self, client, mock_dynlinks):
        """callback with .json path returns plain JSON (not JS variable) wrapped in callback."""
        response = client.get("/api/books.json?bibkeys=059035342X&callback=myCallback")

        assert response.status_code == 200
        # Should be plain JSON wrapped in callback, not JS variable wrapper
        assert response.text == 'myCallback({"ISBN:059035342X": {"bib_key": "ISBN:059035342X", "info_url": "http://localhost/books/OL1M"}});'
        # Verify callback was passed to dynlinks (dynlinks returns plain JSON when callback present)
        options = mock_dynlinks.call_args[1]["options"]
        assert options["callback"] == "myCallback"

    def test_callback_wraps_json(self, client, mock_dynlinks):
        """callback parameter wraps JSON in function call."""
        response = client.get("/api/books.json?bibkeys=059035342X&callback=myCallback")

        assert response.status_code == 200
        assert response.text == 'myCallback({"ISBN:059035342X": {"bib_key": "ISBN:059035342X", "info_url": "http://localhost/books/OL1M"}});'

    def test_callback_with_books_path(self, client, mock_dynlinks):
        """callback works with /api/books path too."""
        response = client.get("/api/books?bibkeys=059035342X&callback=myCallback")

        assert response.status_code == 200
        assert response.text == 'myCallback({"ISBN:059035342X": {"bib_key": "ISBN:059035342X", "info_url": "http://localhost/books/OL1M"}});'

    def test_callback_with_format_json(self, client, mock_dynlinks):
        """callback with format=json."""
        response = client.get("/api/books?bibkeys=059035342X&callback=cb&format=json")

        assert response.status_code == 200
        assert response.text == 'cb({"ISBN:059035342X": {"bib_key": "ISBN:059035342X", "info_url": "http://localhost/books/OL1M"}});'


class TestBooksAPIDetails:
    """Test details parameter."""

    def test_details_true_passed_to_dynlinks(self, client, mock_dynlinks):
        """details=true is passed to dynlinks."""
        response = client.get("/api/books.json?bibkeys=059035342X&details=true")

        assert response.status_code == 200
        options = mock_dynlinks.call_args[1]["options"]
        assert options["details"] == "true"


class TestBooksAPIJscmd:
    """Test jscmd parameter with all possible values."""

    def test_jscmd_data_passed_to_dynlinks(self, client, mock_dynlinks):
        """jscmd=data is passed to dynlinks."""
        response = client.get("/api/books.json?bibkeys=059035342X&jscmd=data")

        assert response.status_code == 200
        options = mock_dynlinks.call_args[1]["options"]
        assert options["jscmd"] == "data"

    def test_jscmd_details_passed_to_dynlinks(self, client, mock_dynlinks):
        """jscmd=details is passed to dynlinks."""
        response = client.get("/api/books.json?bibkeys=059035342X&jscmd=details")

        assert response.status_code == 200
        options = mock_dynlinks.call_args[1]["options"]
        assert options["jscmd"] == "details"

    def test_jscmd_viewapi_passed_to_dynlinks(self, client, mock_dynlinks):
        """jscmd=viewapi is passed to dynlinks."""
        response = client.get("/api/books.json?bibkeys=059035342X&jscmd=viewapi")

        assert response.status_code == 200
        options = mock_dynlinks.call_args[1]["options"]
        assert options["jscmd"] == "viewapi"


class TestBooksAPIHighPriority:
    """Test high_priority parameter."""

    def test_high_priority_true_passed_to_dynlinks(self, client, mock_dynlinks):
        """high_priority=true is passed to dynlinks."""
        response = client.get("/api/books.json?bibkeys=059035342X&high_priority=true")

        assert response.status_code == 200
        options = mock_dynlinks.call_args[1]["options"]
        assert options["high_priority"] is True


class TestBooksAPIText:
    """Test text parameter for Content-Type override."""

    def test_text_true_returns_text_plain(self, client, mock_dynlinks):
        """text=true sets Content-Type to text/plain."""
        response = client.get("/api/books.json?bibkeys=059035342X&text=true")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")

    def test_text_false_returns_application_json(self, client, mock_dynlinks):
        """text=false keeps Content-Type as application/json."""
        response = client.get("/api/books.json?bibkeys=059035342X&text=false")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

    def test_text_default_returns_application_json(self, client, mock_dynlinks):
        """text defaults to application/json."""
        response = client.get("/api/books.json?bibkeys=059035342X")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"


class TestBooksAPIAllParameters:
    """Test all parameters combined."""

    def test_all_params_combined(self, client, mock_dynlinks):
        """All parameters can be used together."""
        response = client.get("/api/books.json?bibkeys=059035342X,0312368615&callback=myCb&details=true&jscmd=data&high_priority=true&format=json&text=true")

        assert response.status_code == 200
        options = mock_dynlinks.call_args[1]["options"]
        assert options["callback"] == "myCb"
        assert options["details"] == "true"
        assert options["jscmd"] == "data"
        assert options["high_priority"] is True
        assert options["format"] == "json"
        assert response.headers["content-type"].startswith("text/plain")


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
