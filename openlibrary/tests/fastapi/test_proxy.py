"""Tests for the FastAPI → web.py fallback proxy (openlibrary/fastapi/proxy.py)."""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from openlibrary.fastapi.proxy import _rebase_redirect, proxy_to_webpy


def _make_app():
    app = FastAPI()

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
    async def fallback(request: Request) -> Response:
        return await proxy_to_webpy(request)

    return app


class FakeResponse:
    """Stand-in for an httpx response with a streamed body."""

    def __init__(self, chunks, status_code=200, headers=None, events=None):
        self.chunks = chunks
        self.status_code = status_code
        self.headers = headers or {}
        self.events = events if events is not None else []

    async def aiter_bytes(self):
        for chunk in self.chunks:
            self.events.append(f"chunk:{chunk!r}")
            yield chunk
        self.events.append("body-done")

    async def aclose(self):
        self.events.append("resp-closed")


class FakeClient:
    """Stand-in for httpx.AsyncClient that records how the request was sent."""

    def __init__(self, response):
        self.response = response
        self.build_kwargs = {}
        self.stream = None
        self.closed = False

    def build_request(self, **kwargs):
        self.build_kwargs = kwargs
        return MagicMock()

    async def send(self, request, *, stream=False):
        self.stream = stream
        return self.response

    async def aclose(self):
        self.closed = True


@contextmanager
def _proxy_client(fake_client, raise_server_exceptions=True):
    """TestClient for the proxy handler with the shared client patched out.

    The patch must stay active for the whole request, so this is a context
    manager rather than a plain factory.
    """
    with (
        patch("openlibrary.fastapi.proxy.get_async_session", return_value=fake_client),
        TestClient(_make_app(), raise_server_exceptions=raise_server_exceptions) as client,
    ):
        yield client


def test_request_body_is_streamed_not_buffered():
    """The request body must be passed as an async stream, and the upstream read with stream=True."""
    fake_client = FakeClient(FakeResponse([b"ok"]))

    with _proxy_client(fake_client) as client:
        response = client.post("/books", content=b"some payload")

    assert response.status_code == 200
    assert response.content == b"ok"
    # Not a pre-read body: an async iterable (request.stream()), not bytes.
    assert hasattr(fake_client.build_kwargs["content"], "__aiter__")
    assert fake_client.stream is True


def test_response_body_is_streamed_and_closed_afterwards():
    """Chunks are yielded in order, and the upstream response is closed only after the body is consumed."""
    events = []
    chunks = [b"chunk-1,", b"chunk-2,", b"chunk-3"]
    fake_client = FakeClient(FakeResponse(chunks, events=events))

    with _proxy_client(fake_client) as client:
        response = client.get("/books/OL1M")

    assert response.content == b"chunk-1,chunk-2,chunk-3"
    # The generator's finally must run after the last chunk, never before.
    assert events == [f"chunk:{c!r}" for c in chunks] + ["body-done", "resp-closed"]
    # The shared per-event-loop client must survive the request.
    assert fake_client.closed is False


def test_hop_by_hop_headers_are_filtered():
    """content-length/encoding, transfer-encoding and x-served-by must not leak through."""
    upstream_headers = {
        "content-length": "7",
        "content-encoding": "gzip",
        "transfer-encoding": "chunked",
        "x-served-by": "web.py",
        "content-type": "text/plain",
    }
    fake_client = FakeClient(FakeResponse([b"abcdefg"], headers=upstream_headers))

    with _proxy_client(fake_client) as client:
        response = client.get("/")

    assert response.headers["content-type"] == "text/plain"
    assert "content-length" not in response.headers
    assert "content-encoding" not in response.headers
    assert "transfer-encoding" not in response.headers
    assert "location" not in response.headers  # no empty Location header when upstream sends none
    assert response.headers["x-served-by"] == "web.py"
    assert response.headers["x-proxied-by"] == "FastAPI"


