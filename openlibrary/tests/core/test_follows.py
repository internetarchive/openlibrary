from unittest.mock import MagicMock, patch

import web

from openlibrary.core import db as ol_db
from openlibrary.core.db import get_db
from openlibrary.core.follows import PubSub

READING_LOG_DDL = """
CREATE TABLE bookshelves_books (
    username text NOT NULL,
    work_id integer NOT NULL,
    bookshelf_id integer NOT NULL,
    edition_id integer default null,
    created timestamp default current_timestamp,
    primary key (username, work_id, bookshelf_id)
);
"""


def _make_user(username, public):
    """Build a mock User object whose .preferences() returns the real stored shape."""
    u = MagicMock()
    u.preferences.return_value = {"public_readlog": "yes" if public else "no"}
    return u


def _make_subscriptions(publishers):
    """Simulate get_following() return value for a list of publisher usernames."""
    return [{"publisher": u, "subscriber": "alice", "disabled": False} for u in publishers]


class TestGetFeedPrivacy:
    @classmethod
    def setup_class(cls):
        ol_db._get_db.cache_clear()
        web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
        get_db().query(READING_LOG_DDL)

    @classmethod
    def teardown_class(cls):
        ol_db._get_db.cache_clear()

    def setup_method(self):
        self.db = get_db()
        self.db.insert("bookshelves_books", username="bob", work_id=1, bookshelf_id=1)
        self.db.insert("bookshelves_books", username="carol", work_id=2, bookshelf_id=1)

    def teardown_method(self):
        self.db.query("delete from bookshelves_books;")

    def _site_get(self, user_map):
        """Return a side_effect function for web.ctx.site.get() keyed by username."""

        def _get(path):
            username = path.split("/")[-1]
            return user_map.get(username)

        return _get

    def test_get_feed_excludes_private_readlog(self):
        """Publishers with private reading logs must not appear in the feed."""
        user_map = {"bob": _make_user("bob", public=True), "carol": _make_user("carol", public=False)}

        with (
            patch.object(PubSub, "get_following", return_value=_make_subscriptions(["bob", "carol"])),
            patch("openlibrary.core.follows.web") as mock_web,
            patch("openlibrary.core.follows.Bookshelves.add_solr_works"),
        ):
            mock_web.ctx.site.get.side_effect = self._site_get(user_map)
            feed = PubSub.get_feed("alice")

        usernames = [r.username for r in feed]
        assert "bob" in usernames
        assert "carol" not in usernames

    def test_get_feed_includes_public_readlog(self):
        """Publishers with public reading logs should appear in the feed."""
        user_map = {"bob": _make_user("bob", public=True), "carol": _make_user("carol", public=True)}

        with (
            patch.object(PubSub, "get_following", return_value=_make_subscriptions(["bob", "carol"])),
            patch("openlibrary.core.follows.web") as mock_web,
            patch("openlibrary.core.follows.Bookshelves.add_solr_works"),
        ):
            mock_web.ctx.site.get.side_effect = self._site_get(user_map)
            feed = PubSub.get_feed("alice")

        usernames = [r.username for r in feed]
        assert "bob" in usernames
        assert "carol" in usernames

    def test_get_feed_all_private_returns_empty(self):
        """If all followed publishers have private logs, feed should be empty."""
        user_map = {"bob": _make_user("bob", public=False), "carol": _make_user("carol", public=False)}

        with patch.object(PubSub, "get_following", return_value=_make_subscriptions(["bob", "carol"])), patch("openlibrary.core.follows.web") as mock_web:
            mock_web.ctx.site.get.side_effect = self._site_get(user_map)
            feed = PubSub.get_feed("alice")

        assert feed == []

    def test_get_feed_no_subscriptions_returns_empty(self):
        """No subscriptions should return an empty feed without querying bookshelves."""
        with patch.object(PubSub, "get_following", return_value=[]):
            feed = PubSub.get_feed("nobody")

        assert feed == []
