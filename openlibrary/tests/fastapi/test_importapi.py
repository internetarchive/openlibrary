"""Tests for the FastAPI import preview endpoints."""

from unittest.mock import MagicMock

import pytest

from openlibrary.utils.request_context import RequestContextVars, req_context, site


def _raise(exc: Exception) -> None:
    raise exc


FAKE_IMPORT_RESULT = {
    "edition": {"key": "/books/OL1M", "title": "Test Book"},
    "success": True,
}


@pytest.fixture(autouse=True)
def _setup_request_context():
    """Set ContextVars for tests that reach _build_preview_response."""
    site.set(MagicMock())
    req_context.set(
        RequestContextVars(
            x_forwarded_for=None,
            user_agent=None,
            lang="en",
            solr_editions=True,
            print_disabled=False,
        )
    )


@pytest.fixture
def mock_user_factory(monkeypatch):
    """Factory fixture to create and mock users with configurable roles.

    Usage:
        user = mock_user_factory(is_admin=True)
        user = mock_user_factory(is_librarian=True)
    """

    def create_user(
        is_admin: bool = False,
        is_librarian: bool = False,
        is_super_librarian: bool = False,
    ):
        user = MagicMock()
        user.is_admin.return_value = is_admin
        user.is_librarian.return_value = is_librarian
        user.is_super_librarian.return_value = is_super_librarian
        monkeypatch.setattr("openlibrary.fastapi.auth.get_current_user", lambda: user)
        return user

    return create_user


@pytest.fixture
def mock_import_request():
    """Return a factory that creates a mock ImportPreviewRequest."""

    def _make(save: bool = False):
        mock_req = MagicMock()
        mock_req.metadata_provider.do_import.return_value = FAKE_IMPORT_RESULT
        mock_req.save = save
        return mock_req

    return _make


class TestImportPreviewAuth:
    """Authentication and authorization tests."""

    def test_get_requires_authentication(self, fastapi_client):
        response = fastapi_client.get("/import/preview.json?source=amazon:ASIN123")
        assert response.status_code == 401

    def test_post_requires_authentication(self, fastapi_client):
        response = fastapi_client.post("/import/preview.json", data={"source": "amazon:ASIN123"})
        assert response.status_code == 401

    def test_get_forbidden_for_regular_user(self, fastapi_client, mock_authenticated_user, mock_user_factory):
        mock_user_factory()
        response = fastapi_client.get("/import/preview.json?source=amazon:ASIN123")
        assert response.status_code == 403

    def test_post_forbidden_for_regular_user(self, fastapi_client, mock_authenticated_user, mock_user_factory):
        mock_user_factory()
        response = fastapi_client.post("/import/preview.json", data={"source": "amazon:ASIN123"})
        assert response.status_code == 403

    def test_get_allows_admin(self, fastapi_client, mock_authenticated_user, mock_user_factory, mock_import_request, monkeypatch):
        mock_user_factory(is_admin=True)
        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.ImportPreviewRequest.from_input",
            lambda i: mock_import_request(),
        )
        response = fastapi_client.get("/import/preview.json?source=amazon:ASIN123")
        assert response.status_code == 200

    def test_get_allows_librarian(self, fastapi_client, mock_authenticated_user, mock_user_factory, mock_import_request, monkeypatch):
        mock_user_factory(is_librarian=True)
        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.ImportPreviewRequest.from_input",
            lambda i: mock_import_request(),
        )
        response = fastapi_client.get("/import/preview.json?source=amazon:ASIN123")
        assert response.status_code == 200

    def test_get_allows_super_librarian(self, fastapi_client, mock_authenticated_user, mock_user_factory, mock_import_request, monkeypatch):
        mock_user_factory(is_super_librarian=True)
        monkeypatch.setattr(
            "openlibrary.fastapi.importapi.ImportPreviewRequest.from_input",
            lambda i: mock_import_request(),
        )
        response = fastapi_client.get("/import/preview.json?source=amazon:ASIN123")
        assert response.status_code == 200


