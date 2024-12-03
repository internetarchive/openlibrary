from datetime import datetime, timedelta

import pytest

from openlibrary.catalog.utils import (
    author_dates_match,
    flip_name,
    get_missing_fields,
    get_non_isbn_asin,
    get_publication_year,
    is_asin_only,
    is_independently_published,
    is_promise_item,
    match_with_bad_chars,
    needs_isbn_and_lacks_one,
    pick_best_author,
    pick_best_name,
    pick_first_date,
    publication_too_old_and_not_exempt,
    published_in_future_year,
    remove_trailing_dot,
    remove_trailing_number_dot,
    strip_count,
)


def test_author_dates_match():
    _atype = {'key': '/type/author'}
    basic = {
        'name': 'John Smith',
        'death_date': '1688',
        'key': '/a/OL6398451A',
        'birth_date': '1650',
        'type': _atype,
    }
    full_dates = {
        'name': 'John Smith',
        'death_date': '23 June 1688',
        'key': '/a/OL6398452A',
        'birth_date': '01 January 1650',
        'type': _atype,
    }
    full_different = {
        'name': 'John Smith',
        'death_date': '12 June 1688',
        'key': '/a/OL6398453A',
        'birth_date': '01 December 1650',
        'type': _atype,
    }
    no_death = {
        'name': 'John Smith',
        'key': '/a/OL6398454A',
        'birth_date': '1650',
        'type': _atype,
    }
    no_dates = {'name': 'John Smith', 'key': '/a/OL6398455A', 'type': _atype}
    non_match = {
        'name': 'John Smith',
        'death_date': '1999',
        'key': '/a/OL6398456A',
        'birth_date': '1950',
        'type': _atype,
    }
    different_name = {'name': 'Jane Farrier', 'key': '/a/OL6398457A', 'type': _atype}

    assert author_dates_match(basic, basic)
    assert author_dates_match(basic, full_dates)
    assert author_dates_match(basic, no_death)
    assert author_dates_match(basic, no_dates)
    assert author_dates_match(no_dates, no_dates)
    # Without dates, the match returns True
    assert author_dates_match(no_dates, non_match)
    # This method only compares dates and ignores names
    assert author_dates_match(no_dates, different_name)
    assert author_dates_match(basic, non_match) is False
    # FIXME: the following should properly be False:
    assert author_dates_match(
        full_different, full_dates
    )  # this shows matches are only occurring on year, full dates are ignored!


def test_flip_name():
    assert flip_name('Smith, John.') == 'John Smith'
    assert flip_name('Smith, J.') == 'J. Smith'
    assert flip_name('No comma.') == 'No comma'


def test_pick_first_date():
    assert pick_first_date(["Mrs.", "1839-"]) == {'birth_date': '1839'}
    assert pick_first_date(["1882-."]) == {'birth_date': '1882'}
    assert pick_first_date(["1900-1990.."]) == {
        'birth_date': '1900',
        'death_date': '1990',
    }
    assert pick_first_date(["4th/5th cent."]) == {'date': '4th/5th cent.'}


def test_pick_best_name():
    names = [
        'Andre\u0301 Joa\u0303o Antonil',
        'Andr\xe9 Jo\xe3o Antonil',
        'Andre? Joa?o Antonil',
    ]
    best = names[1]
    assert pick_best_name(names) == best

    names = [
        'Antonio Carvalho da Costa',
        'Anto\u0301nio Carvalho da Costa',
        'Ant\xf3nio Carvalho da Costa',
    ]
    best = names[2]
    assert pick_best_name(names) == best


def test_pick_best_author():
    a1 = {
        'name': 'Bretteville, Etienne Dubois abb\xe9 de',
        'death_date': '1688',
        'key': '/a/OL6398452A',
        'birth_date': '1650',
        'title': 'abb\xe9 de',
        'personal_name': 'Bretteville, Etienne Dubois',
        'type': {'key': '/type/author'},
    }
    a2 = {
        'name': 'Bretteville, \xc9tienne Dubois abb\xe9 de',
        'death_date': '1688',
        'key': '/a/OL4953701A',
        'birth_date': '1650',
        'title': 'abb\xe9 de',
        'personal_name': 'Bretteville, \xc9tienne Dubois',
        'type': {'key': '/type/author'},
    }
    assert pick_best_author([a1, a2])['key'] == a2['key']


def combinations(items, n):
    if n == 0:
        yield []
    else:
        for i in range(len(items)):
            for cc in combinations(items[i + 1 :], n - 1):
                yield [items[i]] + cc


