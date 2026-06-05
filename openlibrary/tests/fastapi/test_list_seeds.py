"""Tests for the FastAPI list/series seeds endpoints."""

from unittest.mock import MagicMock, patch

import pytest

FAKE_SEEDS = {"entries": [{"url": "/works/OL123W", "type": "work"}], "size": 1}


class TestListSeedsGet:
    """Tests for GET seeds endpoints (public and user-specific)."""

    def test_get_list_seeds_public_success(self, fastapi_client, monkeypatch):
        monkeypatch.setattr("openlibrary.fastapi.lists.get_list_seeds", lambda key: FAKE_SEEDS)
        response = fastapi_client.get("/lists/OL3L/seeds.json")
        assert response.status_code == 200
        assert response.json() == FAKE_SEEDS

    def test_get_series_seeds_public_success(self, fastapi_client, monkeypatch):
        monkeypatch.setattr("openlibrary.fastapi.lists.get_list_seeds", lambda key: FAKE_SEEDS)
        response = fastapi_client.get("/series/OL3L/seeds.json")
        assert response.status_code == 200
        assert response.json() == FAKE_SEEDS

    def test_get_list_seeds_user_success(self, fastapi_client, monkeypatch):
        monkeypatch.setattr("openlibrary.fastapi.lists.get_list_seeds", lambda key: FAKE_SEEDS)
        response = fastapi_client.get("/people/testuser/lists/OL3L/seeds.json")
        assert response.status_code == 200
        assert response.json() == FAKE_SEEDS

    def test_get_series_seeds_user_success(self, fastapi_client, monkeypatch):
        monkeypatch.setattr("openlibrary.fastapi.lists.get_list_seeds", lambda key: FAKE_SEEDS)
        response = fastapi_client.get("/people/testuser/series/OL3L/seeds.json")
        assert response.status_code == 200
        assert response.json() == FAKE_SEEDS

    def test_get_list_seeds_not_found(self, fastapi_client, monkeypatch):
        monkeypatch.setattr("openlibrary.fastapi.lists.get_list_seeds", lambda key: None)
        response = fastapi_client.get("/lists/OL999999L/seeds.json")
        assert response.status_code == 404
        assert response.json() == {"detail": "List or Series not found"}


class TestListSeedsPost:
    """Tests for POST seeds endpoints."""

    def test_post_seeds_unauthorized(self, fastapi_client):
        """Unauthenticated requests to mutate seeds should be rejected."""
        response = fastapi_client.post("/lists/OL3L/seeds.json", json={"add": ["/works/OL123W"], "remove": []})
        assert response.status_code == 401

    @pytest.mark.parametrize(
        ("url", "payload"),
        [
            ("/lists/OL3L/seeds.json", {"add": ["/works/OL123W"], "remove": []}),
            (
                "/people/testuser/lists/OL3L/seeds.json",
                {"add": ["/works/OL123W"], "remove": ["/works/OL456W"]},
            ),
            ("/series/OL3L/seeds.json", {"add": ["/works/OL123W"], "remove": []}),
        ],
    )
    def test_post_seeds_success(self, fastapi_client, mock_authenticated_user, url, payload):
        """Authenticated user with write access can update seeds on any route."""
        expected = {"status": "ok"}

        with (
            patch("openlibrary.fastapi.lists.site") as mock_site_context,
            patch(
                "openlibrary.fastapi.lists._LegacyListSeeds.process_seeds_update",
                return_value=expected,
            ) as mock_process,
        ):
            mock_list = MagicMock()
            mock_site = MagicMock()
            mock_site.get.return_value = mock_list
            mock_site.can_write.return_value = True
            mock_site_context.get.return_value = mock_site

            response = fastapi_client.post(url, json=payload)

        assert response.status_code == 200
        assert response.json() == expected
        mock_process.assert_called_once()

    def test_post_seeds_list_not_found(self, fastapi_client, mock_authenticated_user):
        """POST to a non-existent list should return 404."""
        with patch("openlibrary.fastapi.lists.site") as mock_site_context:
            mock_site = MagicMock()
            mock_site.get.return_value = None
            mock_site_context.get.return_value = mock_site

            response = fastapi_client.post("/lists/OL999L/seeds.json", json={"add": [], "remove": []})

        assert response.status_code == 404
        assert response.json() == {"detail": "List or Series not found"}

    def test_post_seeds_forbidden(self, fastapi_client, mock_authenticated_user):
        """Authenticated user without write access should receive 403."""
        with patch("openlibrary.fastapi.lists.site") as mock_site_context:
            mock_list = MagicMock()
            mock_site = MagicMock()
            mock_site.get.return_value = mock_list
            mock_site.can_write.return_value = False
            mock_site_context.get.return_value = mock_site

            response = fastapi_client.post("/lists/OL3L/seeds.json", json={"add": [], "remove": []})

        assert response.status_code == 403
        assert response.json() == {"detail": "Permission denied."}
