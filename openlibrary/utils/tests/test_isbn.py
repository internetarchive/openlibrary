import pytest

from openlibrary.utils.isbn import (
    get_isbn_10_and_13,
    get_isbn_10s_and_13s,
    isbn_10_to_isbn_13,
    isbn_13_to_isbn_10,
    normalize_identifier,
    normalize_isbn,
    opposite_isbn,
)


def test_isbn_13_to_isbn_10():
    assert isbn_13_to_isbn_10('978-0-940787-08-7') == '0940787083'
    assert isbn_13_to_isbn_10('9780940787087') == '0940787083'
    assert isbn_13_to_isbn_10('BAD-ISBN') is None


def test_isbn_10_to_isbn_13():
    assert isbn_10_to_isbn_13('0-940787-08-3') == '9780940787087'
    assert isbn_10_to_isbn_13('0940787083') == '9780940787087'
    assert isbn_10_to_isbn_13('BAD-ISBN') is None


def test_opposite_isbn():
    assert opposite_isbn('0-940787-08-3') == '9780940787087'
    assert opposite_isbn('978-0-940787-08-7') == '0940787083'
    assert opposite_isbn('BAD-ISBN') is None


def test_normalize_isbn_returns_None():
    assert normalize_isbn(None) is None
    assert normalize_isbn('') is None
    assert normalize_isbn('a') is None


isbn_cases = [
    ('1841151866', '1841151866'),
    ('184115186x', '184115186X'),
    ('184115186X', '184115186X'),
    ('184-115-1866', '1841151866'),
    ('9781841151861', '9781841151861'),
    ('978-1841151861', '9781841151861'),
    ('123-456-789-X ', '123456789X'),
    ('ISBN: 123-456-789-X ', '123456789X'),
    ('56', None),
]


@pytest.mark.parametrize(('isbnlike', 'expected'), isbn_cases)
def test_normalize_isbn(isbnlike, expected):
    assert normalize_isbn(isbnlike) == expected


def test_get_isbn_10s_and_13s() -> None:
    # isbn 10 only
    result = get_isbn_10s_and_13s(["1576079457"])
    assert result == (["1576079457"], [])

    # isbn 13 only
    result = get_isbn_10s_and_13s(["9781576079454"])
    assert result == ([], ["9781576079454"])

    # mixed isbn 10 and 13, with multiple elements in each, one which has an extra space.
    result = get_isbn_10s_and_13s(
        ["9781576079454", "1576079457", "1576079392 ", "9781280711190"]
    )
    assert result == (["1576079457", "1576079392"], ["9781576079454", "9781280711190"])

    # an empty list
    result = get_isbn_10s_and_13s([])
    assert result == ([], [])

    # not an isbn
    result = get_isbn_10s_and_13s(["flop"])
    assert result == ([], [])

    # isbn 10 string, with an extra space.
    result = get_isbn_10s_and_13s(" 1576079457")
    assert result == (["1576079457"], [])

    # isbn 13 string
    result = get_isbn_10s_and_13s("9781280711190")
    assert result == ([], ["9781280711190"])


@pytest.mark.parametrize(
    ('isbn', 'expected'),
    [
        ("1111111111", ("1111111111", "9781111111113")),
        ("9781111111113", ("1111111111", "9781111111113")),
        ("979-1-23456-789-6", (None, "9791234567896")),
        ("", (None, None)),
        (None, (None, None)),
    ],
)
def test_get_isbn_10_and_13(isbn, expected) -> None:
    got = get_isbn_10_and_13(isbn)
    assert got == expected


@pytest.mark.parametrize(
    ('identifier', 'expected'),
    [
        ("B01234678", ("B01234678", None, None)),
        ("1111111111", (None, "1111111111", "9781111111113")),
        ("9781111111113", (None, "1111111111", "9781111111113")),
        ("", (None, None, None)),
    ],
)
def test_normalize_identifier(identifier, expected) -> None:
    got = normalize_identifier(identifier)
    assert got == expected
