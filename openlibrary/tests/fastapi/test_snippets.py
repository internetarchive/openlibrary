"""Tests for the /snippets FastAPI router (openlibrary.fastapi.snippets)."""

from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from openlibrary.fastapi import snippets as snippets_module
from openlibrary.fastapi.auth import AuthenticatedUser, require_authenticated_user

FAKE_AUTH_USER = AuthenticatedUser(
    username="tester",
    user_key="/people/tester",
    timestamp="2026-01-01T00:00:00",
)


def _build_app():
    app = FastAPI()
    app.include_router(snippets_module.router)
    return app


def _patch_delete(return_value):
    """Patch the iannotate delete client the router calls, recording its args."""
    calls = []

    async def fake_delete(snippet_id):
        calls.append(snippet_id)
        return return_value

    return patch.object(snippets_module, "delete_snippet", fake_delete), calls


def test_delete_requires_authentication():
    app = _build_app()
    client = TestClient(app, raise_server_exceptions=False)
    assert client.delete("/snippets/42").status_code == 401


def test_delete_refuses_non_super_librarian():
    app = _build_app()
    app.dependency_overrides[require_authenticated_user] = lambda: FAKE_AUTH_USER
    patcher, calls = _patch_delete(True)

    with patch("openlibrary.fastapi.auth.get_current_user") as mock_user, patcher:
        mock_user.return_value.is_super_librarian_or_higher.return_value = False
        client = TestClient(app, raise_server_exceptions=False)
        response = client.delete("/snippets/42")

    assert response.status_code == 403
    assert calls == []  # the delete must not run for a refused caller
    app.dependency_overrides.clear()


def test_delete_succeeds_for_super_librarian():
    app = _build_app()
    app.dependency_overrides[require_authenticated_user] = lambda: FAKE_AUTH_USER
    patcher, calls = _patch_delete(True)

    with patch("openlibrary.fastapi.auth.get_current_user") as mock_user, patcher:
        mock_user.return_value.is_super_librarian_or_higher.return_value = True
        client = TestClient(app, raise_server_exceptions=False)
        response = client.delete("/snippets/42")

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "id": 42}
    assert calls == [42]
    app.dependency_overrides.clear()


def test_delete_returns_404_when_backend_reports_not_deleted():
    app = _build_app()
    app.dependency_overrides[require_authenticated_user] = lambda: FAKE_AUTH_USER
    patcher, _calls = _patch_delete(False)

    with patch("openlibrary.fastapi.auth.get_current_user") as mock_user, patcher:
        mock_user.return_value.is_super_librarian_or_higher.return_value = True
        client = TestClient(app, raise_server_exceptions=False)
        response = client.delete("/snippets/999")

    assert response.status_code == 404
    app.dependency_overrides.clear()


def test_delete_rejects_non_integer_id():
    app = _build_app()
    app.dependency_overrides[require_authenticated_user] = lambda: FAKE_AUTH_USER

    with patch("openlibrary.fastapi.auth.get_current_user") as mock_user:
        mock_user.return_value.is_super_librarian_or_higher.return_value = True
        client = TestClient(app, raise_server_exceptions=False)
        # A non-numeric id must not reach the handler (also why HAProxy keys on
        # snippets/[0-9]+): FastAPI rejects it as a validation error.
        response = client.delete("/snippets/notanumber")

    assert response.status_code == 422
    app.dependency_overrides.clear()
