import importlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from openlibrary.api import OLError

manage_imports = importlib.import_module("scripts.manage-imports")


def http_error(status, text):
    response = requests.Response()
    response.status_code = status
    response._content = text.encode()
    return OLError(requests.HTTPError(response=response))


@pytest.fixture
def import_item():
    return SimpleNamespace(ia_id="example", batch_id=1, id=1, data='{"title": "Example"}', set_status=Mock())


@pytest.fixture
def import_client(monkeypatch):
    client = Mock()
    monkeypatch.setattr(manage_imports, "get_ol", lambda _: client)
    monkeypatch.setattr(manage_imports.time, "sleep", lambda _: None)
    return client


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (requests.Timeout("timed out"), "timeout"),
        (OSError("connection failed"), "transport-error"),
        (http_error(502, "Bad Gateway"), "server-5xx:502"),
        (http_error(429, "Too Many Requests"), "http-4xx:429"),
        (http_error(400, "Bad Request"), "http-4xx:400"),
    ],
)
def test_import_records_specific_request_failures(import_item, import_client, failure, expected):
    import_client.import_data.side_effect = failure

    manage_imports.do_import(import_item)

    import_item.set_status.assert_called_once_with("failed", error=expected)
    assert import_client.import_data.call_count == (1 if expected.startswith("http-4xx") else 5)


@pytest.mark.parametrize(
    "response",
    ["not JSON", "{broken", "[]", "null", "", '{"success": true, "edition": {}}'],
)
def test_import_records_bad_responses(import_item, import_client, response):
    import_client.import_data.return_value = response

    manage_imports.do_import(import_item)

    import_item.set_status.assert_called_once_with("failed", error="bad-response")


@pytest.mark.parametrize("response", ["upstream returned unexpected HTML", '{"success": true, "edition": {}}'])
def test_import_logs_unusable_response(import_item, import_client, caplog, response):
    import_client.import_data.return_value = response

    manage_imports.do_import(import_item)

    assert f"failed with error code: bad-response; response: {response}" in caplog.text
    import_item.set_status.assert_called_once_with("failed", error="bad-response")


def test_import_logs_unusable_http_error_response(import_item, import_client, caplog):
    import_client.import_data.side_effect = http_error(400, "unexpected HTML")

    manage_imports.do_import(import_item)

    assert "failed with error code: http-4xx:400; response: unexpected HTML" in caplog.text
    import_item.set_status.assert_called_once_with("failed", error="http-4xx:400")


def test_import_preserves_api_error_code_from_http_error(import_item, import_client):
    import_client.import_data.side_effect = http_error(400, '{"success": false, "error_code": "invalid-record"}')

    manage_imports.do_import(import_item)

    import_item.set_status.assert_called_once_with("failed", error="invalid-record")


def test_http_error_cannot_be_recorded_as_success(import_item, import_client):
    import_client.import_data.side_effect = http_error(400, '{"success": true, "edition": {"status": "created", "key": "/books/OL1M"}}')

    manage_imports.do_import(import_item)

    import_item.set_status.assert_called_once_with("failed", error="http-4xx:400")


def test_import_recovers_after_request_failure(import_item, import_client):
    import_client.import_data.side_effect = [
        requests.Timeout("timed out"),
        '{"success": true, "edition": {"status": "created", "key": "/books/OL1M"}}',
    ]

    manage_imports.do_import(import_item)

    import_item.set_status.assert_called_once_with("created", ol_key="/books/OL1M")


def test_import_succeeds_on_first_attempt(import_item, import_client):
    import_client.import_data.return_value = '{"success": true, "edition": {"status": "created", "key": "/books/OL1M"}}'

    manage_imports.do_import(import_item)

    import_client.import_data.assert_called_once_with(import_item.data)
    import_item.set_status.assert_called_once_with("created", ol_key="/books/OL1M")


def test_exhausted_retries_report_the_last_failure(import_item, import_client):
    import_client.import_data.side_effect = [
        requests.Timeout("timed out"),
        OSError("connection failed"),
        http_error(503, "Service Unavailable"),
        requests.Timeout("timed out"),
        http_error(502, "Bad Gateway"),
    ]

    manage_imports.do_import(import_item)

    import_item.set_status.assert_called_once_with("failed", error="server-5xx:502")


def test_ia_import_records_request_failure(import_item, import_client):
    import_item.data = None
    import_client.import_ocaid.side_effect = http_error(503, "Service Unavailable")

    manage_imports.do_import(import_item, require_marc=False)

    import_client.import_ocaid.assert_called_with("example", require_marc=False)
    import_item.set_status.assert_called_once_with("failed", error="server-5xx:503")


def test_import_request_rejects_zero_attempts(import_item):
    with pytest.raises(ValueError, match="at least 1"):
        manage_imports.ol_import_request(import_item, retries=0)
