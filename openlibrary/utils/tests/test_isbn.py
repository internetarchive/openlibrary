import pytest
from openlibrary.utils.isbn import (
    isbn_10_to_isbn_13,
    isbn_13_to_isbn_10,
    normalize_isbn,
    opposite_isbn,
    hyphenate_isbn,
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


@pytest.mark.parametrize('isbnlike,expected', isbn_cases)
def test_normalize_isbn(isbnlike, expected):
    assert normalize_isbn(isbnlike) == expected


hyphenation_cases = [
    ('344203275X', '3-442-03275-X'),  # ISBN10 with X
    ('344203275x', '3-442-03275-X'),  # ISBN10 with lowercase x, X is capitalised
    ('3442-0327-5X', '3-442-03275-X'),  # re-hyphenate bad
    ('9780108646980', '978-0-10-864698-0'),  # good ISBN13
    ('multi046', 'multi046'),  # Invalid unchanged
    ('915502175', '915502175'),  # Invalid unchanged
    ('0860941569', '0860941569'),  # Invalid unchanged
    ('', ''),  # Empty
    # Valid checkdigits but unhyphenatable @ isbnlib==3.10.10:
    ('9786400042628', '9786400042628'),
    ('9789999334525', '9789999334525'),
]


@pytest.mark.parametrize('isbn,expected', hyphenation_cases)
def test_hyphenate_isbn(isbn, expected):
    assert hyphenate_isbn(isbn) == expected


@pytest.mark.xfail(
    reason="isbnlib will not hyphenate invalid checkdigit ISBNs, even when hyphenation rules exist."
)
def test_hyphenate_invalid_checkdigit():
    assert hyphenate_isbn('1841151866') == '1-84115-186-6'
    assert hyphenate_isbn('184115186X') == '1-84115-186-X'
