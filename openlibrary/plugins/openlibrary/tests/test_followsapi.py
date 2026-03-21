from unittest.mock import patch

import pytest
import web

from openlibrary.plugins.openlibrary.api import patrons_follows_json


class FakeUser:
    def __init__(self, key):
        self.key = f"/people/{key}"


def mock_web_input_func(data):
    def _mock_web_input(*args, **kwargs):
        return web.storage(kwargs | data)

    return _mock_web_input


def test_post_follows_nonexistent_publisher_returns_404():
    with (
        patch("web.input") as mock_web_input,
        patch("openlibrary.accounts.get_current_user") as mock_get_current_user,
        patch("openlibrary.accounts.find") as mock_find,
        patch("openlibrary.plugins.openlibrary.api.web.notfound") as mock_notfound,
    ):
        mock_web_input.side_effect = mock_web_input_func({"publisher": "nonexistent_user", "redir_url": "/", "state": "0"})
        mock_get_current_user.return_value = FakeUser("test_user")
        mock_find.return_value = None
        mock_notfound.side_effect = web.HTTPError("404 Not Found")

        with pytest.raises(web.HTTPError):
            patrons_follows_json().POST("/people/test_user")

        mock_notfound.assert_called_once()


def test_post_follows_valid_publisher_succeeds():
    with (
        patch("web.input") as mock_web_input,
        patch("openlibrary.accounts.get_current_user") as mock_get_current_user,
        patch("openlibrary.accounts.find") as mock_find,
        patch("openlibrary.core.follows.PubSub.subscribe") as mock_subscribe,
        patch("openlibrary.plugins.openlibrary.api.web.seeother") as mock_seeother,
    ):
        mock_web_input.side_effect = mock_web_input_func({"publisher": "existing_user", "redir_url": "/", "state": "0"})
        mock_get_current_user.return_value = FakeUser("test_user")
        mock_find.return_value = FakeUser("existing_user")
        mock_seeother.side_effect = web.HTTPError("303 See Other")

        with pytest.raises(web.HTTPError):
            patrons_follows_json().POST("/people/test_user")

        mock_subscribe.assert_called_once()
