import re
from unittest.mock import MagicMock, patch

import pytest
import web

from openlibrary.core.likes import Likes
from openlibrary.plugins.openlibrary.tests.test_followsapi import FakeUser
from openlibrary.plugins.upstream.likes import get_patron_likes, likes_control


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
    with pytest.raises(ValueError, match=re.escape("value must be 1 (like) or -1 (dislike)")):
        Likes.like("user1", "/works/OL1W", 99)


def test_like_unauthenticated():
    with patch("web.data", return_value=b'{"key": "/works/OL1W", "value": 1}'), patch.object(web.ctx, "site") as mock_site:
        mock_site.get_user.return_value = None
        web.ctx.headers = []
        with pytest.raises(web.HTTPError):
            likes_control().POST()


def test_patron_likes_unauthenticated():
    # `create=True` avoids a test-isolation gap in this file's other tests:
    # `web.ctx` may not have a `site` attribute yet until something in the
    # broader suite sets it as a side effect, which makes plain
    # `patch.object(web.ctx, "site")` (no `create=True`) fail before this test
    # even runs, depending on execution order.
    with patch.object(web.ctx, "site", create=True) as mock_site:
        mock_site.get_user.return_value = None
        web.ctx.headers = []
        with pytest.raises(web.HTTPError):
            get_patron_likes().GET()


def test_patron_likes_ignores_username_param_and_uses_caller_identity():
    # A patron must only ever be able to fetch their own likes -- the endpoint
    # must not accept an arbitrary `username` to look up another patron's likes.
    with (
        patch("web.input", return_value=web.storage(username="someone_else", limit=50, offset=0)),
        patch("web.ctx") as mock_ctx,
        patch("openlibrary.core.likes.Likes.get_for_patron", return_value=[]) as mock_get_for_patron,
    ):
        mock_ctx.site.get_user.return_value = FakeUser("test_user")

        get_patron_likes().GET()

        mock_get_for_patron.assert_called_once_with("test_user", 50, 0)
