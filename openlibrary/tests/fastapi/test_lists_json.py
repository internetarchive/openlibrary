"""Tests for the FastAPI lists.json endpoints."""

from unittest.mock import Mock, patch

import web

from infogami.infobase import client as infobase_client


class TestListsJsonGet:
    def test_people_lists_clamps_legacy_pagination(self, fastapi_client):
        current_site = object()
        expected = {"links": {"self": "/people/alice"}, "size": 1, "entries": []}

        with (
            patch("openlibrary.fastapi.lists.site") as mock_site_context,
            patch("openlibrary.fastapi.lists.legacy_lists.get_lists_json_data", return_value=expected) as mock_get_lists,
        ):
            mock_site_context.get.return_value = current_site

            response = fastapi_client.get(
                "/people/alice/lists.json",
                params={"limit": "500", "offset": "-10"},
            )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        assert response.json() == expected
        mock_get_lists.assert_called_once_with(
            "/people/alice",
            current_site,
            limit=100,
            offset=0,
            query={"limit": "500", "offset": "-10"},
            query_path="/people/alice/lists.json",
        )

    def test_work_lists_uses_legacy_safeint_defaults(self, fastapi_client):
        current_site = object()
        expected = {"links": {"self": "/works/OL42W"}, "size": 0, "entries": []}

        with (
            patch("openlibrary.fastapi.lists.site") as mock_site_context,
            patch("openlibrary.fastapi.lists.legacy_lists.get_lists_json_data", return_value=expected) as mock_get_lists,
        ):
            mock_site_context.get.return_value = current_site

            response = fastapi_client.get(
                "/works/OL42W/lists.json",
                params={"limit": "not-a-number", "offset": "still-not-a-number"},
            )

        assert response.status_code == 200
        assert response.json() == expected
        mock_get_lists.assert_called_once_with(
            "/works/OL42W",
            current_site,
            limit=50,
            offset=0,
            query={"limit": "not-a-number", "offset": "still-not-a-number"},
            query_path="/works/OL42W/lists.json",
        )

    def test_subject_lists_reconstructs_subject_path(self, fastapi_client):
        current_site = object()
        expected = {"links": {"self": "/subjects/person:tolkien"}, "size": 0, "entries": []}

        with (
            patch("openlibrary.fastapi.lists.site") as mock_site_context,
            patch("openlibrary.fastapi.lists.legacy_lists.get_lists_json_data", return_value=expected) as mock_get_lists,
        ):
            mock_site_context.get.return_value = current_site

            response = fastapi_client.get("/subjects/person:tolkien/lists.json")

        assert response.status_code == 200
        mock_get_lists.assert_called_once_with(
            "/subjects/person:tolkien",
            current_site,
            limit=50,
            offset=0,
            query={},
            query_path="/subjects/person:tolkien/lists.json",
        )

    def test_missing_doc_returns_404(self, fastapi_client):
        with (
            patch("openlibrary.fastapi.lists.site") as mock_site_context,
            patch("openlibrary.fastapi.lists.legacy_lists.get_lists_json_data", return_value=None),
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
            assert web.ctx.site is current_site
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
            {"name": "Favorites", "seeds": []},
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
                side_effect=ValueError("Spam list"),
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

    def test_client_exception_returns_conflict(self, fastapi_client, mock_authenticated_user):
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
