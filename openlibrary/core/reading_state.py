"""
A reader's shelf, rating and last finish date for a batch of works, in one
query per table: the opening state for `<ol-shelf-button>`.
"""

from __future__ import annotations

from typing import TypedDict

from openlibrary.core.bookshelves import Bookshelves
from openlibrary.core.bookshelves_events import BookshelfEvent, BookshelvesEvents
from openlibrary.core.ratings import Ratings


class ReadingState(TypedDict):
    shelf: int | None
    rating: int | None
    read_date: str | None
    event_id: int | None


def get_reading_state(username: str, work_ids: list[int]) -> dict[int, ReadingState]:
    """Every requested work is present, with `None` where the reader has no state."""
    if not work_ids:
        return {}
    shelves = {row.work_id: row.bookshelf_id for row in Bookshelves.get_users_read_status_of_works(username, work_ids)}
    ratings = Ratings.get_users_ratings_of_works(username, work_ids)
    finishes = BookshelvesEvents.get_latest_event_dates(username, work_ids, BookshelfEvent.FINISH)
    return {
        work_id: {
            "shelf": shelves.get(work_id),
            "rating": ratings.get(work_id),
            "read_date": finishes[work_id]["event_date"] if work_id in finishes else None,
            "event_id": finishes[work_id]["id"] if work_id in finishes else None,
        }
        for work_id in work_ids
    }
