import datetime as dt

import pytest

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


@pytest.mark.parametrize(
    ("date_str", "expected"),
    [
        # Full dates
        ("1993-11-03", "1993-11-03T00:00:00Z"),
        ("1993-11", "1993-11-01T00:00:00Z"),
        ("10 Jan 2000", "2000-01-10T00:00:00Z"),
        ("2 Jan 2000", "2000-01-02T00:00:00Z"),
        ("January 10, 2000", "2000-01-10T00:00:00Z"),
        ("23 Sep 1889", "1889-09-23T00:00:00Z"),
        ("dec 25.2010", "2010-12-25T00:00:00Z"),
        ("April 1980", "1980-04-01T00:00:00Z"),
        # Numeric day/month order is ambiguous, so only the year is kept
        ("12/22/1924", "1924-01-01T00:00:00Z"),
        ("12.01.1954", "1954-01-01T00:00:00Z"),
        # Year only, with cruft/qualifiers
        ("1842", "1842-01-01T00:00:00Z"),
        ("1984.,", "1984-01-01T00:00:00Z"),
        ("1897. [from old catalog]", "1897-01-01T00:00:00Z"),
        ("(1686", "1686-01-01T00:00:00Z"),
        ("1687?.", "1687-01-01T00:00:00Z"),
        ("approx 1990", "1990-01-01T00:00:00Z"),
        ("b. ca. 1841", "1841-01-01T00:00:00Z"),
        ("fl. 1880", "1880-01-01T00:00:00Z"),
        ("1195 or 1196", "1195-01-01T00:00:00Z"),
        ("1840-1845", "1840-01-01T00:00:00Z"),
        # Years before 1000
        ("673", "0673-01-01T00:00:00Z"),
        ("ca. 673", "0673-01-01T00:00:00Z"),
        ("584?", "0584-01-01T00:00:00Z"),
        ("ca. 95", "0095-01-01T00:00:00Z"),
        ("65 A.D.", "0065-01-01T00:00:00Z"),
        ("18 A.D.", "0018-01-01T00:00:00Z"),
        ("17 dC.", "0017-01-01T00:00:00Z"),
        ("A.D. 65", "0065-01-01T00:00:00Z"),
        # BC: astronomical year numbering
        ("ca. 264 B.C.", "-0263-01-01T00:00:00Z"),
        ("1207 B.C.", "-1206-01-01T00:00:00Z"),
        ("1 BC", "0000-01-01T00:00:00Z"),
        ("63 BCE", "-0062-01-01T00:00:00Z"),
        ("0043 av. J.-C.", "-0042-01-01T00:00:00Z"),
        ("120? a.C.", "-0119-01-01T00:00:00Z"),
        ("ca. 18 B.C.", "-0017-01-01T00:00:00Z"),
        # Uncertain decades
        ("198?", "1980-01-01T00:00:00Z"),
        ("(197?", "1970-01-01T00:00:00Z"),
        ("983?", "0983-01-01T00:00:00Z"),
        # Unparsable / ambiguous
        (None, None),
        ("", None),
        ("19th cent.", None),
        ("16th/17th cent.", None),
        ("19..", None),
        ("12/24", None),
        ("12.04.21", None),
        ("95", None),
        ("ca 18", None),
        ("b.18", None),
        ("00/00/0000", None),
        ("2857", None),
        ("12 January 2918", None),
        ("[from old catalog]", None),
        ("19 Mar 007", None),
    ],
)
def test_parse_user_entered_date(date_str, expected):
    assert dateutil.parse_user_entered_date(date_str) == expected
