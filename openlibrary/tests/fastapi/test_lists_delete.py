"""Tests for POST /people/{username}/lists/{list_id}/delete.json (FastAPI)."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_site():
    """Mock out the site ContextVar."""
    with patch("openlibrary.fastapi.lists.site") as mock:
        yield mock


@pytest.fixture
def mock_site_for_get_list():
    """Mock out the site ContextVar used in get_list function."""
    with patch("openlibrary.plugins.openlibrary.lists.site") as mock:
        yield mock


@pytest.fixture
def mock_process_delete():
    """Mock out the legacy process_delete method."""
    with patch(
        "openlibrary.fastapi.lists._LegacyListsDelete.process_delete",
        autospec=True,
    ) as mock:
        yield mock


@pytest.fixture
def mock_user_factory(monkeypatch):
    """Factory fixture to create and mock users.

    Usage:
        user = mock_user_factory(key="/people/testuser", is_admin=False)
    """

    def create_user(key: str = "/people/testuser", is_admin: bool = False):
        user = MagicMock()
        user.key = key
        user.is_admin.return_value = is_admin
        monkeypatch.setattr("openlibrary.fastapi.lists.get_current_user", lambda: user)
        return user

    return create_user


@pytest.fixture
def mock_doc_factory(mock_site):
    """Factory fixture to create and mock documents.

    Usage:
        doc = mock_doc_factory(type_key="/type/list")
    """

    def create_doc(type_key: str = "/type/list"):
        doc = MagicMock()
        doc.type.key = type_key
        mock_site.get.return_value.get.return_value = doc
        return doc

    return create_doc


class TestListsDelete:
    def test_delete_success(self, fastapi_client, mock_authenticated_user, mock_doc_factory, mock_user_factory, mock_process_delete):
        """User can delete their own list."""
        mock_doc_factory()
        mock_user_factory(key="/people/testuser", is_admin=False)

        response = fastapi_client.post("/people/testuser/lists/OL1L/delete.json")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        mock_process_delete.assert_called_once()

    def test_delete_unauthenticated(self, fastapi_client):
        """Unauthenticated request returns 401."""
        response = fastapi_client.post("/people/testuser/lists/OL1L/delete.json")
        assert response.status_code == 401

    def test_delete_list_not_found(self, fastapi_client, mock_authenticated_user, mock_site, mock_user_factory):
        """List not found returns 404."""
        mock_site.get.return_value.get.return_value = None
        mock_user_factory()

        response = fastapi_client.post("/people/testuser/lists/OL999L/delete.json")
        assert response.status_code == 404

    def test_delete_wrong_type(self, fastapi_client, mock_authenticated_user, mock_doc_factory, mock_user_factory):
        """Document exists but is not a list type returns 404."""
        mock_doc_factory(type_key="/type/work")
        mock_user_factory()

        response = fastapi_client.post("/people/testuser/lists/OL1L/delete.json")
        assert response.status_code == 404

    def test_delete_forbidden_wrong_user(self, fastapi_client, mock_authenticated_user, mock_doc_factory, mock_user_factory):
        """User cannot delete another user's list (non-admin)."""
        mock_doc_factory()
        mock_user_factory()

        # testuser trying to delete otheruser's list
        response = fastapi_client.post("/people/otheruser/lists/OL1L/delete.json")
        assert response.status_code == 403

    def test_delete_admin_user(self, fastapi_client, mock_authenticated_user, mock_doc_factory, mock_user_factory, mock_process_delete):
        """Admin user can delete any list, even ones they don't own."""
        mock_doc_factory()
        mock_user_factory(key="/people/admin", is_admin=True)

        # Admin deleting another user's list
        response = fastapi_client.post("/people/otheruser/lists/OL1L/delete.json")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        mock_process_delete.assert_called_once()

    def test_invalid_list_id_format(self, fastapi_client, mock_authenticated_user, mock_user_factory):
        """Invalid list_id format returns 422."""
        mock_user_factory()

        response = fastapi_client.post("/people/testuser/lists/invalid-id/delete.json")
        assert response.status_code == 422

    def test_delete_no_prefix_route_forbidden(self, fastapi_client, mock_authenticated_user, mock_doc_factory, mock_user_factory):
        """Legacy route /lists/{list_id}/delete.json requires admin for lists without user prefix."""
        mock_doc_factory()
        mock_user_factory()

        # /lists/OL1L/delete.json corresponds to key="/lists/OL1L"
        # testuser.key is "/people/testuser" so key.startswith(user.key) is False
        # Non-admin cannot delete lists without user prefix
        response = fastapi_client.post("/lists/OL1L/delete.json")
        assert response.status_code == 403

    def test_delete_admin_via_legacy_route(self, fastapi_client, mock_authenticated_user, mock_doc_factory, mock_user_factory, mock_process_delete):
        """Admin can delete via legacy route too."""
        mock_doc_factory()
        mock_user_factory(key="/people/admin", is_admin=True)

        response = fastapi_client.post("/lists/OL123L/delete.json")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        mock_process_delete.assert_called_once()

    def test_delete_forbidden_via_legacy_route(self, fastapi_client, mock_authenticated_user, mock_doc_factory, mock_user_factory):
        """Non-admin cannot delete via legacy route either."""
        mock_doc_factory()
        mock_user_factory()

        # /lists/OL1L/delete.json corresponds to key="/lists/OL1L"
        # testuser.key is "/people/testuser" so key.startswith(user.key) is False
        response = fastapi_client.post("/lists/OL1L/delete.json")
        assert response.status_code == 403


