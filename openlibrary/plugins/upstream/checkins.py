"""Reading log check-ins handler and services."""


def make_date_string(year: int, month: int | None, day: int | None) -> str:
    """Creates a date string in the expected format, given the year, month, and day.

    Event dates can take one of three forms:
    "YYYY"
    "YYYY-MM"
    "YYYY-MM-DD"
    """
    result = f"{year}"
    if month:
        result += f"-{month:02}"
        if day:
            result += f"-{day:02}"
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
    if month is not None and not 1 <= int(month) <= 12:
        return False
    if day is not None and not 1 <= int(day) <= 31:
        return False
    return not day or bool(month)


def setup():
    pass
