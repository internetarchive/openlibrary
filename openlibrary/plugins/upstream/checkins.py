"""Reading log check-ins handler and services."""

import json

import web
from typing_extensions import deprecated

from infogami.utils import delegate
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
    result = f'{year}'
    if month:
        result += f'-{month:02}'
        if day:
            result += f'-{day:02}'
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

    username = user['key'].split('/')[-1]

    work_id = extract_numeric_id_from_olid(work_olid)

    result = BookshelvesEvents.get_latest_event_date(
        username, work_id, BookshelfEvent.FINISH
    )
    return result


@deprecated("migrated to fastapi")
class patron_check_ins(delegate.page):
    path = r'/works/OL(\d+)W/check-ins'
    encoding = 'json'

    def POST(self, work_id):
        """Validates data, constructs date string, and persists check-in event.

        Data object should have the following:
        event_type : number
        year : number
        month : number : optional
        day : number : optional
        edition_key : string : optional
        event_id : int : optional
        """
        user = get_current_user()
        if not user:
            raise web.HTTPError(
                "401 Unauthorized", headers={"Content-Type": "application/json"}
            )

        data = json.loads(web.data())
        if not self.validate_data(data):
            raise web.HTTPError(
                "400 Bad Request", headers={"Content-Type": "application/json"}
            )

        username = user['key'].split('/')[-1]

        edition_key = data.get('edition_key', None)
        edition_id = extract_numeric_id_from_olid(edition_key) if edition_key else None

        event_type = data.get('event_type')

        date_str = make_date_string(
            data.get('year', None),
            data.get('month', None),
            data.get('day', None),
        )

        event_id = data.get('event_id', None)

        if event_id:
            # update existing event
            events = BookshelvesEvents.select_by_id(event_id)
            if not events:
                raise web.HTTPError(
                    "404 Not Found", headers={"Content-Type": "application/json"}
                )

            event = events[0]
            if username != event['username']:
                raise web.HTTPError(
                    "403 Forbidden", headers={"Content-Type": "application/json"}
                )

            BookshelvesEvents.update_event(
                event_id, event_date=date_str, edition_id=edition_id
            )
        else:
            # create new event
            result = BookshelvesEvents.create_event(
                username, work_id, edition_id, date_str, event_type=event_type
            )

            event_id = result

        return delegate.RawText(json.dumps({'status': 'ok', 'id': event_id}))

    def validate_data(self, data):
        """Validates data submitted from check-in dialog."""

        # Event type must exist:
        if 'event_type' not in data:
            return False

        if not BookshelfEvent.has_value(data.get('event_type')):
            return False

        # Date must be valid:
        return is_valid_date(
            data.get('year', None),
            data.get('month', None),
            data.get('day', None),
        )


@deprecated("migrated to fastapi")
class patron_check_in(delegate.page):
    path = r'/check-ins/(\d+)'

    def DELETE(self, check_in_id):
        user = get_current_user()
        if not user:
            raise web.unauthorized(message="Requires login")

        events = BookshelvesEvents.select_by_id(check_in_id)
        if not events:
            raise web.notfound(message='Event does not exist')

        event = events[0]
        username = user['key'].split('/')[-1]
        if username != event['username']:
            raise web.forbidden()

        BookshelvesEvents.delete_by_id(check_in_id)
        return web.ok()


def setup():
    pass
