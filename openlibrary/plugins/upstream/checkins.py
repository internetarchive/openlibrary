"""Reading log check-ins handler and services."""

from infogami.utils.view import public
from openlibrary.accounts import get_current_user
from openlibrary.core.bookshelves_events import BookshelfEvent, BookshelvesEvents
from openlibrary.utils import extract_numeric_id_from_olid


def make_date_string(year: int, month: int | None, day: int | None) -> str:
    """Creates a date string in the expected format, given the year, month, and day.

    Event dates can take one of three forms:
    "YYYY"
    "YYYY-MM"
    "YYYY-MM-DD"
    """
    result = f"{year}"
    if month:
        result += f"-{month:02}"
        if day:
            result += f"-{day:02}"
    return result


def is_valid_date(year: int, month: int | None, day: int | None) -> bool:
    """Validates dates.

    Dates are considered valid if there is:
    1. A year only.
    2. A year and a month only.
    3. A year, month, and day.
    """
    if not year:
        return False

    return not day or bool(month)


@public
def get_latest_read_date(work_olid: str) -> dict | None:
    user = get_current_user()
    if not user:
        return None

    username = user["key"].split("/")[-1]

    work_id = extract_numeric_id_from_olid(work_olid)

    result = BookshelvesEvents.get_latest_event_date(username, work_id, BookshelfEvent.FINISH)
    return result


def setup():
    pass
