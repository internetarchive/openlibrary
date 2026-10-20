"""Tests for the /cdn/archive.org JS proxy endpoint (FastAPI)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


@pytest.fixture
def mock_upstream():
    """Patch httpx.AsyncClient so no real network calls are made."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.content = b"/* mocked JS */"
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("openlibrary.fastapi.cdn.httpx.AsyncClient", return_value=mock_client):
        yield mock_client, mock_response


class TestIaJsCdn:
    """Tests for GET /cdn/archive.org/{filename}."""

    def test_donate_js_returns_200(self, fastapi_client, mock_upstream):
        """donate.js is proxied with correct status, headers, and body."""
        response = fastapi_client.get("/cdn/archive.org/donate.js")

        assert response.status_code == 200
        assert "text/javascript" in response.headers["content-type"]
        assert response.headers["cache-control"] == "max-age=86400"
        assert response.content == b"/* mocked JS */"

    def test_athena_js_returns_200(self, fastapi_client, mock_upstream):
        """athena.js is proxied with correct status, headers, and body."""
        response = fastapi_client.get("/cdn/archive.org/athena.js")

        assert response.status_code == 200
        assert "text/javascript" in response.headers["content-type"]
        assert response.headers["cache-control"] == "max-age=86400"
        assert response.content == b"/* mocked JS */"

    @pytest.mark.parametrize(
        "bad_name",
        ["evil.js", "../../etc/passwd", "donate.js.map", "athena.min.js", ""],
    )
    def test_various_invalid_filenames_return_404(self, fastapi_client, mock_upstream, bad_name):
        """Any filename that is not donate.js or athena.js must be rejected with 404."""
        response = fastapi_client.get(f"/cdn/archive.org/{bad_name}")
        assert response.status_code == 404

    def test_invalid_filename_does_not_call_upstream(self, fastapi_client, mock_upstream):
        """Upstream must not be called for disallowed filenames."""
        mock_client, _ = mock_upstream
        fastapi_client.get("/cdn/archive.org/evil.js")
        mock_client.get.assert_not_called()

    def test_upstream_error_returns_502(self, fastapi_client, mock_upstream):
        """If the upstream request fails with an HTTP error, a 502 Bad Gateway is returned."""
        _, mock_response = mock_upstream
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "upstream error",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )

        response = fastapi_client.get("/cdn/archive.org/donate.js")

        assert response.status_code == 502

    def test_upstream_request_error_returns_502(self, fastapi_client, mock_upstream):
        """Network failures (timeout, DNS error, connection refused) return 502."""
        mock_client, _ = mock_upstream
        mock_client.get.side_effect = httpx.RequestError("connection refused")

        response = fastapi_client.get("/cdn/archive.org/donate.js")

        assert response.status_code == 502

    def test_upstream_404_returns_502(self, fastapi_client, mock_upstream):
        """If archive.org itself returns 404, we return 502, not 404.

        The path /cdn/archive.org/donate.js is valid (passed our allowlist),
        so a 404 from upstream is an upstream problem, not a bad path.
        """
        _, mock_response = mock_upstream
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "not found",
            request=MagicMock(),
            response=MagicMock(status_code=404),
        )

        response = fastapi_client.get("/cdn/archive.org/donate.js")

        assert response.status_code == 502

    def test_upstream_called_with_correct_url(self, fastapi_client, mock_upstream):
        """The upstream URL must be https://archive.org/includes/{filename}."""
        mock_client, _ = mock_upstream
        fastapi_client.get("/cdn/archive.org/donate.js")

        mock_client.get.assert_called_once_with("https://archive.org/includes/donate.js")


# Captured before any fixture patches httpx.AsyncClient (which is module-global).
RealAsyncClient = httpx.AsyncClient

SNIPPETS = [
    {"id": 1, "annotation": "https://archive.org/details/macklife0000mack/page/3?text=x", "uri": None},
    {"id": 2, "annotation": None, "uri": "https://www-drini.archive.org/details/annakarnina00tols/page/7"},
    {"id": 3, "annotation": "https://evil.example/details/x/page/1", "uri": None},
    {"id": 4, "annotation": "https://archive.org.evil.example/details/x", "uri": None},
    {"id": 5, "annotation": "https://archive.org/search?query=x", "uri": None},
]
IMAGE_SERVER_URL = "https://ia800000.us.archive.org/BookReader/BookReaderImages.php?id=macklife0000mack&page=3"
JPEG = b"\xff\xd8\xff\xe0 mocked jpeg"


