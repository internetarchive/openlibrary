from datetime import datetime
from unittest.mock import patch

import pytest

from openlibrary.fastapi.auth import AuthenticatedUser, get_authenticated_user
from openlibrary.fastapi.internal.api import FollowEntry

FAKE_FOLLOWING = [
    {
        "subscriber": "testuser",
        "publisher": "author1",
        "disabled": False,
        "updated": datetime(2026, 1, 1, 12, 0, 0),
        "created": datetime(2026, 1, 1, 12, 0, 0),
    },
]


@pytest.fixture
def mock_auth_user(fastapi_client):
    fake_user = AuthenticatedUser(
        username="testuser",
        user_key="/people/testuser",
        timestamp="2026-01-01T00:00:00",
    )
    fastapi_client.app.dependency_overrides[get_authenticated_user] = lambda: fake_user
    yield fake_user
    fastapi_client.app.dependency_overrides.pop(get_authenticated_user, None)


class TestGetPatronFollows:
    def test_get_follows_returns_following(self, fastapi_client, mock_auth_user):
        with patch("openlibrary.fastapi.internal.api.PubSub.get_following", return_value=FAKE_FOLLOWING):
            response = fastapi_client.get("/people/testuser/follows.json")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        FollowEntry(**data[0])
        assert data[0]["publisher"] == "author1"
        assert data[0]["subscriber"] == "testuser"
        assert data[0]["disabled"] is False
        assert data[0]["updated"] == "2026-01-01T12:00:00"
        assert data[0]["created"] == "2026-01-01T12:00:00"

    def test_get_follows_requires_authentication(self, fastapi_client):
        response = fastapi_client.get("/people/testuser/follows.json", follow_redirects=False)

        assert response.status_code == 303

    def test_get_follows_redirects_for_wrong_user(self, fastapi_client, mock_auth_user):
        response = fastapi_client.get("/people/otheruser/follows.json", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"].startswith("/account/login")

    def test_get_follows_redirects_with_redir_url(self, fastapi_client):
        response = fastapi_client.get("/people/testuser/follows.json?redir_url=/books", follow_redirects=False)

        assert response.status_code == 303
        assert "redir_url=%2Fbooks" in response.headers["location"]

    def test_get_follows_empty_list(self, fastapi_client, mock_auth_user):
        with patch("openlibrary.fastapi.internal.api.PubSub.get_following", return_value=[]):
            response = fastapi_client.get("/people/testuser/follows.json")

        assert response.status_code == 200
        assert response.json() == []


class TestPostPatronFollows:
    def test_post_follows_subscribes(self, fastapi_client, mock_auth_user):
        with (
            patch("openlibrary.fastapi.internal.api.accounts.find") as mock_find,
            patch("openlibrary.fastapi.internal.api.PubSub.subscribe") as mock_subscribe,
        ):
            mock_find.return_value = True
            response = fastapi_client.post(
                "/people/testuser/follows.json",
                data={"publisher": "author1", "state": "0"},
                follow_redirects=False,
            )

        assert response.status_code == 303
        mock_find.assert_called_once_with(username="author1")
        mock_subscribe.assert_called_once_with("testuser", "author1")

    def test_post_follows_unsubscribes(self, fastapi_client, mock_auth_user):
        with (
            patch("openlibrary.fastapi.internal.api.accounts.find") as mock_find,
            patch("openlibrary.fastapi.internal.api.PubSub.unsubscribe") as mock_unsubscribe,
        ):
            mock_find.return_value = True
            response = fastapi_client.post(
                "/people/testuser/follows.json",
                data={"publisher": "author1", "state": "1"},
                follow_redirects=False,
            )

        assert response.status_code == 303
        mock_find.assert_called_once_with(username="author1")
        mock_unsubscribe.assert_called_once_with("testuser", "author1")

    def test_post_follows_redirects_to_login_when_unauthenticated(self, fastapi_client):
        response = fastapi_client.post(
            "/people/testuser/follows.json",
            data={"publisher": "author1", "redir_url": "/"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"].startswith("/account/login")

    def test_post_follows_wrong_user_preserves_redir_url(self, fastapi_client, mock_auth_user):
        response = fastapi_client.post(
            "/people/otheruser/follows.json",
            data={"publisher": "author1", "redir_url": "/books/OL1M", "state": "0"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "redir_url=%2Fbooks%2FOL1M" in response.headers["location"]

    def test_post_follows_redirects_to_login_for_wrong_user(self, fastapi_client, mock_auth_user):
        response = fastapi_client.post(
            "/people/otheruser/follows.json",
            data={"publisher": "author1", "redir_url": "/"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"].startswith("/account/login")

    def test_post_follows_nonexistent_publisher_returns_404(self, fastapi_client, mock_auth_user):
        with patch("openlibrary.fastapi.internal.api.accounts.find", return_value=None):
            response = fastapi_client.post(
                "/people/testuser/follows.json",
                data={"publisher": "nonexistent_user", "redir_url": "/", "state": "0"},
            )

        assert response.status_code == 404

    def test_post_follows_follows_redirect_url(self, fastapi_client, mock_auth_user):
        with (
            patch("openlibrary.fastapi.internal.api.accounts.find") as mock_find,
            patch("openlibrary.fastapi.internal.api.PubSub.subscribe"),
        ):
            mock_find.return_value = True
            response = fastapi_client.post(
                "/people/testuser/follows.json",
                data={"publisher": "author1", "redir_url": "/books/OL1M", "state": "0"},
                follow_redirects=False,
            )

        assert response.status_code == 303
        assert response.headers["location"] == "/books/OL1M"