def test_match_with_bad_chars():
    samples = [
        ['Machiavelli, Niccolo, 1469-1527', 'Machiavelli, Niccol\xf2 1469-1527'],
        ['Humanitas Publica\xe7\xf5es', 'Humanitas Publicac?o?es'],
        [
            'A pesquisa ling\xfc\xedstica no Brasil',
            'A pesquisa lingu?i?stica no Brasil',
        ],
        ['S\xe3o Paulo', 'Sa?o Paulo'],
        [
            'Diccionario espa\xf1ol-ingl\xe9s de bienes ra\xedces',
            'Diccionario Espan\u0303ol-Ingle\u0301s de bienes rai\u0301ces',
        ],
        [
            'Konfliktunterdru?ckung in O?sterreich seit 1918',
            'Konfliktunterdru\u0308ckung in O\u0308sterreich seit 1918',
            'Konfliktunterdr\xfcckung in \xd6sterreich seit 1918',
        ],
        [
            'Soi\ufe20u\ufe21z khudozhnikov SSSR.',
            'Soi?u?z khudozhnikov SSSR.',
            'Soi\u0361uz khudozhnikov SSSR.',
        ],
        ['Andrzej Weronski', 'Andrzej Wero\u0144ski', 'Andrzej Weron\u0301ski'],
    ]
    for sample in samples:
        for a, b in combinations(sample, 2):
            assert match_with_bad_chars(a, b)


def test_strip_count():
    input = [
        ('Side by side', ['a', 'b', 'c', 'd']),
        ('Side by side.', ['e', 'f', 'g']),
        ('Other.', ['h', 'i']),
    ]
    expect = [
        ('Side by side', ['a', 'b', 'c', 'd', 'e', 'f', 'g']),
        ('Other.', ['h', 'i']),
    ]
    assert strip_count(input) == expect


def test_remove_trailing_dot():
    data = [
        ('Test', 'Test'),
        ('Test.', 'Test'),
        ('Test J.', 'Test J.'),
        ('Test...', 'Test...'),
        # ('Test Jr.', 'Test Jr.'),
    ]
    for input, expect in data:
        output = remove_trailing_dot(input)
        assert output == expect


@pytest.mark.parametrize(
    'year, expected',
    [
        ('1999-01', 1999),
        ('1999', 1999),
        ('01-1999', 1999),
        ('May 5, 1999', 1999),
        ('May 5, 19999', None),
        ('1999-01-01', 1999),
        ('1999/1/1', 1999),
        ('01-01-1999', 1999),
        ('1/1/1999', 1999),
        ('199', None),
        ('19990101', None),
        (None, None),
        (1999, 1999),
        (19999, None),
    ],
)
def test_publication_year(year, expected) -> None:
    assert get_publication_year(year) == expected


@pytest.mark.parametrize(
    'years_from_today, expected',
    [
        (1, True),
        (0, False),
        (-1, False),
    ],
)
def test_published_in_future_year(years_from_today, expected) -> None:
    """Test with last year, this year, and next year."""

    def get_datetime_for_years_from_now(years: int) -> datetime:
        """Get a datetime for now +/- x years."""
        now = datetime.now()
        return now + timedelta(days=365 * years)

    year = get_datetime_for_years_from_now(years_from_today).year
    assert published_in_future_year(year) == expected


@pytest.mark.parametrize(
    'name, rec, expected',
    [
        (
            "1399 is too old for an Amazon source",
            {'source_records': ['amazon:123'], 'publish_date': '1399'},
            True,
        ),
        (
            "1400 is acceptable for an Amazon source",
            {'source_records': ['amazon:123'], 'publish_date': '1400'},
            False,
        ),
        (
            "1401 is acceptable for an Amazon source",
            {'source_records': ['amazon:123'], 'publish_date': '1401'},
            False,
        ),
        (
            "1399 is acceptable for an IA source",
            {'source_records': ['ia:123'], 'publish_date': '1399'},
            False,
        ),
        (
            "1400 is acceptable for an IA source",
            {'source_records': ['ia:123'], 'publish_date': '1400'},
            False,
        ),
        (
            "1401 is acceptable for an IA source",
            {'source_records': ['ia:123'], 'publish_date': '1401'},
            False,
        ),
    ],
)
def test_publication_too_old_and_not_exempt(name, rec, expected) -> None:
    """
    See publication_too_old_and_not_exempt() for an explanation of which sources require
    which publication years.
    """
    assert publication_too_old_and_not_exempt(rec) == expected, f"Test failed: {name}"


@pytest.mark.parametrize(
    'publishers, expected',
    [
        (['INDEPENDENTLY PUBLISHED'], True),
        (['Independent publisher'], True),
        (['Another Publisher', 'independently published'], True),
        (['Another Publisher', 'independent publisher'], True),
        (['Another Publisher'], False),
    ],
)
def test_independently_published(publishers, expected) -> None:
    assert is_independently_published(publishers) == expected


