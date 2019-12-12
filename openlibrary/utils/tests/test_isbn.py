import pytest
from openlibrary.utils.isbn import isbn_10_to_isbn_13, isbn_13_to_isbn_10, \
    normalize_isbn, opposite_isbn

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
        ('56', '56'), # does NOT check length
]

@pytest.mark.parametrize('isbnlike,expected', isbn_cases)
def test_normalize_isbn(isbnlike, expected):
    assert normalize_isbn(isbnlike) == expected
