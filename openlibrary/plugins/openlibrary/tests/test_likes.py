import json
import re
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import web

from openlibrary.core.likes import Likes
from openlibrary.plugins.upstream.likes import get_likes_record, get_patron_likes, likes_control


class FakeUser:
    def __init__(self, key):
        self.key = f"/people/{key}"


LIKES_DDL = """
CREATE TABLE likes (
    username TEXT NOT NULL,
    key TEXT NOT NULL,
    value SMALLINT NOT NULL DEFAULT 1 CHECK (value IN (1, -1)),
    created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (username, key)
);
"""


@pytest.fixture
def likes_db(monkeypatch):
    oldb = web.database(dbn="sqlite", db=":memory:")
    oldb.query(LIKES_DDL)
    monkeypatch.setattr("openlibrary.core.likes.db.get_db", lambda: oldb)
    yield oldb
    oldb.ctx.db.close()


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


def test_unlike_deletes_only_that_row(likes_db):
    key = "/people/user1/lists/OL1L"
    other_key = "/people/user1/lists/OL2L"
    Likes.like("user1", key)
    Likes.like("user2", key)
    Likes.like("user1", other_key)

    Likes.unlike("user1", key)
    Likes.unlike("user1", key)

    remaining = {(row.username, row.key) for row in likes_db.select("likes")}
    assert remaining == {("user2", key), ("user1", other_key)}


@pytest.mark.parametrize(("first_value", "second_value"), [(1, 1), (1, -1), (-1, 1), (-1, -1)])
def test_double_like(likes_db, first_value, second_value):
    key = "/people/user1/lists/OL1L"
    assert Likes.like("user1", key, first_value) is None
    first = next(iter(likes_db.select("likes")))
    assert first.value == first_value
    assert first.created == first.modified

    original_time = datetime(2000, 1, 1)
    likes_db.update("likes", where="username=$username AND key=$key", vars={"username": "user1", "key": key}, created=original_time, modified=original_time)

    assert Likes.like("user1", key, second_value) is None

    rows = list(likes_db.select("likes"))
    assert len(rows) == 1
    assert rows[0].username == "user1"
    assert rows[0].key == key
    assert rows[0].value == second_value
    assert rows[0].created == original_time
    assert rows[0].modified > original_time


@pytest.mark.parametrize("value", [0, 2, -2, 99])
def test_like_invalid_value(value):
    with (
        patch("openlibrary.core.likes.db.get_db") as mock_get_db,
        pytest.raises(ValueError, match=re.escape("value must be 1 (like) or -1 (dislike)")),
    ):
        Likes.like("user1", "/works/OL1W", value)
    mock_get_db.assert_not_called()


def test_like_leaves_other_users_and_keys_untouched(likes_db):
    key = "/people/user1/lists/OL1L"
    other_key = "/people/user1/lists/OL2L"
    Likes.like("user1", key)
    Likes.like("user2", key)
    Likes.like("user1", other_key)
    before = {(row.username, row.key): dict(row) for row in likes_db.select("likes")}

    Likes.dislike("user1", key)

    after = {(row.username, row.key): dict(row) for row in likes_db.select("likes")}
    assert len(after) == 3
    assert after["user1", key]["value"] == -1
    assert after["user2", key] == before["user2", key]
    assert after["user1", other_key] == before["user1", other_key]


def test_like_endpoint_saves_latest_value(likes_db):
    key = "/people/user1/lists/OL1L"
    with patch("web.ctx") as mock_ctx:
        mock_ctx.site.get_user.return_value = FakeUser("user1")
        for value in [1, 1, -1, 1]:
            with patch("web.data", return_value=json.dumps({"key": key, "value": value}).encode()):
                assert json.loads(likes_control().POST().rawtext) == {"key": key, "value": value}
            rows = list(likes_db.select("likes"))
            assert len(rows) == 1
            assert (rows[0].username, rows[0].key, rows[0].value) == ("user1", key, value)


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