class ImageUpstream:
    """archive.org stand-in: /download/ redirects to an image server."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.redirect_to = IMAGE_SERVER_URL
        self.content_type = "image/jpeg"
        self.status_code = 200
        self.error: Exception | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.error:
            raise self.error
        if "/download/" in request.url.path:
            return httpx.Response(302, headers={"location": self.redirect_to})
        return httpx.Response(self.status_code, content=JPEG, headers={"content-type": self.content_type})


@pytest.fixture
def snippet_image_upstream(mock_upstream):
    _, mock_response = mock_upstream
    mock_response.json = MagicMock(return_value=SNIPPETS)
    upstream = ImageUpstream()
    client = RealAsyncClient(transport=httpx.MockTransport(upstream))
    with (
        patch("openlibrary.fastapi.cdn.cache.singleflight_cache", new=lambda key, compute, ttl: compute()),
        patch("openlibrary.fastapi.cdn.get_snippet_image_session", return_value=client),
    ):
        yield upstream


class TestSnippetImage:
    """Tests for GET /cdn/snippets/{annotation_id}."""

    def test_streams_image_fetched_server_side(self, fastapi_client, snippet_image_upstream):
        response = fastapi_client.get("/cdn/snippets/1", follow_redirects=False)

        assert response.status_code == 200
        assert response.content == JPEG
        assert response.headers["content-type"] == "image/jpeg"
        assert response.headers["cache-control"] == "public, max-age=3600"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert [str(r.url) for r in snippet_image_upstream.requests] == [
            "https://archive.org/download/macklife0000mack/page/3?text=x",
            IMAGE_SERVER_URL,
        ]

    def test_falls_back_to_uri(self, fastapi_client, snippet_image_upstream):
        response = fastapi_client.get("/cdn/snippets/2")

        assert response.status_code == 200
        assert str(snippet_image_upstream.requests[0].url) == "https://www-drini.archive.org/download/annakarnina00tols/page/7"

    @pytest.mark.parametrize("annotation_id", [3, 4, 5, 999])
    def test_unknown_or_unsafe_snippet_returns_404(self, fastapi_client, snippet_image_upstream, annotation_id):
        response = fastapi_client.get(f"/cdn/snippets/{annotation_id}")

        assert response.status_code == 404
        assert snippet_image_upstream.requests == []

    def test_redirect_off_archive_org_is_not_followed(self, fastapi_client, snippet_image_upstream):
        snippet_image_upstream.redirect_to = "http://169.254.169.254/latest/meta-data"

        response = fastapi_client.get("/cdn/snippets/1")

        assert response.status_code == 502
        assert len(snippet_image_upstream.requests) == 1

    @pytest.mark.parametrize("content_type", ["text/html", "image/svg+xml", ""])
    def test_non_raster_response_returns_502(self, fastapi_client, snippet_image_upstream, content_type):
        snippet_image_upstream.content_type = content_type
        assert fastapi_client.get("/cdn/snippets/1").status_code == 502

    def test_image_server_error_returns_502(self, fastapi_client, snippet_image_upstream):
        snippet_image_upstream.status_code = 401
        snippet_image_upstream.content_type = "text/html"

        response = fastapi_client.get("/cdn/snippets/1")

        assert response.status_code == 502
        assert response.json()["detail"] == "Image fetch failed: upstream returned 401 text/html"

    def test_image_network_error_returns_502(self, fastapi_client, snippet_image_upstream):
        snippet_image_upstream.error = httpx.ConnectError("connection refused")
        assert fastapi_client.get("/cdn/snippets/1").status_code == 502

    def test_non_integer_id_is_rejected(self, fastapi_client, mock_upstream, snippet_image_upstream):
        mock_client, _ = mock_upstream
        response = fastapi_client.get("/cdn/snippets/abc")

        assert response.status_code == 422
        mock_client.get.assert_not_called()

    def test_list_upstream_error_returns_502(self, fastapi_client, mock_upstream, snippet_image_upstream):
        mock_client, _ = mock_upstream
        mock_client.get.side_effect = httpx.RequestError("connection refused")

        response = fastapi_client.get("/cdn/snippets/1")

        assert response.status_code == 502
        assert response.json()["detail"] == "Snippet list fetch failed"
