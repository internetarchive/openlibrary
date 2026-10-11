"""Tests for the bounded MARC range fetch (issue #13874)."""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from openlibrary.catalog.marc.fetch import MarcFetchTimeout, fetch_range

URL = "https://archive.org/download/harvard_bibliographic_metadata/ab.bib.02.20150123.full.mrc"


class FakeResponse:
    """Minimal requests.Response double: context manager + iter_content."""

    def __init__(self, status_code=200, content=b"", exc=None):
        self.status_code = status_code
        self._content = content
        self._exc = exc

    def __enter__(self):
        if self._exc is not None:
            raise self._exc
        return self

    def __exit__(self, *args):
        return

    def raise_for_status(self):
        if self._exc is not None:
            raise self._exc
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} for {URL}")

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i : i + chunk_size]


def test_partial_206_returns_window(monkeypatch):
    body = bytes(range(256)) * 500
    seen = {}

    def fake_get(url, headers=None, timeout=None, stream=None):
        seen.update(headers=headers, stream=stream)
        return FakeResponse(206, body[:1000])

    monkeypatch.setattr(requests, "get", fake_get)
    status, data = fetch_range(URL, 0, 1000)
    assert status == 206
    assert data == body[:1000]
    assert seen["headers"] == {"Range": "bytes=0-1000"}
    assert seen["stream"] is True


def test_full_200_is_capped(monkeypatch):
    """A server ignoring Range must not make us buffer the whole file."""
    big = b"x" * (3 * 1024 * 1024)
    materialized = []

    orig_iter = FakeResponse.iter_content

    def counting_iter(self, chunk_size=1):
        for chunk in orig_iter(self, chunk_size):
            materialized.append(len(chunk))
            yield chunk

    monkeypatch.setattr(FakeResponse, "iter_content", counting_iter)
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(200, big))
    status, data = fetch_range(URL, 0, 100000)
    assert status == 200
    assert len(data) == 100000
    assert sum(materialized) <= 100000 + 16384


def test_timeout_retried_then_raised(monkeypatch):
    calls = []

    def fake_get(*args, **kwargs):
        calls.append(1)
        raise requests.ConnectTimeout("slow")

    monkeypatch.setattr(requests, "get", fake_get)
    with pytest.raises(MarcFetchTimeout):
        fetch_range(URL, 0, 100, timeout=1, retries=1)
    assert len(calls) == 2


def test_timeout_single_attempt_without_retries(monkeypatch):
    calls = []

    def fake_get(*args, **kwargs):
        calls.append(1)
        raise requests.ConnectTimeout("slow")

    monkeypatch.setattr(requests, "get", fake_get)
    with pytest.raises(MarcFetchTimeout):
        fetch_range(URL, 0, 100, timeout=1, retries=0)
    assert len(calls) == 1


def test_http_error_propagates(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(404, b"nope"))
    with pytest.raises(requests.HTTPError):
        fetch_range(URL, 0, 100)


class _IgnoreRangeHandler(BaseHTTPRequestHandler):
    """Serves 1 MiB with 200 no matter the Range (like a non-compliant origin)."""

    BODY = b"y" * (1024 * 1024)

    def do_GET(self):
        data = type(self).BODY
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def test_integration_local_server_ignoring_range():
    """Against a real socket: a 200 full body is capped, not buffered."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _IgnoreRangeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/huge.mrc"
        status, data = fetch_range(url, 0, 100000)
        assert status == 200
        assert len(data) == 100000
        assert data == b"y" * 100000
    finally:
        server.shutdown()
        thread.join(timeout=10)
