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
