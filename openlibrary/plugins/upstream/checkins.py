"""Reading log check-ins handler and services.
"""
import json
import web

from typing import Optional

from infogami.utils import delegate
from infogami.utils.view import render_template

from openlibrary.accounts import get_current_user
from openlibrary.utils import extract_numeric_id_from_olid
from openlibrary.core.bookshelves_events import BookshelvesEvents
from openlibrary.utils.decorators import authorized_for


class check_ins(delegate.page):
    path = r'/check-ins/OL(\d+)W'

    def GET(self, work_id):
        pass

    @authorized_for('/usergroup/beta-testers', '/usergroup/admin')
    def POST(self, work_id):
        """Creates a check-in for the given work.

        Additional data is expected to be sent as JSON in the body, and will
        have the following keys:
        edition_olid : str,
        event_type : str,
        year : integer,
        month : integer [optional],
        day : integer [optional]
        """
        data = json.loads(web.data())
        valid_request = self.is_valid(data)
        user = get_current_user()
        username = user['key'].split('/')[-1]

        if valid_request and username:
            edition_id = extract_numeric_id_from_olid(data['edition_olid'])
            date_str = self.make_date_string(
                data['year'], data.get('month', None), data.get('day', None)
            )
            event_type = BookshelvesEvents.EVENT_TYPES[data['event_type']]
            BookshelvesEvents.create_event(
                username, work_id, edition_id, date_str, event_type=event_type
            )
        else:
            return web.badrequest(message="Invalid request")
        return delegate.RawText(json.dumps({'status': 'ok'}))

    def is_valid(self, data: dict) -> bool:
        """Validates POSTed check-in data."""
        if not all(key in data for key in ('edition_olid', 'year', 'event_type')):
            return False
        if data['event_type'] not in BookshelvesEvents.EVENT_TYPES:
            return False
        return True

    def make_date_string(
        self, year: int, month: Optional[int], day: Optional[int]
    ) -> str:
        """Creates a date string in 'YYYY-MM-DD' format, given the year, month, and day.

        Month and day can be None.  If the month is None, only the year is returned.
        If there is a month but day is None, the year and month are returned.

        >>> check_ins.make_date_string(1999, 12, 22)
        '1999-12-22'
        >>> check_ins.make_date_string(1999, 2, 2)
        '1999-02-02'
        >>> check_ins.make_date_string(1999, 2, None)
        '1999-02'
        >>> check_ins.make_date_string(1999, None, None)
        '1999'
        >>> check_ins.make_date_string(1999, None, 2)
        '1999'
        """
        result = f'{year}'
        if month:
            result += f'-{month:02}'
            if day:
                result += f'-{day:02}'
        return result


def setup():
    pass
