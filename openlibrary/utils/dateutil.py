"""Generic date utilities.
"""

import calendar
import datetime
from contextlib import contextmanager
from sys import stderr
from time import perf_counter

from infogami.utils.view import public


MINUTE_SECS = 60
HALF_HOUR_SECS = MINUTE_SECS * 30
HOUR_SECS = MINUTE_SECS * 60
HALF_DAY_SECS = HOUR_SECS * 12
DAY_SECS = HOUR_SECS * 24
WEEK_SECS = DAY_SECS * 7


def days_in_current_month():
    now = datetime.datetime.now()
    return calendar.monthrange(now.year, now.month)[1]


def todays_date_minus(**kwargs):
    return datetime.date.today() - datetime.timedelta(**kwargs)


def date_n_days_ago(n=None, start=None):
    """
    Args:
        n (int) - number of days since start
        start (date) - date to start counting from (default: today)
    Returns:
        A (datetime.date) of `n` days ago if n is provided, else None
    """
    _start = start or datetime.date.today()
    return (_start - datetime.timedelta(days=n)) if n else None


DATE_ONE_YEAR_AGO = date_n_days_ago(n=365)
DATE_ONE_MONTH_AGO = date_n_days_ago(n=days_in_current_month())
DATE_ONE_WEEK_AGO = date_n_days_ago(n=7)
DATE_ONE_DAY_AGO = date_n_days_ago(n=1)


def parse_date(datestr):
    """Parses date string.

    >>> parse_date("2010")
    datetime.date(2010, 1, 1)
    >>> parse_date("2010-02")
    datetime.date(2010, 2, 1)
    >>> parse_date("2010-02-04")
    datetime.date(2010, 2, 4)
    """
    tokens = datestr.split("-")
    _resize_list(tokens, 3)

    yyyy, mm, dd = tokens[:3]
    return datetime.date(int(yyyy), mm and int(mm) or 1, dd and int(dd) or 1)


def parse_daterange(datestr):
    """Parses date range.

    >>> parse_daterange("2010-02")
    (datetime.date(2010, 2, 1), datetime.date(2010, 3, 1))
    """
    date = parse_date(datestr)
    tokens = datestr.split("-")

    if len(tokens) == 1:  # only year specified
        return date, nextyear(date)
    elif len(tokens) == 2:  # year and month specified
        return date, nextmonth(date)
    else:
        return date, nextday(date)


def nextday(date):
    return date + datetime.timedelta(1)


def nextmonth(date):
    """Returns a new date object with first day of the next month."""
    year, month = date.year, date.month
    month = month + 1

    if month > 12:
        month = 1
        year += 1

    return datetime.date(year, month, 1)


def nextyear(date):
    """Returns a new date object with first day of the next year."""
    return datetime.date(date.year + 1, 1, 1)


def _resize_list(x, size):
    """Increase the size of the list x to the specified size it is smaller."""
    if len(x) < size:
        x += [None] * (size - len(x))


@public
def current_year():
    return datetime.datetime.now().year


@public
def get_reading_goals_year():
    now = datetime.datetime.now()
    year = now.year
    return year if now.month < 12 else year + 1


@public
def within_date_range(
    start_month: int,
    start_day: int,
    end_month: int,
    end_day: int,
    current_date: datetime.datetime | None = None,
) -> bool:
    """
    Checks if the current date is within the given duration.
    If now current_date is given, the actual current date is instead.
    Year is not used when determining if current date is within range.
    """
    now = current_date or datetime.datetime.now()
    current_month = now.month
    current_day = now.day

    if start_month < end_month:  # Duration spans a single calendar year
        if (
            (current_month < start_month or current_month > end_month)
            or (current_month == start_month and current_day < start_day)
            or (current_month == end_month and current_day > end_day)
        ):
            return False
    elif start_month > end_month:  # Duration spans two years
        if (
            (current_month > end_month and current_month < start_month)
            or (current_month == start_month and current_day < start_day)
            or (current_month == end_month and current_day > end_day)
        ):
            return False
    else:  # Duration is within a single month
        if (current_month != start_month) or (
            current_day < start_day or current_day > end_day
        ):
            return False

    return True


@contextmanager
def elapsed_time(name="elapsed_time"):
    """
    Two ways to use elapsed_time():
    1. As a decorator to time the execution of an entire function:
        @elapsed_time("my_slow_function")
        def my_slow_function(n=10_000_000):
            pass
    2. As a context manager to time the execution of a block of code inside a function:
        with elapsed_time("my_slow_block_of_code"):
            pass
    """
    start = perf_counter()
    yield
    print(f"Elapsed time ({name}): {perf_counter() - start:0.8} seconds", file=stderr)
