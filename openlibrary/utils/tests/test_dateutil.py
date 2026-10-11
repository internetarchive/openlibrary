import datetime

from .. import dateutil


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


def test_date_cutoffs_are_computed_at_call_time(monkeypatch):
    """Regression test: the "one week/month ago" cutoffs must follow the current
    date instead of being frozen when the module is imported."""

    def set_today(today: datetime.date):
        class FakeDate(datetime.date):
            @classmethod
            def today(cls):
                return today

        class FakeDatetime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.datetime(today.year, today.month, today.day)

        monkeypatch.setattr(dateutil.datetime, "date", FakeDate)
        monkeypatch.setattr(dateutil.datetime, "datetime", FakeDatetime)

    set_today(datetime.date(2026, 9, 1))
    assert dateutil.date_one_day_ago() == datetime.date(2026, 8, 31)
    assert dateutil.date_one_week_ago() == datetime.date(2026, 8, 25)
    assert dateutil.date_one_month_ago() == datetime.date(2026, 8, 2)

    # Same process, a month later: the cutoffs must move with the clock.
    set_today(datetime.date(2026, 10, 2))
    assert dateutil.date_one_day_ago() == datetime.date(2026, 10, 1)
    assert dateutil.date_one_week_ago() == datetime.date(2026, 9, 25)
    assert dateutil.date_one_month_ago() == datetime.date(2026, 9, 1)
    assert dateutil.date_one_year_ago() == datetime.date(2025, 10, 2)
