"""Generic date utilities."""

import calendar
import datetime as dt
import re
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
    now = dt.datetime.now()
    return calendar.monthrange(now.year, now.month)[1]


def todays_date_minus(**kwargs) -> dt.date:
    return dt.date.today() - dt.timedelta(**kwargs)


def date_n_days_ago(n: int | None = None, start=None) -> dt.date | None:
    """
    Args:
        n (int) - number of days since start
        start (date) - date to start counting from (default: today)
    Returns:
        A (datetime.date) of `n` days ago if n is provided, else None
    """
    _start = start or dt.date.today()
    return (_start - dt.timedelta(days=n)) if n else None


DATE_ONE_YEAR_AGO = date_n_days_ago(n=365)
DATE_ONE_MONTH_AGO = date_n_days_ago(n=days_in_current_month())
DATE_ONE_WEEK_AGO = date_n_days_ago(n=7)
DATE_ONE_DAY_AGO = date_n_days_ago(n=1)


def parse_date(datestr: str) -> dt.date:
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
    return dt.date(int(yyyy), (mm and int(mm)) or 1, (dd and int(dd)) or 1)


def parse_daterange(datestr: str) -> tuple[dt.date, dt.date]:
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


def nextday(date: dt.date) -> dt.date:
    return date + dt.timedelta(1)


def nextmonth(date: dt.date) -> dt.date:
    """Returns a new date object with first day of the next month."""
    year, month = date.year, date.month
    month = month + 1

    if month > 12:
        month = 1
        year += 1

    return dt.date(year, month, 1)


def nextyear(date: dt.date) -> dt.date:
    """Returns a new date object with first day of the next year."""
    return dt.date(date.year + 1, 1, 1)


def _resize_list(x, size: int) -> None:
    """Increase the size of the list x to the specified size it is smaller."""
    if len(x) < size:
        x += [None] * (size - len(x))


MONTH_NAMES: dict[str, int] = {
    name: i
    for i, names in enumerate(
        [
            ("january", "jan"),
            ("february", "feb"),
            ("march", "mar"),
            ("april", "apr"),
            ("may",),
            ("june", "jun"),
            ("july", "jul"),
            ("august", "aug"),
            ("september", "sept", "sep"),
            ("october", "oct"),
            ("november", "nov"),
            ("december", "dec"),
        ],
        start=1,
    )
    for name in names
}
# Era markers, allowed to touch the number ("77BC"). BC: "B.C."/"BCE", French
# "av. J.-C.", Spanish/Italian "a.C.", Russian "до н. э.". AD: "A.D."/"CE", Spanish "d.C."
_BC_RE = re.compile(r"(?<![^\W\d_])(?:b\.?\s?c\.?(?:e\.?)?|av\.?\s*j|a\.\s?c\.?|до\s*н\.?\s*э\.?)(?![^\W\d_])", re.IGNORECASE)
_AD_RE = re.compile(r"(?<![^\W\d_])(?:a\.?\s?d|c\.?\s?e|d\.?\s?c)\.?(?![^\W\d_])", re.IGNORECASE)


def format_solr_date(year: int, month: int = 1, day: int = 1) -> str:
    """Format as a Solr date. BC years use ISO 8601's astronomical numbering
    (1 BC = ``0000``, 2 BC = ``-0001``)."""
    sign = "-" if year < 0 else ""
    return f"{sign}{abs(year):04d}-{month:02d}-{day:02d}T00:00:00Z"