class TestImportPreviewGet:
    """GET /import/preview.json endpoint tests."""

    @pytest.fixture(autouse=True)
    def _auth_setup(self, fastapi_client, mock_authenticated_user, mock_user_factory, monkeypatch):
        self.client = fastapi_client
        self.monkeypatch = monkeypatch
        mock_user_factory(is_admin=True)

    def test_get_returns_import_result(self, mock_import_request):
        self.monkeypatch.setattr(
            "openlibrary.fastapi.importapi.ImportPreviewRequest.from_input",
            lambda i: mock_import_request(),
        )
        response = self.client.get("/import/preview.json?source=amazon:ASIN123")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["edition"]["key"] == "/books/OL1M"

    def test_get_does_not_save(self):
        captured = {}

        def fake_from_input(i):
            captured["save"] = i.get("save", "false")
            mock_req = MagicMock()
            mock_req.metadata_provider.do_import.return_value = FAKE_IMPORT_RESULT
            mock_req.save = False
            return mock_req

        self.monkeypatch.setattr(
            "openlibrary.fastapi.importapi.ImportPreviewRequest.from_input",
            fake_from_input,
        )
        response = self.client.get("/import/preview.json?source=amazon:ASIN123&save=true")
        assert response.status_code == 200
        assert captured["save"] == "false"

    def test_get_invalid_source_returns_error(self):
        self.monkeypatch.setattr(
            "openlibrary.fastapi.importapi.ImportPreviewRequest.from_input",
            lambda i: _raise(ValueError("Invalid source provided")),
        )
        response = self.client.get("/import/preview.json?source=invalid")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Invalid source provided" in data["error"]

    def test_get_with_provider_and_identifier(self):
        captured = {}

        def fake_from_input(i):
            captured["params"] = i
            mock_req = MagicMock()
            mock_req.metadata_provider.do_import.return_value = FAKE_IMPORT_RESULT
            mock_req.save = False
            return mock_req

        self.monkeypatch.setattr(
            "openlibrary.fastapi.importapi.ImportPreviewRequest.from_input",
            fake_from_input,
        )
        response = self.client.get("/import/preview.json?provider=amazon&identifier=1234567890")
        assert response.status_code == 200
        assert captured["params"]["provider"] == "amazon"
        assert captured["params"]["identifier"] == "1234567890"

    def test_get_no_params_returns_error(self):
        self.monkeypatch.setattr(
            "openlibrary.fastapi.importapi.ImportPreviewRequest.from_input",
            lambda i: _raise(ValueError("No provider specified")),
        )
        response = self.client.get("/import/preview.json")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False


class TestImportPreviewPost:
    """POST /import/preview.json endpoint tests."""

    @pytest.fixture(autouse=True)
    def _auth_setup(self, fastapi_client, mock_authenticated_user, mock_user_factory, monkeypatch):
        self.client = fastapi_client
        self.monkeypatch = monkeypatch
        mock_user_factory(is_admin=True)

    def test_post_returns_import_result(self, mock_import_request):
        self.monkeypatch.setattr(
            "openlibrary.fastapi.importapi.ImportPreviewRequest.from_input",
            lambda i: mock_import_request(),
        )
        response = self.client.post("/import/preview.json", data={"source": "amazon:ASIN123"})
        assert response.status_code == 200

    def test_post_can_save(self):
        captured = {}

        def fake_from_input(i):
            captured["save"] = i.get("save", "false")
            mock_req = MagicMock()
            mock_req.metadata_provider.do_import.return_value = FAKE_IMPORT_RESULT
            mock_req.save = captured["save"] == "true"
            return mock_req

        self.monkeypatch.setattr(
            "openlibrary.fastapi.importapi.ImportPreviewRequest.from_input",
            fake_from_input,
        )
        response = self.client.post(
            "/import/preview.json",
            data={"source": "amazon:ASIN123", "save": "true"},
        )
        assert response.status_code == 200
        assert captured["save"] == "true"

    def test_post_without_save_defaults_to_false(self):
        captured = {}

        def fake_from_input(i):
            captured["save"] = i.get("save", "false")
            mock_req = MagicMock()
            mock_req.metadata_provider.do_import.return_value = FAKE_IMPORT_RESULT
            return mock_req

        self.monkeypatch.setattr(
            "openlibrary.fastapi.importapi.ImportPreviewRequest.from_input",
            fake_from_input,
        )
        response = self.client.post("/import/preview.json", data={"source": "amazon:ASIN123"})
        assert response.status_code == 200
        assert captured["save"] == "false"

    def test_post_invalid_source_returns_error(self):
        self.monkeypatch.setattr(
            "openlibrary.fastapi.importapi.ImportPreviewRequest.from_input",
            lambda i: _raise(ValueError("Invalid source provided")),
        )
        response = self.client.post("/import/preview.json", data={"source": "invalid"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
