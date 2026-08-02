"""Tests for the unified activity stream that backs the social feed."""

from datetime import datetime
from unittest.mock import patch

import pytest

from openlibrary.core.activity import (
    ActivityStream,
    LikeEvent,
    ListEvent,
    RatingEvent,
    ShelfEvent,
    shelf_label,
)

JAN = datetime(2026, 1, 10, 12, 0, 0)
FEB = datetime(2026, 2, 10, 12, 0, 0)
MAR = datetime(2026, 3, 10, 12, 0, 0)


def shelf_row(username="reader", work_id=1, bookshelf_id=1, created=JAN, **extra):
    return {
        "username": username,
        "work_id": work_id,
        "bookshelf_id": bookshelf_id,
        "edition_id": None,
        "private": False,
        "created": created,
        "updated": created,
        **extra,
    }


def rating_row(username="reader", work_id=1, rating=4, created=JAN):
    return {
        "username": username,
        "work_id": work_id,
        "rating": rating,
        "edition_id": None,
        "created": created,
        "updated": created,
    }


class TestShelfLabel:
    @pytest.mark.parametrize(
        ("shelf_id", "expected"),
        [
            (1, "added to Want to Read"),
            (2, "is Currently Reading"),
            (3, "finished reading"),
            (4, "stopped reading"),
        ],
    )
    def test_known_shelves(self, shelf_id, expected):
        assert shelf_label(shelf_id) == expected

    def test_unknown_shelf_falls_back(self):
        # An unrecognised shelf id must not blow up the whole feed.
        assert shelf_label(99) == "logged"


class TestShelfEvent:
    def test_carries_shelf_url_for_the_acting_patron(self):
        event = ShelfEvent.from_row(shelf_row(username="ada", bookshelf_id=2))
        assert event.shelf_url == "/people/ada/books/currently-reading"

    def test_work_key_is_built_from_the_numeric_work_id(self):
        event = ShelfEvent.from_row(shelf_row(work_id=59800))
        assert event.work_key == "/works/OL59800W"

    def test_sorts_by_created(self):
        older = ShelfEvent.from_row(shelf_row(created=JAN))
        newer = ShelfEvent.from_row(shelf_row(created=MAR))
        assert sorted([older, newer], key=lambda e: e.created, reverse=True)[0] is newer


class TestRatingEvent:
    def test_carries_the_star_rating(self):
        event = RatingEvent.from_row(rating_row(rating=5))
        assert event.rating == 5
        assert event.type == "rating"

    def test_rejects_ratings_outside_the_star_range(self):
        # A 0 means "rating cleared", which is not a feed-worthy event.
        assert RatingEvent.from_row(rating_row(rating=0)) is None


class TestActivityStreamPublicFeed:
    def test_merges_sources_newest_first(self):
        shelves = [shelf_row(username="ada", work_id=1, created=JAN)]
        ratings = [rating_row(username="bo", work_id=2, created=MAR)]

        with (
            patch("openlibrary.core.activity.Bookshelves.get_recently_logged_books", return_value=shelves),
            patch("openlibrary.core.activity.Ratings.get_recent_ratings", return_value=ratings),
            patch("openlibrary.core.activity.Likes.get_recent_likes", return_value=[]),
            patch("openlibrary.core.activity.ActivityStream._recent_lists", return_value=[]),
            patch("openlibrary.core.activity.ActivityStream._public_usernames", side_effect=set),
        ):
            events = ActivityStream.public_feed(limit=10)

        assert [e.type for e in events] == ["rating", "shelf_change"]

    def test_excludes_patrons_with_private_reading_logs(self):
        shelves = [
            shelf_row(username="public_patron", work_id=1, created=MAR),
            shelf_row(username="private_patron", work_id=2, created=FEB),
        ]

        with (
            patch("openlibrary.core.activity.Bookshelves.get_recently_logged_books", return_value=shelves),
            patch("openlibrary.core.activity.Ratings.get_recent_ratings", return_value=[]),
            patch("openlibrary.core.activity.Likes.get_recent_likes", return_value=[]),
            patch("openlibrary.core.activity.ActivityStream._recent_lists", return_value=[]),
            patch("openlibrary.core.activity.ActivityStream._public_usernames", return_value={"public_patron"}),
        ):
            events = ActivityStream.public_feed(limit=10)

        assert [e.username for e in events] == ["public_patron"]

    def test_excludes_the_viewers_own_activity(self):
        # Your own shelvings are already all over My Books; seeing them again in
        # the community feed is noise.
        shelves = [
            shelf_row(username="me", work_id=1, created=MAR),
            shelf_row(username="someone_else", work_id=2, created=FEB),
        ]

        with (
            patch("openlibrary.core.activity.Bookshelves.get_recently_logged_books", return_value=shelves),
            patch("openlibrary.core.activity.Ratings.get_recent_ratings", return_value=[]),
            patch("openlibrary.core.activity.Likes.get_recent_likes", return_value=[]),
            patch("openlibrary.core.activity.ActivityStream._recent_lists", return_value=[]),
            patch("openlibrary.core.activity.ActivityStream._public_usernames", side_effect=set),
        ):
            events = ActivityStream.public_feed(viewer="me", limit=10)

        assert [e.username for e in events] == ["someone_else"]

    def test_respects_the_limit_after_merging(self):
        shelves = [shelf_row(username="ada", work_id=i, created=JAN) for i in range(10)]
        ratings = [rating_row(username="bo", work_id=i, created=MAR) for i in range(10)]

        with (
            patch("openlibrary.core.activity.Bookshelves.get_recently_logged_books", return_value=shelves),
            patch("openlibrary.core.activity.Ratings.get_recent_ratings", return_value=ratings),
            patch("openlibrary.core.activity.Likes.get_recent_likes", return_value=[]),
            patch("openlibrary.core.activity.ActivityStream._recent_lists", return_value=[]),
            patch("openlibrary.core.activity.ActivityStream._public_usernames", side_effect=set),
        ):
            events = ActivityStream.public_feed(limit=3)

        assert len(events) == 3

    def test_collapses_a_rating_into_the_matching_shelf_event(self):
        # Rating a book you just marked read is one act, not two feed entries.
        shelves = [shelf_row(username="ada", work_id=7, bookshelf_id=3, created=JAN)]
        ratings = [rating_row(username="ada", work_id=7, rating=5, created=JAN)]

        with (
            patch("openlibrary.core.activity.Bookshelves.get_recently_logged_books", return_value=shelves),
            patch("openlibrary.core.activity.Ratings.get_recent_ratings", return_value=ratings),
            patch("openlibrary.core.activity.Likes.get_recent_likes", return_value=[]),
            patch("openlibrary.core.activity.ActivityStream._recent_lists", return_value=[]),
            patch("openlibrary.core.activity.ActivityStream._public_usernames", side_effect=set),
        ):
            events = ActivityStream.public_feed(limit=10)

        assert len(events) == 1
        assert events[0].type == "shelf_change"
        assert events[0].rating == 5


