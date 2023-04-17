from .. import dateutil
import datetime


def test_parse_date():
    assert dateutil.parse_date("2010") == datetime.date(2010, 1, 1)
    assert dateutil.parse_date("2010-02") == datetime.date(2010, 2, 1)
    assert dateutil.parse_date("2010-02-03") == datetime.date(2010, 2, 3)


def test_nextday():
    assert dateutil.nextday(datetime.date(2008, 1, 1)) == datetime.date(2008, 1, 2)
    assert dateutil.nextday(datetime.date(2008, 1, 31)) == datetime.date(2008, 2, 1)

    assert dateutil.nextday(datetime.date(2008, 2, 28)) == datetime.date(2008, 2, 29)
    assert dateutil.nextday(datetime.date(2008, 2, 29)) == datetime.date(2008, 3, 1)

    assert dateutil.nextday(datetime.date(2008, 12, 31)) == datetime.date(2009, 1, 1)


def test_nextmonth():
    assert dateutil.nextmonth(datetime.date(2008, 1, 1)) == datetime.date(2008, 2, 1)
    assert dateutil.nextmonth(datetime.date(2008, 1, 12)) == datetime.date(2008, 2, 1)

    assert dateutil.nextmonth(datetime.date(2008, 12, 12)) == datetime.date(2009, 1, 1)


def test_nextyear():
    assert dateutil.nextyear(datetime.date(2008, 1, 1)) == datetime.date(2009, 1, 1)
    assert dateutil.nextyear(datetime.date(2008, 2, 12)) == datetime.date(2009, 1, 1)


def test_parse_daterange():
    assert dateutil.parse_daterange("2010") == (
        datetime.date(2010, 1, 1),
        datetime.date(2011, 1, 1),
    )
    assert dateutil.parse_daterange("2010-02") == (
        datetime.date(2010, 2, 1),
        datetime.date(2010, 3, 1),
    )
    assert dateutil.parse_daterange("2010-02-03") == (
        datetime.date(2010, 2, 3),
        datetime.date(2010, 2, 4),
    )


def test_within_date_range():
    # Test single-year date range:
    start_date = datetime.datetime(2030, 1, 2)
    end_date = datetime.datetime(2030, 5, 20)

    # Positive cases:
    assert (
        dateutil.within_date_range(
            start_date.month,
            start_date.day,
            end_date.month,
            end_date.day,
            current_date=start_date,
        )
        is True
    )
    assert (
        dateutil.within_date_range(
            start_date.month,
            start_date.day,
            end_date.month,
            end_date.day,
            current_date=datetime.datetime(2030, 2, 1),
        )
        is True
    )
    assert (
        dateutil.within_date_range(
            start_date.month,
            start_date.day,
            end_date.month,
            end_date.day,
            current_date=end_date,
        )
        is True
    )
    # Negative cases:
    assert (
        dateutil.within_date_range(
            start_date.month,
            start_date.day,
            end_date.month,
            end_date.day,
            current_date=datetime.datetime(2030, 1, 1),
        )
        is False
    )
    assert (
        dateutil.within_date_range(
            start_date.month,
            start_date.day,
            end_date.month,
            end_date.day,
            current_date=datetime.datetime(2030, 5, 25),
        )
        is False
    )
    assert (
        dateutil.within_date_range(
            start_date.month,
            start_date.day,
            end_date.month,
            end_date.day,
            current_date=datetime.datetime(2030, 10, 13),
        )
        is False
    )

    # Test multi-year date range:
    start_date = datetime.datetime(2030, 12, 1)
    end_date = datetime.datetime(2031, 2, 1)

    # Positive cases:
    assert (
        dateutil.within_date_range(
            start_date.month,
            start_date.day,
            end_date.month,
            end_date.day,
            current_date=start_date,
        )
        is True
    )
    assert (
        dateutil.within_date_range(
            start_date.month,
            start_date.day,
            end_date.month,
            end_date.day,
            current_date=datetime.datetime(2031, 1, 11),
        )
        is True
    )
    assert (
        dateutil.within_date_range(
            start_date.month,
            start_date.day,
            end_date.month,
            end_date.day,
            current_date=end_date,
        )
        is True
    )

    # Negative cases:
    assert (
        dateutil.within_date_range(
            start_date.month,
            start_date.day,
            end_date.month,
            end_date.day,
            current_date=datetime.datetime(2030, 11, 15),
        )
        is False
    )
    assert (
        dateutil.within_date_range(
            start_date.month,
            start_date.day,
            end_date.month,
            end_date.day,
            current_date=datetime.datetime(2031, 2, 2),
        )
        is False
    )

    # Test single-month date range:
    start_date = datetime.datetime(2030, 6, 3)
    end_date = datetime.datetime(2030, 6, 10)

    # Positive cases:
    assert (
        dateutil.within_date_range(
            start_date.month,
            start_date.day,
            end_date.month,
            end_date.day,
            current_date=start_date,
        )
        is True
    )
    assert (
        dateutil.within_date_range(
            start_date.month,
            start_date.day,
            end_date.month,
            end_date.day,
            current_date=datetime.datetime(2030, 6, 8),
        )
        is True
    )
    assert (
        dateutil.within_date_range(
            start_date.month,
            start_date.day,
            end_date.month,
            end_date.day,
            current_date=end_date,
        )
        is True
    )

    # Negative cases:
    assert (
        dateutil.within_date_range(
            start_date.month,
            start_date.day,
            end_date.month,
            end_date.day,
            current_date=datetime.datetime(2030, 5, 8),
        )
        is False
    )
    assert (
        dateutil.within_date_range(
            start_date.month,
            start_date.day,
            end_date.month,
            end_date.day,
            current_date=datetime.datetime(2031, 6, 2),
        )
        is False
    )
    assert (
        dateutil.within_date_range(
            start_date.month,
            start_date.day,
            end_date.month,
            end_date.day,
            current_date=datetime.datetime(2031, 6, 20),
        )
        is False
    )