@pytest.mark.parametrize(
    'rec, expected',
    [
        ({'source_records': ['bwb:123'], 'isbn_10': ['1234567890']}, False),
        ({'source_records': ['amazon:123'], 'isbn_13': ['1234567890123']}, False),
        ({'source_records': ['bwb:123'], 'isbn_10': []}, True),
        ({'source_records': ['bwb:123']}, True),
        ({'source_records': ['ia:someocaid']}, False),
        ({'source_records': ['amazon:123']}, True),
    ],
)
def test_needs_isbn_and_lacks_one(rec, expected) -> None:
    assert needs_isbn_and_lacks_one(rec) == expected


@pytest.mark.parametrize(
    'rec, expected',
    [
        ({'source_records': ['promise:123', 'ia:456']}, True),
        ({'source_records': ['ia:456']}, False),
        ({'source_records': []}, False),
        ({}, False),
    ],
)
def test_is_promise_item(rec, expected) -> None:
    assert is_promise_item(rec) == expected


@pytest.mark.parametrize(
    ["rec", "expected"],
    [
        ({"source_records": ["amazon:B01234568"]}, "B01234568"),
        ({"source_records": ["amazon:123456890"]}, None),
        ({"source_records": ["ia:BLOB"]}, None),
        ({"source_records": []}, None),
        ({"identifiers": {"ia": ["B01234568"]}}, None),
        ({"identifiers": {"amazon": ["123456890"]}}, None),
        ({"identifiers": {"amazon": ["B01234568"]}}, "B01234568"),
        ({"identifiers": {"amazon": []}}, None),
        ({"identifiers": {}}, None),
        ({}, None),
    ],
)
def test_get_non_isbn_asin(rec, expected) -> None:
    got = get_non_isbn_asin(rec)
    assert got == expected


@pytest.mark.parametrize(
    ["rec", "expected"],
    [
        ({"isbn_10": "123456890", "source_records": ["amazon:B01234568"]}, False),
        ({"isbn_13": "1234567890123", "source_records": ["amazon:B01234568"]}, False),
        ({"isbn_10": "1234567890", "identifiers": {"amazon": ["B01234568"]}}, False),
        ({"source_records": ["amazon:1234567890"]}, False),
        ({"identifiers": {"amazon": ["123456890"]}}, False),
        ({}, False),
        ({"identifiers": {"amazon": ["B01234568"]}}, True),
        ({"source_records": ["amazon:B01234568"]}, True),
    ],
)
def test_is_asin_only(rec, expected) -> None:
    got = is_asin_only(rec)
    assert got == expected


@pytest.mark.parametrize(
    'name, rec, expected',
    [
        (
            "Returns an empty list if no fields are missing",
            {'title': 'A Great Book', 'source_records': ['ia:123']},
            [],
        ),
        (
            "Catches a missing required field",
            {'source_records': ['ia:123']},
            ['title'],
        ),
        (
            "Catches multiple missing required fields",
            {'publish_date': '1999'},
            ['source_records', 'title'],
        ),
    ],
)
def test_get_missing_field(name, rec, expected) -> None:
    assert sorted(get_missing_fields(rec=rec)) == sorted(
        expected
    ), f"Test failed: {name}"


@pytest.mark.parametrize(
    ("date, expected"),
    [
        ("", ""),
        ("1865.", "1865"),
        ("1865", "1865"),  # No period to remove
        ("1865.5", "1865.5"),  # Period not at the end
        ("1865,", "1865,"),  # Comma instead of period
        ("18.", "18"),  # Minimum digits
        ("1.", "1."),  # Fewer than minimum digits with period
        ("18651.", "18651"),  # More than minimum digits
        ("123blap.", "123blap."),  # Non-digit before period
        ("123...", "123"),  # Multiple periods at the end
        ("123 -..", "123 -"),  # Spaces and hyphens before multiple periods
        ("123-.", "123-"),  # Hyphen directly before single period
        (" 123 .", " 123 "),  # Spaces around digits and single period
        ("123 - .", "123 - "),  # Space between hyphen and single period
        ("abc123...", "abc123"),  # Leading characters
        ("123...xyz", "123...xyz"),  # Trailing characters after periods
        ("12 34..", "12 34"),  # Spaces within digits before periods
        ("123", "123"),  # Spaces between periods
        ("12-34.", "12-34"),  # Hyphens within digits
        ("100-200.", "100-200"),  # Hyphens within digits, ending with period
    ],
)
def test_remove_trailing_number_dot(date: str, expected: str) -> None:
    got = remove_trailing_number_dot(date)
    assert got == expected
