"""Tests for POST /people/{username}/lists/{list_id}/delete.json (FastAPI)."""
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_site():
    with patch("openlibrary.fastapi.lists.site") as mock:
        yield mock


@pytest.fixture
def mock_process_delete():
    with patch(
        "openlibrary.fastapi.lists._LegacyListsDelete.process_delete",
        autospec=True,
    ) as mock:
        yield mock


class TestListsDelete:
    def test_delete_success(
        self, fastapi_client, mock_authenticated_user, mock_site, mock_process_delete
    ):
        doc = MagicMock()
        doc.type.key = "/type/list"
        mock_site.get.return_value.get.return_value = doc

        response = fastapi_client.post(
            "/people/testuser/lists/OL1L/delete.json"
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        mock_process_delete.assert_called_once()

    def test_delete_unauthenticated(self, fastapi_client):
        response = fastapi_client.post(
            "/people/testuser/lists/OL1L/delete.json"
        )
        assert response.status_code == 401

    def test_delete_list_not_found(
        self, fastapi_client, mock_authenticated_user, mock_site
    ):
        mock_site.get.return_value.get.return_value = None

        response = fastapi_client.post(
            "/people/testuser/lists/OL999L/delete.json"
        )
        assert response.status_code == 404

    def test_delete_wrong_type(
        self, fastapi_client, mock_authenticated_user, mock_site
    ):
        doc = MagicMock()
        doc.type.key = "/type/work"
        mock_site.get.return_value.get.return_value = doc

        response = fastapi_client.post(
            "/people/testuser/lists/OL1L/delete.json"
        )
        assert response.status_code == 404

    def test_delete_forbidden_wrong_user(
        self, fastapi_client, mock_authenticated_user, mock_site
    ):
        doc = MagicMock()
        doc.type.key = "/type/list"
        mock_site.get.return_value.get.return_value = doc

        # testuser trying to delete otheruser's list
        response = fastapi_client.post(
            "/people/otheruser/lists/OL1L/delete.json"
        )
        assert response.status_code == 403
