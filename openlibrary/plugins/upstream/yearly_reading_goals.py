from datetime import datetime
from math import floor

from infogami.utils.view import public
from openlibrary.accounts import get_current_user
from openlibrary.core.bookshelves_events import BookshelfEvent, BookshelvesEvents
from openlibrary.core.yearly_reading_goals import YearlyReadingGoals
from openlibrary.utils.async_utils import async_bridge


async def get_reading_goals_async(username: str, year: int) -> YearlyGoal | None:
    """User's reading goal and progress for ``year``."""
    goal = await YearlyReadingGoals.select_by_username_and_year(username, year)
    if goal is None:
        return None

    books_read = await BookshelvesEvents.count_distinct_work_ids_by_user_type_and_year(username, BookshelfEvent.FINISH, year)
    return YearlyGoal(goal.year, goal.target, books_read)


@public
def get_reading_goals(year=None):
    user = get_current_user()
    if not user:
        return None

    username = user.get_username()
    return async_bridge.run(get_reading_goals_async(username, year or datetime.now().year))


class YearlyGoal:
    def __init__(self, year, goal, books_read):
        self.year = year
        self.goal = goal
        self.books_read = books_read
        self.progress = floor((books_read / goal) * 100)

    @property
    def completed(self) -> int:
        """Progress capped at 100 for the bar width."""
        return min(self.progress, 100) if self.progress is not None else 0


def setup():
    pass
