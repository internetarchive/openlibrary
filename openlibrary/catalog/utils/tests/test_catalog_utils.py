import pytest

from openlibrary.catalog.utils import author_dates_match

EXISTING = {"birth_date": "1904", "death_date": "1996"}


MATCH_CASES = [
    {"birth_date": "1904", "death_date": "1996"},
    {"death_date": "1996"},
    {"birth_date": "1904"},
]


NON_MATCH_CASES = [
    {"birth_date": "1794", "death_date": "1823"},
    {"birth_date": "1904", "death_date": "2005"},  # one date mismatch
]


@pytest.mark.parametrize("a", MATCH_CASES)
def test_author_dates_match_true(a):
    assert author_dates_match(a, EXISTING)


@pytest.mark.parametrize("a", NON_MATCH_CASES)
def test_author_dates_match_false(a):
    assert not author_dates_match(a, EXISTING)


def test_author_dates_match_death_only():
    a = {"death_date": "1996"}
    b = {"death_date": "1996"}
    assert author_dates_match(a, b)
