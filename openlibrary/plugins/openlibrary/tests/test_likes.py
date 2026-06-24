from unittest.mock import MagicMock, patch

import pytest
import web

from openlibrary.core.likes import Likes
from openlibrary.plugins.openlibrary.tests.test_followsapi import FakeUser
from openlibrary.plugins.upstream.likes import likes_control


def test_like():
    with (
        patch("web.data", return_value=b'{"key": "/works/OL1W", "value": 1}'),
        patch("web.ctx") as mock_ctx,
        patch("openlibrary.core.likes.Likes.like") as mock_likes,
    ):
        mock_ctx.site.get_user.return_value = FakeUser("test_user")
        likes_control().POST()
        mock_likes.assert_called_once_with("test_user", "/works/OL1W", 1)


def test_unlike():
    with (
        patch("web.data", return_value=b'{"key": "/works/OL1W"}'),
        patch("web.ctx") as mock_ctx,
        patch("openlibrary.core.likes.Likes.unlike") as mock_unlike,
    ):
        mock_ctx.site.get_user.return_value = FakeUser("test_user")

        likes_control().DELETE()

        mock_unlike.assert_called_once_with("test_user", "/works/OL1W")


def test_double_like():
    with (
        patch("openlibrary.core.likes.db.get_db") as mock_get_db,
        patch.object(Likes, "patron_liked", side_effect=[False, True]),
    ):
        oldb = MagicMock()
        mock_get_db.return_value = oldb

        Likes.like("user1", "/works/OL1W", 1)
        Likes.like("user1", "/works/OL1W", 1)

        assert oldb.insert.call_count == 1
        assert oldb.update.call_count == 1


def test_like_invalid_value():
    with pytest.raises(ValueError):
        Likes.like("user1", "/works/OL1W", 99)


def test_like_unauthenticated():
    with (
        patch("web.data", return_value=b'{"key": "/works/OL1W", "value": 1}'),
        patch("web.ctx") as mock_ctx,
    ):
        mock_ctx.site.get_user.return_value = None

        with pytest.raises(web.HTTPError):
            likes_control().POST()
