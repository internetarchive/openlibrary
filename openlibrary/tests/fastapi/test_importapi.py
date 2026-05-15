"""Tests for the FastAPI import preview endpoints."""

from unittest.mock import MagicMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openlibrary.fastapi.importapi import router


def _raise(exc: Exception) -> None:
    raise exc


def _make_mock_user(
    is_admin: bool = True,
    is_librarian: bool = False,
    is_super_librarian: bool = False,
) -> Mock:
    """Create a mock user with configurable role flags."""
    user = MagicMock()
    user.is_admin.return_value = is_admin
    user.is_librarian.return_value = is_librarian
    user.is_super_librarian.return_value = is_super_librarian
    return user


FAKE_IMPORT_RESULT = {
    "edition": {"key": "/books/OL1M", "title": "Test Book"},
    "success": True,
}


@pytest.fixture
def client() -> TestClient:
    """Return a TestClient for the import preview router."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestImportPreviewAuth:
    """Authentication and authorization tests."""

    def test_get_requires_authentication(self, client, monkeypatch):
        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.get_current_user",
            lambda: None,
        )
        response = client.get("/import/preview?source=amazon:ASIN123")
        assert response.status_code == 401

    def test_post_requires_authentication(self, client, monkeypatch):
        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.get_current_user",
            lambda: None,
        )
        response = client.post("/import/preview", data={"source": "amazon:ASIN123"})
        assert response.status_code == 401

    def test_get_forbidden_for_regular_user(self, client, monkeypatch):
        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.get_current_user",
            lambda: _make_mock_user(is_admin=False, is_librarian=False),
        )
        response = client.get("/import/preview?source=amazon:ASIN123")
        assert response.status_code == 403

    def test_post_forbidden_for_regular_user(self, client, monkeypatch):
        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.get_current_user",
            lambda: _make_mock_user(is_admin=False, is_librarian=False),
        )
        response = client.post("/import/preview", data={"source": "amazon:ASIN123"})
        assert response.status_code == 403

    def test_get_allows_admin(self, client, monkeypatch):
        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.get_current_user",
            lambda: _make_mock_user(is_admin=True),
        )
        mock_req = MagicMock()
        mock_req.metadata_provider.do_import.return_value = FAKE_IMPORT_RESULT
        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.ImportPreviewRequest.from_input",
            lambda i: mock_req,
        )
        response = client.get("/import/preview?source=amazon:ASIN123")
        assert response.status_code == 200

    def test_get_allows_librarian(self, client, monkeypatch):
        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.get_current_user",
            lambda: _make_mock_user(is_admin=False, is_librarian=True),
        )
        mock_req = MagicMock()
        mock_req.metadata_provider.do_import.return_value = FAKE_IMPORT_RESULT
        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.ImportPreviewRequest.from_input",
            lambda i: mock_req,
        )
        response = client.get("/import/preview?source=amazon:ASIN123")
        assert response.status_code == 200

    def test_get_allows_super_librarian(self, client, monkeypatch):
        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.get_current_user",
            lambda: _make_mock_user(is_admin=False, is_librarian=False, is_super_librarian=True),
        )
        mock_req = MagicMock()
        mock_req.metadata_provider.do_import.return_value = FAKE_IMPORT_RESULT
        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.ImportPreviewRequest.from_input",
            lambda i: mock_req,
        )
        response = client.get("/import/preview?source=amazon:ASIN123")
        assert response.status_code == 200


class TestImportPreviewGet:
    """GET /import/preview endpoint tests."""

    def test_get_returns_import_result(self, client, monkeypatch):
        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.get_current_user",
            lambda: _make_mock_user(is_admin=True),
        )
        mock_req = MagicMock()
        mock_req.metadata_provider.do_import.return_value = {
            "edition": {"key": "/books/OL1M", "title": "Test Book"},
            "success": True,
        }
        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.ImportPreviewRequest.from_input",
            lambda i: mock_req,
        )
        response = client.get("/import/preview?source=amazon:ASIN123")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["edition"]["key"] == "/books/OL1M"

    def test_get_does_not_save(self, client, monkeypatch):
        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.get_current_user",
            lambda: _make_mock_user(is_admin=True),
        )
        captured = {}

        def fake_from_input(i):
            captured["save"] = i.get("save", "false")
            mock_req = MagicMock()
            mock_req.metadata_provider.do_import.return_value = FAKE_IMPORT_RESULT
            mock_req.save = False
            return mock_req

        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.ImportPreviewRequest.from_input",
            fake_from_input,
        )
        response = client.get("/import/preview?source=amazon:ASIN123&save=true")
        assert response.status_code == 200
        assert captured["save"] == "false"

    def test_get_invalid_source_returns_error(self, client, monkeypatch):
        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.get_current_user",
            lambda: _make_mock_user(is_admin=True),
        )
        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.ImportPreviewRequest.from_input",
            lambda i: _raise(ValueError("Invalid source provided")),
        )
        response = client.get("/import/preview?source=invalid")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Invalid source provided" in data["error"]

    def test_get_with_provider_and_identifier(self, client, monkeypatch):
        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.get_current_user",
            lambda: _make_mock_user(is_admin=True),
        )
        captured = {}

        def fake_from_input(i):
            captured["params"] = i
            mock_req = MagicMock()
            mock_req.metadata_provider.do_import.return_value = FAKE_IMPORT_RESULT
            mock_req.save = False
            return mock_req

        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.ImportPreviewRequest.from_input",
            fake_from_input,
        )
        response = client.get("/import/preview?provider=amazon&identifier=1234567890")
        assert response.status_code == 200
        assert captured["params"]["provider"] == "amazon"
        assert captured["params"]["identifier"] == "1234567890"

    def test_get_no_params_returns_error(self, client, monkeypatch):
        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.get_current_user",
            lambda: _make_mock_user(is_admin=True),
        )
        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.ImportPreviewRequest.from_input",
            lambda i: _raise(ValueError("Invalid source provided")),
        )
        response = client.get("/import/preview")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False


class TestImportPreviewPost:
    """POST /import/preview endpoint tests."""

    def test_post_returns_import_result(self, client, monkeypatch):
        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.get_current_user",
            lambda: _make_mock_user(is_admin=True),
        )
        mock_req = MagicMock()
        mock_req.metadata_provider.do_import.return_value = FAKE_IMPORT_RESULT
        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.ImportPreviewRequest.from_input",
            lambda i: mock_req,
        )
        response = client.post("/import/preview", data={"source": "amazon:ASIN123"})
        assert response.status_code == 200

    def test_post_can_save(self, client, monkeypatch):
        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.get_current_user",
            lambda: _make_mock_user(is_admin=True),
        )
        captured = {}

        def fake_from_input(i):
            captured["save"] = i.get("save", "false")
            mock_req = MagicMock()
            mock_req.metadata_provider.do_import.return_value = FAKE_IMPORT_RESULT
            mock_req.save = captured["save"] == "true"
            return mock_req

        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.ImportPreviewRequest.from_input",
            fake_from_input,
        )
        response = client.post(
            "/import/preview",
            data={"source": "amazon:ASIN123", "save": "true"},
        )
        assert response.status_code == 200
        assert captured["save"] == "true"

    def test_post_without_save_defaults_to_false(self, client, monkeypatch):
        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.get_current_user",
            lambda: _make_mock_user(is_admin=True),
        )
        captured = {}

        def fake_from_input(i):
            captured["save"] = i.get("save", "false")
            mock_req = MagicMock()
            mock_req.metadata_provider.do_import.return_value = FAKE_IMPORT_RESULT
            mock_req.save = captured["save"] == "true"
            return mock_req

        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.ImportPreviewRequest.from_input",
            fake_from_input,
        )
        response = client.post("/import/preview", data={"source": "amazon:ASIN123"})
        assert response.status_code == 200
        assert captured["save"] == "false"

    def test_post_invalid_source_returns_error(self, client, monkeypatch):
        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.get_current_user",
            lambda: _make_mock_user(is_admin=True),
        )
        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.ImportPreviewRequest.from_input",
            lambda i: _raise(ValueError("Invalid source provided")),
        )
        response = client.post("/import/preview", data={"source": "invalid"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