class TestListViewGet:
    """Tests for GET /people/{username}/{category}/{list_id}.json endpoints."""

    def test_get_deleted_list_returns_404(self, fastapi_client, mock_site_for_get_list):
        """GET request for a deleted list should return 404, not 500.

        This is a regression test for a bug where deleted lists caused
        PydanticSerializationError due to Nothing values in the response dict.
        """
        # Mock a deleted list - type is /type/delete but the doc still exists
        deleted_doc = MagicMock()
        deleted_doc.type.key = "/type/delete"
        deleted_doc.key = "/people/testuser/lists/OL1L"
        deleted_doc.name = MagicMock()  # This returns Nothing for deleted docs
        deleted_doc.seed_count = MagicMock()  # This returns Nothing for deleted docs
        mock_site_for_get_list.get.return_value.get.return_value = deleted_doc

        response = fastapi_client.get("/people/testuser/lists/OL1L.json")
        # Should be 404, not 500
        assert response.status_code == 404

    def test_get_deleted_list_via_public_route_returns_404(self, fastapi_client, mock_site_for_get_list):
        """GET request for a deleted list via /lists/{list_id}.json should return 404."""
        deleted_doc = MagicMock()
        deleted_doc.type.key = "/type/delete"
        deleted_doc.key = "/lists/OL1L"
        deleted_doc.name = MagicMock()
        deleted_doc.seed_count = MagicMock()
        mock_site_for_get_list.get.return_value.get.return_value = deleted_doc

        response = fastapi_client.get("/lists/OL1L.json")
        assert response.status_code == 404

    def test_get_existing_list_returns_200(self, fastapi_client, mock_site_for_get_list):
        """GET request for an existing list should return 200 with JSON data."""
        existing_doc = MagicMock()
        existing_doc.type.key = "/type/list"
        existing_doc.key = "/people/testuser/lists/OL1L"
        existing_doc.name = "My Test List"
        existing_doc.description = None
        existing_doc.seed_count = 5
        existing_doc.revision = 1
        existing_doc.created = MagicMock()
        existing_doc.created.isoformat.return_value = "2024-01-01T00:00:00"
        existing_doc.last_modified = MagicMock()
        existing_doc.last_modified.isoformat.return_value = "2024-01-01T00:00:00"
        mock_site_for_get_list.get.return_value.get.return_value = existing_doc

        response = fastapi_client.get("/people/testuser/lists/OL1L.json")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "My Test List"
