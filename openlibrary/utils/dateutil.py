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


def days_in_current_month() -> int:
    now = datetime.datetime.now()
    return calendar.monthrange(now.year, now.month)[1]


def todays_date_minus(**kwargs) -> datetime.date:
    return datetime.date.today() - datetime.timedelta(**kwargs)


def date_n_days_ago(n: int | None = None, start=None) -> datetime.date | None:
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


def parse_date(datestr: str) -> datetime.date:
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


def parse_daterange(datestr: str) -> tuple[datetime.date, datetime.date]:
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


def nextday(date: datetime.date) -> datetime.date:
    return date + datetime.timedelta(1)


def nextmonth(date: datetime.date) -> datetime.date:
    """Returns a new date object with first day of the next month."""
    year, month = date.year, date.month
    month = month + 1

    if month > 12:
        month = 1
        year += 1

    return datetime.date(year, month, 1)


def nextyear(date: datetime.date) -> datetime.date:
    """Returns a new date object with first day of the next year."""
    return datetime.date(date.year + 1, 1, 1)


def _resize_list(x, size: int) -> None:
    """Increase the size of the list x to the specified size it is smaller."""
    if len(x) < size:
        x += [None] * (size - len(x))


@public
def current_year() -> int:
    return datetime.datetime.now().year


@contextmanager
def elapsed_time(name: str = "elapsed_time"):
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
