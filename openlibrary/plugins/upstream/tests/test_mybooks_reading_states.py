"""Tests for the batched reading state behind `<ol-shelf-button>`.

The point of the helper is that a page of results costs three queries instead of
two per result, so what matters is that it asks once with every id and folds the
three answers back onto the right work.
"""

from unittest.mock import patch

import web

from openlibrary.plugins.upstream.mybooks import get_patrons_reading_states

MODULE = "openlibrary.plugins.upstream.mybooks"


def _patches(shelves=None, ratings=None, check_ins=None):
    return (
        patch(f"{MODULE}.accounts.get_current_user", return_value=web.storage(key="/people/tester")),
        patch(f"{MODULE}.Bookshelves.get_users_read_status_of_works", return_value=shelves or []),
        patch(f"{MODULE}.Ratings.get_users_ratings_of_works", return_value=ratings or {}),
        patch(f"{MODULE}.BookshelvesEvents.get_latest_event_dates_for_works", return_value=check_ins or {}),
    )


def _run(work_keys, **kwargs):
    user, shelves, ratings, check_ins = _patches(**kwargs)
    with user, shelves as s, ratings as r, check_ins as c:
        return get_patrons_reading_states(work_keys), (s, r, c)


class TestGetPatronsReadingStates:
    def test_signed_out_asks_for_nothing(self):
        with patch(f"{MODULE}.accounts.get_current_user", return_value=None):
            assert get_patrons_reading_states(["/works/OL1W"]) == {}

    def test_no_works_asks_for_nothing(self):
        with patch(f"{MODULE}.accounts.get_current_user", return_value=web.storage(key="/people/tester")):
            assert get_patrons_reading_states([]) == {}

    def test_one_batched_call_per_source(self):
        _, (shelves, ratings, check_ins) = _run(["/works/OL1W", "/works/OL2W"])
        shelves.assert_called_once_with("tester", [1, 2])
        ratings.assert_called_once_with("tester", [1, 2])
        assert check_ins.call_args[0][:2] == ("tester", [1, 2])

    def test_folds_all_three_onto_the_right_work(self):
        states, _ = _run(
            ["/works/OL1W", "/works/OL2W", "/works/OL3W"],
            shelves=[web.storage(work_id=1, bookshelf_id=3)],
            ratings={2: 5},
            check_ins={1: {"id": 7, "event_date": "2026-05-01"}},
        )
        assert states["/works/OL1W"] == {
            "shelf": 3,
            "rating": None,
            "last_read_date": "2026-05-01",
            "event_id": 7,
        }
        assert states["/works/OL2W"]["rating"] == 5
        assert states["/works/OL2W"]["last_read_date"] is None

    def test_works_with_no_state_are_left_out(self):
        states, _ = _run(
            ["/works/OL1W", "/works/OL2W"],
            shelves=[web.storage(work_id=1, bookshelf_id=1)],
        )
        assert "/works/OL2W" not in states

    def test_a_check_in_alone_is_state_enough(self):
        # The prompt still has a date to show even when the book sits on no
        # shelf and is unrated, so the work has to survive the filter.
        states, _ = _run(
            ["/works/OL1W"],
            check_ins={1: {"id": 7, "event_date": "2026-05-01"}},
        )
        assert states["/works/OL1W"]["last_read_date"] == "2026-05-01"
