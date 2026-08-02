"""Tests for the unified activity stream that backs the social feed."""

from datetime import datetime
from unittest.mock import patch

import pytest

from openlibrary.core.activity import (
    ActivityStream,
    ListAddEvent,
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
            patch("openlibrary.core.activity.ActivityStream._recent_list_adds", return_value=[]),
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
            patch("openlibrary.core.activity.ActivityStream._recent_list_adds", return_value=[]),
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
            patch("openlibrary.core.activity.ActivityStream._recent_list_adds", return_value=[]),
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
            patch("openlibrary.core.activity.ActivityStream._recent_list_adds", return_value=[]),
            patch("openlibrary.core.activity.ActivityStream._public_usernames", side_effect=set),
        ):
            events = ActivityStream.public_feed(limit=3)

        assert len(events) == 3

    def test_a_rating_is_its_own_card_not_folded_into_the_shelving(self):
        # Shelving and rating are two of the three card types, so a patron who
        # does both produces two cards.
        shelves = [shelf_row(username="ada", work_id=7, bookshelf_id=3, created=JAN)]
        ratings = [rating_row(username="ada", work_id=7, rating=5, created=JAN)]

        with (
            patch("openlibrary.core.activity.Bookshelves.get_recently_logged_books", return_value=shelves),
            patch("openlibrary.core.activity.Ratings.get_recent_ratings", return_value=ratings),
            patch("openlibrary.core.activity.ActivityStream._recent_list_adds", return_value=[]),
            patch("openlibrary.core.activity.ActivityStream._public_usernames", side_effect=set),
        ):
            events = ActivityStream.public_feed(limit=10)

        assert sorted(e.type for e in events) == ["rating", "shelf_change"]
        assert next(e for e in events if e.type == "rating").rating == 5
        assert next(e for e in events if e.type == "shelf_change").rating is None


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
            patch("openlibrary.core.activity.ActivityStream._recent_list_adds", return_value=[]),
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
            patch("openlibrary.core.activity.ActivityStream._recent_list_adds", return_value=[]),
            patch("openlibrary.core.activity.ActivityStream._public_usernames", return_value=set()) as public_mock,
        ):
            events = ActivityStream.following_feed("viewer", limit=10)

        assert [e.username for e in events] == ["ada"]
        public_mock.assert_not_called()


class TestListAddEvent:
    """Card three: a patron added a book to one of their lists."""

    def test_carries_both_the_book_and_the_list(self):
        event = ListAddEvent(
            username="ada",
            created=JAN,
            work_id=59800,
            work_key="/works/OL59800W",
            list_key="/people/ada/lists/OL1L",
            name="Books that rewired my brain",
            book_count=4,
            cover_ids=[1, 2, 3],
        )
        assert event.type == "list_add"
        # The book is the subject, so it enriches from Solr like any other card.
        assert event.work_id == 59800
        assert event.list_url == "/people/ada/lists/OL1L"

    def test_the_newest_seed_is_the_one_that_was_just_added(self):
        # `List.add_seed` appends, so the tail of `seeds` is the latest add.
        seeds = [{"key": "/works/OL1W"}, {"key": "/works/OL2W"}, {"key": "/works/OL3W"}]
        assert ActivityStream._newest_work_seed(seeds) == 3

    def test_non_work_seeds_are_skipped(self):
        seeds = [{"key": "/works/OL7W"}, "subject:love", {"key": "/authors/OL1A"}]
        assert ActivityStream._newest_work_seed(seeds) == 7

    def test_a_list_with_no_book_seeds_yields_nothing(self):
        assert ActivityStream._newest_work_seed(["subject:love"]) is None
        assert ActivityStream._newest_work_seed([]) is None


class TestBalancedSample:
    """The design gallery needs every card type visible in every variant."""

    def _events(self):
        return (
            [ShelfEvent.from_row(shelf_row(work_id=i, created=MAR)) for i in range(8)]
            + [RatingEvent.from_row(rating_row(work_id=i, created=FEB)) for i in range(8)]
            + [ListAddEvent(username="ada", created=JAN, work_id=99, work_key="/works/OL99W", list_key="/people/ada/lists/OL1L", name="L", book_count=1)]
        )

    def test_every_type_survives_a_small_limit(self):
        # Newest-first would return eight shelvings and nothing else.
        picked = ActivityStream.balance(self._events(), limit=4)
        assert {e.type for e in picked} == {"shelf_change", "rating", "list_add"}
        assert len(picked) == 4

    def test_order_stays_newest_first_within_the_sample(self):
        picked = ActivityStream.balance(self._events(), limit=6)
        assert picked == sorted(picked, key=lambda e: e.created, reverse=True)

    def test_a_limit_larger_than_the_input_returns_everything(self):
        events = self._events()
        assert len(ActivityStream.balance(events, limit=100)) == len(events)
