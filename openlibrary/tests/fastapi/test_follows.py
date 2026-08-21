from datetime import datetime
from unittest.mock import patch

import pytest

FAKE_FOLLOWING = [
    {
        "subscriber": "testuser",
        "publisher": "author1",
        "disabled": False,
        "updated": datetime(2026, 1, 1, 12, 0, 0),
        "created": datetime(2026, 1, 1, 12, 0, 0),
    },
]


class TestGetPatronFollows:
    def test_returns_following_list(self, fastapi_client, mock_optional_authenticated_user):
        with patch("openlibrary.fastapi.internal.api.PubSub.get_following", return_value=FAKE_FOLLOWING):
            response = fastapi_client.get("/people/testuser/follows.json")

        assert response.status_code == 200
        assert response.json() == [
            {
                "subscriber": "testuser",
                "publisher": "author1",
                "disabled": False,
                "updated": "2026-01-01T12:00:00",
                "created": "2026-01-01T12:00:00",
            }
        ]

    def test_empty_list(self, fastapi_client, mock_optional_authenticated_user):
        with patch("openlibrary.fastapi.internal.api.PubSub.get_following", return_value=[]):
            response = fastapi_client.get("/people/testuser/follows.json")

        assert response.status_code == 200
        assert response.json() == []

    def test_unauthenticated_redirects_to_login(self, fastapi_client):
        response = fastapi_client.get("/people/testuser/follows.json", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"].startswith("/account/login")

    def test_wrong_user_redirects_to_login(self, fastapi_client, mock_optional_authenticated_user):
        response = fastapi_client.get("/people/otheruser/follows.json", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"].startswith("/account/login")

    def test_redirect_preserves_redir_url(self, fastapi_client):
        response = fastapi_client.get("/people/testuser/follows.json?redir_url=/books", follow_redirects=False)

        assert response.status_code == 303
        assert "redir_url=%2Fbooks" in response.headers["location"]


class TestPostPatronFollows:
    @pytest.mark.parametrize(
        ("state", "expected_method"),
        [
            ("0", "subscribe"),
            ("1", "unsubscribe"),
            ("", "unsubscribe"),  # missing/empty state defaults to unsubscribe
        ],
    )
    def test_routes_state_to_subscribe_or_unsubscribe(
        self,
        fastapi_client,
        mock_optional_authenticated_user,
        state,
        expected_method,
    ):
        with (
            patch("openlibrary.fastapi.internal.api.accounts.find", return_value=True),
            patch(f"openlibrary.fastapi.internal.api.PubSub.{expected_method}") as mock_action,
        ):
            response = fastapi_client.post(
                "/people/testuser/follows.json",
                data={"publisher": "author1", "state": state},
                follow_redirects=False,
            )

        assert response.status_code == 303
        mock_action.assert_called_once_with("testuser", "author1")

    def test_unauthenticated_redirects_to_login(self, fastapi_client):
        response = fastapi_client.post(
            "/people/testuser/follows.json",
            data={"publisher": "author1", "redir_url": "/"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"].startswith("/account/login")

    def test_wrong_user_redirects_to_login_and_preserves_redir_url(self, fastapi_client, mock_optional_authenticated_user):
        response = fastapi_client.post(
            "/people/otheruser/follows.json",
            data={"publisher": "author1", "redir_url": "/books/OL1M", "state": "0"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "redir_url=%2Fbooks%2FOL1M" in response.headers["location"]

    def test_nonexistent_publisher_returns_404(self, fastapi_client, mock_optional_authenticated_user):
        with patch("openlibrary.fastapi.internal.api.accounts.find", return_value=None):
            response = fastapi_client.post(
                "/people/testuser/follows.json",
                data={"publisher": "nonexistent_user", "redir_url": "/", "state": "0"},
            )

        assert response.status_code == 404

    def test_success_redirects_to_redir_url(self, fastapi_client, mock_optional_authenticated_user):
        with (
            patch("openlibrary.fastapi.internal.api.accounts.find", return_value=True),
            patch("openlibrary.fastapi.internal.api.PubSub.subscribe"),
        ):
            response = fastapi_client.post(
                "/people/testuser/follows.json",
                data={"publisher": "author1", "redir_url": "/books/OL1M", "state": "0"},
                follow_redirects=False,
            )

        assert response.status_code == 303
        assert response.headers["location"] == "/books/OL1M"