def parse_user_entered_date(date_str: str | None) -> str | None:
    """Best-effort parse of a free-text, user-entered date (e.g. an author's
    birth date) into a Solr date string (e.g. ``1842-03-01T00:00:00Z``), for sorting.

    Missing month/day default to January 1st, and partial years to the start
    of their range ("19xx" and "20th century" -> 1900). See format_solr_date
    for BC years. Returns None when no year can be identified unambiguously
    (e.g. "12/24", "ca 18"), so the record sorts with the undated ones.

    >>> parse_user_entered_date("10 Jan 2000")
    '2000-01-10T00:00:00Z'
    >>> parse_user_entered_date("ca. 264 B.C.")
    '-0263-01-01T00:00:00Z'
    """
    if not date_str:
        return None
    is_bc = bool(_BC_RE.search(date_str))
    is_ad = bool(_AD_RE.search(date_str))
    text = _AD_RE.sub(" ", _BC_RE.sub(" ", date_str))
    month = day = None

    iso_match = re.search(r"(?<!\d)(\d{4})-(\d{2})(?:-(\d{2}))?(?!\d)", text)
    year_match = re.search(r"(?<!\d)\d{4}(?!\d)", text)
    if not (iso_match or year_match):
        if (partial_year := _parse_partial_year(text, is_bc)) is not None:
            return format_solr_date(partial_year)
        year_match = re.search(r"(?<!\w)[1-9]\d{2}(?!\w)", text)

    if iso_match:
        year = int(iso_match.group(1))
        month = int(iso_match.group(2))
        day = int(iso_match.group(3)) if iso_match.group(3) else None
    elif year_match:
        year = int(year_match.group())
        rest = text[: year_match.start()] + " " + text[year_match.end() :]
        months = {MONTH_NAMES[w] for w in re.findall(r"[^\W\d_]+", rest.lower()) if w in MONTH_NAMES}
        if len(months) == 1:
            month = months.pop()
            if (days := re.findall(r"(?<!\d)(\d{1,2})(?:st|nd|rd|th)?(?!\d)", rest)) and len(days) == 1:
                day = int(days[0])
    elif m := re.fullmatch(
        # A bare 1-2 digit year with qualifiers/punctuation, e.g. "ca. 67?" or "(58)"
        r"(?:\b(?:ca|c|circa|approx|approximately|fl|floruit|active|b|d|born|died)\b|[\s?.,;:()\[\]])*"
        r"(\d{1,2})"
        r"(?:\s*\[from old catalog\]|[\s?.,;:()\[\]])*",
        text.strip(),
        re.IGNORECASE,
    ):
        year = int(m.group(1))
        # Without an era, a bare 1-2 digit number is more likely a truncated
        # year ("95") or a day than an ancient year, unless it's marked as
        # such; and 10-20 is usually a truncated century ("ca 18")
        if not (is_bc or is_ad) and (10 <= year <= 20 or not re.search(r"[a-z]", text, re.IGNORECASE)):
            return None
    else:
        return None

    if is_bc:
        year = 1 - year
    elif year == 0:
        return None
    try:
        dt.date(2000, month or 1, day or 1)  # validate month/day; 2000 is a leap year
    except ValueError:
        month = day = None
    return format_solr_date(year, month or 1, day or 1)


def _parse_partial_year(text: str, is_bc: bool) -> int | None:
    """The first year of a century ("18th cent.", "4th cent. B.C.") or of a
    year with unknown digits ("19xx", "19..", "197-", "198?"), in astronomical
    numbering."""
    ordinal = r"(\d{1,2})(?:st|nd|rd|th|d)\.?"
    has_month = any(w in MONTH_NAMES for w in re.findall(r"[^\W\d_]+", text.lower()))
    if (
        (
            # Takes the first of e.g. "16th/17th cent." or "4th or 3rd cent. B.C."
            m := re.search(rf"(?<!\d){ordinal}(?:\s*(?:/|-|or)\s*{ordinal})?\s*(?:cent|c\b)", text, re.IGNORECASE)
        )
        or (
            # A lone ordinal ("active 17th"), unless it's a day ("July 4th")
            not has_month and (m := re.search(rf"(?<!\d){ordinal}\s*$", text.strip(), re.IGNORECASE))
        )
        or (m := re.search(r"(?<!\d)(\d{1,2})\.?\s*cent", text, re.IGNORECASE))
    ):
        century = int(m.group(1))
        return 1 - century * 100 if is_bc else max((century - 1) * 100, 1)
    if not is_bc and (m := re.search(r"(?<!\d)(\d{1,3})([xX?._\-]+)(?!\d)", text)):
        digits, placeholders = m.groups()
        # "983?" is an uncertain year 983 rather than 9830-9839
        if placeholders.strip("?") == "" and len(digits) == 3 and not digits.startswith(("1", "20")):
            return None
        if len(digits) + len(placeholders) >= 4:
            return int(digits.ljust(4, "0"))
    return None


@public
def current_year() -> int:
    return dt.datetime.now().year


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