class TestActivityStreamFollowingFeed:
    def test_returns_nothing_when_following_nobody(self):
        with patch("openlibrary.core.activity.PubSub.get_following", return_value=[]):
            assert ActivityStream.following_feed("lonely") == []

    def test_only_includes_followed_patrons(self):
        following = [{"publisher": "ada"}, {"publisher": "bo"}]
        shelves = [
            shelf_row(username="ada", work_id=1, created=MAR),
            shelf_row(username="stranger", work_id=2, created=FEB),
        ]

        with (
            patch("openlibrary.core.activity.PubSub.get_following", return_value=following),
            patch("openlibrary.core.activity.ActivityStream._shelf_rows_for", return_value=shelves),
            patch("openlibrary.core.activity.Ratings.get_recent_ratings", return_value=[]),
            patch("openlibrary.core.activity.Likes.get_recent_likes", return_value=[]),
            patch("openlibrary.core.activity.ActivityStream._recent_lists", return_value=[]),
        ):
            events = ActivityStream.following_feed("viewer", limit=10)

        assert [e.username for e in events] == ["ada"]

    def test_does_not_filter_followed_patrons_by_public_readlog(self):
        # Following is consent enough -- a private reading log still reaches the
        # people the patron chose to publish to.
        following = [{"publisher": "ada"}]
        shelves = [shelf_row(username="ada", work_id=1, created=MAR)]

        with (
            patch("openlibrary.core.activity.PubSub.get_following", return_value=following),
            patch("openlibrary.core.activity.ActivityStream._shelf_rows_for", return_value=shelves),
            patch("openlibrary.core.activity.Ratings.get_recent_ratings", return_value=[]),
            patch("openlibrary.core.activity.Likes.get_recent_likes", return_value=[]),
            patch("openlibrary.core.activity.ActivityStream._recent_lists", return_value=[]),
            patch("openlibrary.core.activity.ActivityStream._public_usernames", return_value=set()) as public_mock,
        ):
            events = ActivityStream.following_feed("viewer", limit=10)

        assert [e.username for e in events] == ["ada"]
        public_mock.assert_not_called()


class TestLikeEvent:
    def test_builds_from_a_liked_list_key(self):
        event = LikeEvent.from_row({"username": "ada", "key": "/people/bo/lists/OL1L", "value": 1, "created": JAN})
        assert event.type == "like"
        assert event.liked_key == "/people/bo/lists/OL1L"

    def test_ignores_dislikes(self):
        # "Someone disliked this" is not worth broadcasting.
        assert LikeEvent.from_row({"username": "ada", "key": "/people/bo/lists/OL1L", "value": -1, "created": JAN}) is None

    def test_a_liked_work_key_becomes_a_work_event(self):
        # `likes.key` is a generic Infogami key, so it may point at a work.
        event = LikeEvent.from_row({"username": "ada", "key": "/works/OL59800W", "value": 1, "created": JAN})
        assert event.work_id == 59800
        assert event.work_key == "/works/OL59800W"

    def test_an_unrecognised_key_is_dropped(self):
        assert LikeEvent.from_row({"username": "ada", "key": "/authors/OL1A", "value": 1, "created": JAN}) is None


class TestActivityStreamIncludesLikes:
    def test_likes_join_the_public_feed(self):
        likes = [{"username": "ada", "key": "/people/bo/lists/OL1L", "value": 1, "created": MAR}]

        with (
            patch("openlibrary.core.activity.Bookshelves.get_recently_logged_books", return_value=[]),
            patch("openlibrary.core.activity.Ratings.get_recent_ratings", return_value=[]),
            patch("openlibrary.core.activity.Likes.get_recent_likes", return_value=likes),
            patch("openlibrary.core.activity.ActivityStream._recent_lists", return_value=[]),
            patch("openlibrary.core.activity.ActivityStream._public_usernames", side_effect=set),
        ):
            events = ActivityStream.public_feed(limit=10)

        assert [e.type for e in events] == ["like"]


class TestListEvent:
    def test_builds_from_a_list_thing(self):
        event = ListEvent(
            username="ada",
            created=JAN,
            list_key="/people/ada/lists/OL1L",
            name="Books that rewired my brain",
            book_count=4,
            cover_ids=[1, 2, 3],
        )
        assert event.type == "list_update"
        assert event.list_url == "/people/ada/lists/OL1L"
