"""Tests for the iannotate snippets client (openlibrary.core.snippets)."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import httpx

from openlibrary.core import snippets


def _run_delete(snippet_id, handler, url="http://iannotate.test"):
    """Run delete_snippet with httpx wired to a MockTransport running `handler`,
    and the service URL pinned, so nothing touches the network."""
    transport = httpx.MockTransport(handler)
    with (
        patch.object(snippets, "_iannotate_url", lambda: url),
        patch.object(
            snippets,
            "_async_client",
            lambda: httpx.AsyncClient(transport=transport),
        ),
    ):
        return asyncio.run(snippets.delete_snippet(snippet_id))


def test_delete_snippet_sends_delete_to_annotations_with_id():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["id"] = request.url.params.get("id")
        return httpx.Response(200, json={"deleted": True, "id": 42})

    result = _run_delete(42, handler)

    assert result is True
    assert seen["method"] == "DELETE"
    assert seen["path"] == "/annotations"
    assert seen["id"] == "42"


def test_delete_snippet_returns_false_on_404():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "not found"})

    assert _run_delete(999, handler) is False


def test_delete_snippet_returns_false_when_service_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("iannotate down")

    assert _run_delete(1, handler) is False


def test_delete_snippet_returns_false_when_backend_reports_not_deleted():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"deleted": False})

    assert _run_delete(7, handler) is False


def test_delete_snippet_uses_configured_url():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host"] = request.url.host
        return httpx.Response(200, json={"deleted": True, "id": 5})

    assert _run_delete(5, handler, url="http://other-iannotate.example:9000") is True
    assert seen["host"] == "other-iannotate.example"


def test_iannotate_url_defaults_when_unconfigured():
    with patch.object(snippets.config, "get", return_value=None):
        assert snippets._iannotate_url() == snippets.DEFAULT_IANNOTATE_URL
