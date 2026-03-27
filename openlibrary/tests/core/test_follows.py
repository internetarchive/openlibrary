from unittest.mock import MagicMock, patch

import web

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


def _make_pref(username, public):
    """Build a mock preferences object like web.ctx.site.get_many returns."""
    p = MagicMock()
    p.key = f'/people/{username}/preferences'
    p.dict.return_value = {
        'notifications': {'public_readlog': 'yes' if public else 'no'}
    }
    return p


def _make_subscriptions(publishers):
    """Simulate get_following() return value for a list of publisher usernames."""
    return [{'publisher': u, 'subscriber': 'alice', 'disabled': False} for u in publishers]


class TestGetFeedPrivacy:
    @classmethod
    def setup_class(cls):
        web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
        get_db().query(READING_LOG_DDL)

    def setup_method(self):
        self.db = get_db()
        self.db.insert("bookshelves_books", username="bob", work_id=1, bookshelf_id=1)
        self.db.insert("bookshelves_books", username="carol", work_id=2, bookshelf_id=1)

    def teardown_method(self):
        self.db.query("delete from bookshelves_books;")

    def test_get_feed_excludes_private_readlog(self):
        """Publishers with private reading logs must not appear in the feed."""
        prefs = [_make_pref("bob", public=True), _make_pref("carol", public=False)]

        with patch.object(PubSub, 'get_following', return_value=_make_subscriptions(["bob", "carol"])):
            with patch("openlibrary.core.follows.web") as mock_web:
                with patch("openlibrary.core.follows.Bookshelves.add_solr_works"):
                    mock_web.ctx.site.get_many.return_value = prefs
                    feed = PubSub.get_feed("alice")

        usernames = [r.username for r in feed]
        assert "bob" in usernames
        assert "carol" not in usernames

    def test_get_feed_includes_public_readlog(self):
        """Publishers with public reading logs should appear in the feed."""
        prefs = [_make_pref("bob", public=True), _make_pref("carol", public=True)]

        with patch.object(PubSub, 'get_following', return_value=_make_subscriptions(["bob", "carol"])):
            with patch("openlibrary.core.follows.web") as mock_web:
                with patch("openlibrary.core.follows.Bookshelves.add_solr_works"):
                    mock_web.ctx.site.get_many.return_value = prefs
                    feed = PubSub.get_feed("alice")

        usernames = [r.username for r in feed]
        assert "bob" in usernames
        assert "carol" in usernames

    def test_get_feed_all_private_returns_empty(self):
        """If all followed publishers have private logs, feed should be empty."""
        prefs = [_make_pref("bob", public=False), _make_pref("carol", public=False)]

        with patch.object(PubSub, 'get_following', return_value=_make_subscriptions(["bob", "carol"])):
            with patch("openlibrary.core.follows.web") as mock_web:
                mock_web.ctx.site.get_many.return_value = prefs
                feed = PubSub.get_feed("alice")

        assert feed == []

    def test_get_feed_no_subscriptions_returns_empty(self):
        """No subscriptions should return an empty feed without querying bookshelves."""
        with patch.object(PubSub, 'get_following', return_value=[]):
            feed = PubSub.get_feed("nobody")

        assert feed == []
