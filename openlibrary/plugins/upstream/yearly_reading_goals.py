from datetime import datetime
from math import floor

from infogami.utils.view import public
from openlibrary.accounts import get_current_user
from openlibrary.core.bookshelves_events import BookshelfEvent, BookshelvesEvents
from openlibrary.core.yearly_reading_goals import YearlyReadingGoals

MAX_READING_GOAL = 10_000


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