@pytest.mark.parametrize("status_code", [201, 301, 302, 303, 307, 308])
def test_location_is_rewritten_to_client_host(status_code):
    """Any Location pointing at the internal web.py URL must point back at the public host."""
    fake_client = FakeClient(
        FakeResponse(
            [b""],
            status_code=status_code,
            headers={"location": "http://web:8080/books/OL1M"},
        )
    )

    with _proxy_client(fake_client) as client:
        response = client.get("/books/OL1M", follow_redirects=False)

    assert response.status_code == status_code
    assert response.headers["location"] == "http://testserver/books/OL1M"


@pytest.mark.parametrize(
    ("upstream_location", "request_headers", "expected_location"),
    [
        pytest.param(
            "https://web:8080/books/OL1M",
            {},
            "http://testserver/books/OL1M",
            id="https-upstream-no-forwarded-headers",
        ),
        pytest.param(
            "https://web:8080/books/OL1M",
            {"X-Scheme": "https"},
            "https://testserver/books/OL1M",
            id="x-scheme-https-rewrites-to-https",
        ),
        pytest.param(
            "http://web:8080/books/OL1M",
            {"X-Forwarded-Proto": "https"},
            "https://testserver/books/OL1M",
            id="x-forwarded-proto-https-rewrites-to-https",
        ),
        pytest.param(
            "https://archive.org/services/img/OL1M",
            {"X-Scheme": "https"},
            "https://archive.org/services/img/OL1M",
            id="non-webpy-absolute-location-untouched",
        ),
        pytest.param(
            "HTTP://WEB:8080/books/OL1M",
            {},
            "http://testserver/books/OL1M",
            id="case-insensitive-upstream-origin-rebased",
        ),
        pytest.param(
            "/account/login?redirect=http://web:8080/works/OL1W",
            {},
            "/account/login?redirect=http://web:8080/works/OL1W",
            id="webpy-url-in-query-param-untouched",
        ),
    ],
)
def test_location_scheme_matches_client_facing_scheme(upstream_location, request_headers, expected_location):
    """The rewritten Location must use the client-facing scheme (https on testing, http locally)."""
    fake_client = FakeClient(FakeResponse([b""], status_code=302, headers={"location": upstream_location}))

    with _proxy_client(fake_client) as client:
        response = client.get("/books/OL1M", headers=request_headers, follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == expected_location


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        pytest.param("http://web:8080/works/OL1W", "https://ol.org/works/OL1W", id="http-rebased"),
        pytest.param("https://web:8080/works/OL1W", "https://ol.org/works/OL1W", id="https-rebased"),
        pytest.param("HTTP://WEB:8080/works/OL1W", "https://ol.org/works/OL1W", id="case-insensitive-rebased"),
        pytest.param("http://web:8080?a=1#frag", "https://ol.org?a=1#frag", id="query-and-fragment-preserved"),
        pytest.param("/login?redirect=http://web:8080/works/OL1W", "/login?redirect=http://web:8080/works/OL1W", id="query-param-substring-untouched"),
        pytest.param("/static/http://web:8080/logo.png", "/static/http://web:8080/logo.png", id="path-substring-untouched"),
        pytest.param("http://web:8080.evil.com/works/OL1W", "http://web:8080.evil.com/works/OL1W", id="lookalike-host-untouched"),
        pytest.param("http://user@web:8080/works/OL1W", "http://user@web:8080/works/OL1W", id="userinfo-netloc-untouched"),
        pytest.param("https://archive.org/works/OL1W", "https://archive.org/works/OL1W", id="other-host-untouched"),
        pytest.param("/works/OL1W", "/works/OL1W", id="relative-untouched"),
    ],
)
def test_rebase_redirect(location, expected):
    """Only Locations whose authority is exactly web.py's may be rebased; everything else passes through."""
    assert _rebase_redirect(location, "https", "ol.org") == expected


def test_upstream_failure_propagates():
    """If the upstream request fails, the error propagates and the shared client survives."""

    class FailingClient(FakeClient):
        async def send(self, request, *, stream=False):
            raise ConnectionError("upstream down")

    fake_client = FailingClient(FakeResponse([b""]))

    with _proxy_client(fake_client, raise_server_exceptions=False) as client:
        response = client.get("/")

    assert response.status_code == 500
    assert fake_client.closed is False
