"""Reading log check-ins handler and services.
"""

import json
import web

from datetime import datetime
from math import floor

from infogami.utils import delegate
from infogami.utils.view import public

from openlibrary.accounts import get_current_user
from openlibrary.app import render_template
from openlibrary.core.yearly_reading_goals import YearlyReadingGoals
from openlibrary.utils import extract_numeric_id_from_olid
from openlibrary.core.bookshelves_events import BookshelfEvent, BookshelvesEvents
from openlibrary.utils.decorators import (
    authorized_for,  # noqa: F401 side effects may be needed
)

MAX_READING_GOAL = 10_000


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
        data = json.loads(web.data())

        if not self.validate_data(data):
            raise web.badrequest(message='Invalid date submitted')

        user = get_current_user()
        if not user:
            raise web.unauthorized(message='Requires login')

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
                raise web.notfound(message='Event does not exist')

            event = events[0]
            if username != event['username']:
                raise web.forbidden()

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


class yearly_reading_goal_json(delegate.page):
    path = '/reading-goal'
    encoding = 'json'

    def GET(self):
        i = web.input(year=None)

        user = get_current_user()
        if not user:
            raise web.unauthorized(message='Requires login')

        username = user['key'].split('/')[-1]
        if i.year:
            results = [
                {'year': i.year, 'goal': record.target, 'progress': record.current}
                for record in YearlyReadingGoals.select_by_username_and_year(
                    username, i.year
                )
            ]
        else:
            results = [
                {'year': record.year, 'goal': record.target, 'progress': record.current}
                for record in YearlyReadingGoals.select_by_username(username)
            ]

        return delegate.RawText(json.dumps({'status': 'ok', 'goal': results}))

    def POST(self):
        i = web.input(goal=0, year=None, is_update=None)

        goal = min(int(i.goal), MAX_READING_GOAL)

        if i.is_update:
            if goal < 0:
                raise web.badrequest(
                    message='Reading goal update must be 0 or a positive integer'
                )
        elif not goal or goal < 1:
            raise web.badrequest(message='Reading goal must be a positive integer')

        if i.is_update and not i.year:
            raise web.badrequest(message='Year required to update reading goals')

        user = get_current_user()
        if not user:
            raise web.unauthorized(message='Requires login')

        username = user['key'].split('/')[-1]
        current_year = i.year or datetime.now().year

        if i.is_update:
            if goal == 0:
                # Delete goal if "0" was submitted:
                YearlyReadingGoals.delete_by_username_and_year(username, i.year)
            else:
                # Update goal normally:
                YearlyReadingGoals.update_target(username, i.year, goal)
        else:
            YearlyReadingGoals.create(username, current_year, goal)

        return delegate.RawText(json.dumps({'status': 'ok'}))


@public
def get_reading_goals(year=None):
    user = get_current_user()
    if not user:
        return None

    username = user['key'].split('/')[-1]
    if not year:
        year = datetime.now().year

    if not (data := YearlyReadingGoals.select_by_username_and_year(username, year)):
        return None

    books_read = BookshelvesEvents.select_distinct_by_user_type_and_year(
        username, BookshelfEvent.FINISH, year
    )
    read_count = len(books_read)
    result = YearlyGoal(data[0].year, data[0].target, read_count)

    return result


class YearlyGoal:
    def __init__(self, year, goal, books_read):
        self.year = year
        self.goal = goal
        self.books_read = books_read
        self.progress = floor((books_read / goal) * 100)

    @classmethod
    def calc_progress(cls, books_read, goal):
        return floor((books_read / goal) * 100)


class ui_partials(delegate.page):
    path = '/reading-goal/partials'
    encoding = 'json'

    def GET(self):
        i = web.input(year=None)
        year = i.year or datetime.now().year
        goal = get_reading_goals(year=year)
        component = render_template('check_ins/reading_goal_progress', [goal])
        partials = {"partials": str(component)}
        return delegate.RawText(json.dumps(partials))


def setup():
    pass
