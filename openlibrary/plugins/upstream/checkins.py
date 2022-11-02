"""Reading log check-ins handler and services.
"""
import json
import web

from typing import Optional

from infogami.utils import delegate

from openlibrary.accounts import get_current_user
from openlibrary.utils import extract_numeric_id_from_olid
from openlibrary.core.bookshelves_events import BookshelvesEvents
from openlibrary.utils.decorators import authorized_for


def make_date_string(year: int, month: Optional[int], day: Optional[int]) -> str:
    """Creates a date string in the expected format, given the year, month, and day.

    Event dates can take one of three forms:
    "YYYY"
    "YYYY-MM"
    "YYYY-MM-DD"
    """
    result = f'{year}'
    if month:
        result += f'-{month:02}'
        if day:
            result += f'-{day:02}'
    return result


def is_valid_date(day, month, year):
    """Validates dates.

    Dates are considered valid if there is:
    1. A year
    2. A year and a month
    3. A year, month, and day
    """
    if not year:
        return False
    if day and not month:
        return False
    return True


class patron_check_ins(delegate.page):
    path = r'/works/OL(\d+)W/check-ins'
    encoding = 'json'

    @authorized_for('/usergroup/beta-testers')
    def POST(self, work_id):
        data = json.loads(web.data())

        if not self.validate_data(data):
            raise web.badrequest('Invalid date submitted')

        user = get_current_user()
        username = user['key'].split('/')[-1]

        edition_key = data.get('edition_key', None)
        edition_id = extract_numeric_id_from_olid(edition_key) if edition_key else None

        event_type = data.get('event_type')

        date_str = make_date_string(
            data.get('year', None),
            data.get('month', None),
            data.get('day', None),
        )

        BookshelvesEvents.create_event(
            username, work_id, edition_id, date_str, event_type=event_type
        )

        return delegate.RawText(json.dumps({'status': 'ok'}))

    def validate_data(self, data):
        """Validates data submitted from check-in dialog."""

        # Event type must exist:
        if 'event_type' not in data:
            return False

        # Date must be valid:
        if not is_valid_date(
            data.get('day', None),
            data.get('month', None),
            data.get('year', None),
        ):
            return False

        return True


def setup():
    pass
