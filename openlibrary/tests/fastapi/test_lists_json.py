"""Tests for the FastAPI lists.json endpoints."""

from unittest.mock import Mock, patch

from infogami.infobase import client as infobase_client
from openlibrary.plugins.openlibrary.lists import SpamListError


class TestListsJsonGet:
    def test_people_lists_validates_pagination_params(self, fastapi_client):
        current_site = object()
        expected = {"links": {"self": "/people/alice", "next": None, "prev": None}, "size": 1, "entries": []}

        with (
            patch("openlibrary.fastapi.lists.site") as mock_site_context,
            patch("openlibrary.fastapi.lists.legacy_lists.lists_json.get_lists_data", return_value=expected) as mock_get_lists,
        ):
            mock_site_context.get.return_value = current_site

            response = fastapi_client.get(
                "/people/alice/lists.json",
                params={"limit": "100", "offset": "0"},
            )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        assert response.json() == expected
        mock_get_lists.assert_called_once_with(
            "/people/alice",
            site_obj=current_site,
            limit=100,
            offset=0,
            query_path="/people/alice/lists.json",
        )

    def test_people_lists_rejects_invalid_limit(self, fastapi_client):
        response = fastapi_client.get(
            "/people/alice/lists.json",
            params={"limit": "500"},
        )
        assert response.status_code == 422

    def test_people_lists_rejects_negative_offset(self, fastapi_client):
        response = fastapi_client.get(
            "/people/alice/lists.json",
            params={"offset": "-10"},
        )
        assert response.status_code == 422

    def test_people_lists_rejects_non_numeric_limit(self, fastapi_client):
        response = fastapi_client.get(
            "/people/alice/lists.json",
            params={"limit": "not-a-number"},
        )
        assert response.status_code == 422

    def test_work_lists_uses_default_pagination(self, fastapi_client):
        current_site = object()
        expected = {"links": {"self": "/works/OL42W", "next": None, "prev": None}, "size": 0, "entries": []}

        with (
            patch("openlibrary.fastapi.lists.site") as mock_site_context,
            patch("openlibrary.fastapi.lists.legacy_lists.lists_json.get_lists_data", return_value=expected) as mock_get_lists,
        ):
            mock_site_context.get.return_value = current_site

            response = fastapi_client.get("/works/OL42W/lists.json")

        assert response.status_code == 200
        assert response.json() == expected
        mock_get_lists.assert_called_once_with(
            "/works/OL42W",
            site_obj=current_site,
            limit=50,
            offset=0,
            query_path="/works/OL42W/lists.json",
        )

    def test_subject_lists_reconstructs_subject_path(self, fastapi_client):
        current_site = object()
        expected = {"links": {"self": "/subjects/person:tolkien"}, "size": 0, "entries": []}

        with (
            patch("openlibrary.fastapi.lists.site") as mock_site_context,
            patch("openlibrary.fastapi.lists.legacy_lists.lists_json.get_lists_data", return_value=expected) as mock_get_lists,
        ):
            mock_site_context.get.return_value = current_site

            response = fastapi_client.get("/subjects/person:tolkien/lists.json")

        assert response.status_code == 200
        mock_get_lists.assert_called_once_with(
            "/subjects/person:tolkien",
            site_obj=current_site,
            limit=50,
            offset=0,
            query_path="/subjects/person:tolkien/lists.json",
        )

    def test_missing_doc_returns_404(self, fastapi_client):
        with (
            patch("openlibrary.fastapi.lists.site") as mock_site_context,
            patch("openlibrary.fastapi.lists.legacy_lists.lists_json.get_lists_data", return_value=None),
        ):
            mock_site_context.get.return_value = object()

            response = fastapi_client.get("/authors/OL1A/lists.json")

        assert response.status_code == 404


class TestListsJsonPost:
    def test_create_list_uses_legacy_process_method(self, fastapi_client, mock_authenticated_user):
        current_site = Mock()
        user = object()
        expected = {"key": "/people/alice/lists/OL1L", "revision": 1}
        current_site.get.return_value = user
        current_site.can_write.return_value = True

        def process_new_list(user_arg, data_arg, site_arg):
            return expected

        with (
            patch("openlibrary.fastapi.lists.site") as mock_site_context,
            patch("openlibrary.fastapi.lists.legacy_lists.lists_json.process_new_list", side_effect=process_new_list) as mock_process,
        ):
            mock_site_context.get.return_value = current_site

            response = fastapi_client.post(
                "/people/alice/lists.json",
                content=b'{"name": "Favorites", "seeds": []}',
                headers={"content-type": "application/json"},
            )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        assert response.json() == expected
        current_site.get.assert_called_once_with("/people/alice")
        current_site.can_write.assert_called_once_with("/people/alice")
        mock_process.assert_called_once_with(
            user,
            {"name": "Favorites", "description": "", "tags": [], "seeds": []},
            current_site,
        )

    def test_missing_user_returns_404(self, fastapi_client, mock_authenticated_user):
        current_site = Mock()
        current_site.get.return_value = None

        with (
            patch("openlibrary.fastapi.lists.site") as mock_site_context,
            patch("openlibrary.fastapi.lists.legacy_lists.lists_json.process_new_list") as mock_process,
        ):
            mock_site_context.get.return_value = current_site

            response = fastapi_client.post(
                "/people/alice/lists.json",
                content=b'{"name": "Favorites"}',
                headers={"content-type": "application/json"},
            )

        assert response.status_code == 404
        current_site.can_write.assert_not_called()
        mock_process.assert_not_called()

    def test_permission_denied_returns_forbidden(self, fastapi_client, mock_authenticated_user):
        current_site = Mock()
        current_site.get.return_value = object()
        current_site.can_write.return_value = False

        with patch("openlibrary.fastapi.lists.site") as mock_site_context:
            mock_site_context.get.return_value = current_site

            response = fastapi_client.post(
                "/people/alice/lists.json",
                content=b'{"name": "Favorites"}',
                headers={"content-type": "application/json"},
            )

        assert response.status_code == 403
        assert response.json() == {"detail": "Permission denied."}

    def test_spam_list_returns_forbidden(self, fastapi_client, mock_authenticated_user):
        current_site = Mock()
        current_site.get.return_value = object()
        current_site.can_write.return_value = True

        with (
            patch("openlibrary.fastapi.lists.site") as mock_site_context,
            patch(
                "openlibrary.fastapi.lists.legacy_lists.lists_json.process_new_list",
                side_effect=SpamListError(),
            ),
        ):
            mock_site_context.get.return_value = current_site

            response = fastapi_client.post(
                "/people/alice/lists.json",
                content=b'{"name": "Favorites"}',
                headers={"content-type": "application/json"},
            )

        assert response.status_code == 403
        assert response.json() == {"detail": "Permission denied."}

    def test_client_exception_preserves_status_code(self, fastapi_client, mock_authenticated_user):
        current_site = Mock()
        current_site.get.return_value = object()
        current_site.can_write.return_value = True

        with (
            patch("openlibrary.fastapi.lists.site") as mock_site_context,
            patch(
                "openlibrary.fastapi.lists.legacy_lists.lists_json.process_new_list",
                side_effect=infobase_client.ClientException(
                    "409 Conflict",
                    "Duplicate list",
                ),
            ),
        ):
            mock_site_context.get.return_value = current_site

            response = fastapi_client.post(
                "/people/alice/lists.json",
                content=b'{"name": "Favorites"}',
                headers={"content-type": "application/json"},
            )

        assert response.status_code == 409
        assert response.json() == {"detail": "Duplicate list"}
