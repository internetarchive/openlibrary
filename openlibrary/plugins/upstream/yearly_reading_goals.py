import json
from datetime import datetime
from math import floor

import web
from infogami.utils import delegate
from infogami.utils.view import public

from openlibrary.accounts import get_current_user
from openlibrary.core.bookshelves_events import BookshelfEvent, BookshelvesEvents
from openlibrary.core.yearly_reading_goals import YearlyReadingGoals

MAX_READING_GOAL = 10_000


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


def setup():
    pass
