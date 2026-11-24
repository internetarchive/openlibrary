import datetime as dt

from .. import dateutil


def test_parse_date():
    assert dateutil.parse_date("2010") == dt.date(2010, 1, 1)
    assert dateutil.parse_date("2010-02") == dt.date(2010, 2, 1)
    assert dateutil.parse_date("2010-02-03") == dt.date(2010, 2, 3)


def test_nextday():
    assert dateutil.nextday(dt.date(2008, 1, 1)) == dt.date(2008, 1, 2)
    assert dateutil.nextday(dt.date(2008, 1, 31)) == dt.date(2008, 2, 1)

    assert dateutil.nextday(dt.date(2008, 2, 28)) == dt.date(2008, 2, 29)
    assert dateutil.nextday(dt.date(2008, 2, 29)) == dt.date(2008, 3, 1)

    assert dateutil.nextday(dt.date(2008, 12, 31)) == dt.date(2009, 1, 1)


def test_nextmonth():
    assert dateutil.nextmonth(dt.date(2008, 1, 1)) == dt.date(2008, 2, 1)
    assert dateutil.nextmonth(dt.date(2008, 1, 12)) == dt.date(2008, 2, 1)

    assert dateutil.nextmonth(dt.date(2008, 12, 12)) == dt.date(2009, 1, 1)


def test_nextyear():
    assert dateutil.nextyear(dt.date(2008, 1, 1)) == dt.date(2009, 1, 1)
    assert dateutil.nextyear(dt.date(2008, 2, 12)) == dt.date(2009, 1, 1)


def test_parse_daterange():
    assert dateutil.parse_daterange("2010") == (
        dt.date(2010, 1, 1),
        dt.date(2011, 1, 1),
    )
    assert dateutil.parse_daterange("2010-02") == (
        dt.date(2010, 2, 1),
        dt.date(2010, 3, 1),
    )
    assert dateutil.parse_daterange("2010-02-03") == (
        dt.date(2010, 2, 3),
        dt.date(2010, 2, 4),
    )
