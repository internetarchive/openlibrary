import json
import re
from unittest.mock import MagicMock, patch

import pytest
import web

from openlibrary.core.likes import Likes
from openlibrary.plugins.upstream.likes import get_likes_record, get_patron_likes, likes_control


class FakeUser:
    def __init__(self, key):
        self.key = f"/people/{key}"


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
    # `create=True` -- see test_patron_likes_unauthenticated below for why.
    with patch("web.data", return_value=b'{"key": "/works/OL1W", "value": 1}'), patch.object(web.ctx, "site", create=True) as mock_site:
        mock_site.get_user.return_value = None
        web.ctx.headers = []
        with pytest.raises(web.HTTPError):
            likes_control().POST()


def test_unlike_unauthenticated():
    with patch("web.data", return_value=b'{"key": "/works/OL1W"}'), patch.object(web.ctx, "site", create=True) as mock_site:
        mock_site.get_user.return_value = None
        web.ctx.headers = []
        with pytest.raises(web.HTTPError):
            likes_control().DELETE()


def test_like_missing_key():
    with patch("web.data", return_value=b'{"value": 1}'), patch("web.ctx") as mock_ctx:
        mock_ctx.site.get_user.return_value = FakeUser("test_user")
        with pytest.raises(web.HTTPError):
            likes_control().POST()


def test_unlike_missing_key():
    with patch("web.data", return_value=b"{}"), patch("web.ctx") as mock_ctx:
        mock_ctx.site.get_user.return_value = FakeUser("test_user")
        with pytest.raises(web.HTTPError):
            likes_control().DELETE()


def test_get_likes_record_missing_key():
    with patch("web.input", return_value=web.storage(key="")), pytest.raises(web.HTTPError):
        get_likes_record().GET()


def test_get_likes_record_anonymous():
    with (
        patch("web.input", return_value=web.storage(key="/works/OL1W")),
        patch("web.ctx") as mock_ctx,
        patch("openlibrary.core.likes.Likes.get_count", return_value={"likes": 3, "dislikes": 1}),
    ):
        mock_ctx.site.get_user.return_value = None
        result = get_likes_record().GET()
        assert json.loads(result.rawtext) == {"likes": 3, "dislikes": 1, "patron_liked": False}


def test_get_likes_record_authenticated():
    with (
        patch("web.input", return_value=web.storage(key="/works/OL1W")),
        patch("web.ctx") as mock_ctx,
        patch("openlibrary.core.likes.Likes.get_count", return_value={"likes": 3, "dislikes": 1}),
        patch("openlibrary.core.likes.Likes.patron_liked", return_value=True),
    ):
        mock_ctx.site.get_user.return_value = FakeUser("test_user")
        result = get_likes_record().GET()
        assert json.loads(result.rawtext) == {"likes": 3, "dislikes": 1, "patron_liked": True}


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


def test_patron_likes_invalid_limit():
    with (
        patch("web.input", return_value=web.storage(limit="not-a-number", offset=0)),
        patch("web.ctx") as mock_ctx,
    ):
        mock_ctx.site.get_user.return_value = FakeUser("test_user")
        with pytest.raises(web.HTTPError):
            get_patron_likes().GET()


def test_patron_likes_negative_offset():
    with (
        patch("web.input", return_value=web.storage(limit=50, offset=-1)),
        patch("web.ctx") as mock_ctx,
    ):
        mock_ctx.site.get_user.return_value = FakeUser("test_user")
        with pytest.raises(web.HTTPError):
            get_patron_likes().GET()


def test_patron_likes_limit_is_capped():
    with (
        patch("web.input", return_value=web.storage(limit=100_000, offset=0)),
        patch("web.ctx") as mock_ctx,
        patch("openlibrary.core.likes.Likes.get_for_patron", return_value=[]) as mock_get_for_patron,
    ):
        mock_ctx.site.get_user.return_value = FakeUser("test_user")

        get_patron_likes().GET()

        mock_get_for_patron.assert_called_once_with("test_user", get_patron_likes.MAX_LIMIT, 0)


def test_get_count():
    with patch("openlibrary.core.likes.db.get_db") as mock_get_db:
        oldb = MagicMock()
        oldb.query.side_effect = [
            [{"value": 1, "count": 3}],
            [{"value": -1, "count": 1}],
        ]
        mock_get_db.return_value = oldb

        assert Likes.get_count("/works/OL1W") == {"likes": 3, "dislikes": 1}


def test_get_count_no_likes():
    with patch("openlibrary.core.likes.db.get_db") as mock_get_db:
        oldb = MagicMock()
        oldb.query.return_value = []
        mock_get_db.return_value = oldb

        assert Likes.get_count("/works/OL1W") == {"likes": 0, "dislikes": 0}
