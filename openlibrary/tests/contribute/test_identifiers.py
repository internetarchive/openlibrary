import pytest

from openlibrary.contribute import save
from openlibrary.utils.oclc import normalize_oclc


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("47810608", "47810608"),
        ("  47810608 ", "47810608"),
        ("ocm00047810608", "47810608"),  # fixed-width padding from a library system
        ("ocn071369523", "71369523"),
        ("on1234567", "1234567"),
        ("(OCoLC)1052587398", "1052587398"),  # straight out of MARC 035
        ("https://search.worldcat.org/title/47810608", "47810608"),
        ("0", None),
        ("abc", None),
        ("", None),
    ],
)
def test_normalize_oclc(raw, expected):
    assert normalize_oclc(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2001016794", "2001016794"),
        ("  2001016794 ", "2001016794"),
        ("75-425165", "75425165"),  # hyphenated form is the same number
        ("https://lccn.loc.gov/94013429", "94013429"),
        ("lccn:86046157", "86046157"),
        ("nonsense", None),
    ],
)
def test_normalize_lccn_value(raw, expected):
    assert save.normalize_lccn_value(raw) == expected


def test_normalized_drops_unusable_values():
    assert save.normalized("oclc_numbers", ["ocm0004781", "junk"]) == ["4781"]
    assert save.normalized("lccn", None) == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("9780140449266", "9780140449266"),
        ("978-0-14-044926-6", "9780140449266"),
        (" 0 14 044926 4 ", "0140449264"),
        ("080442957x", "080442957X"),  # a check digit of ten is an X
        ("9780140449267", None),  # wrong check digit
        ("0140449265", None),
        ("12345", None),
        ("", None),
    ],
)
def test_normalize_isbn_value(raw, expected):
    assert save.normalize_isbn_value(raw) == expected


class FakeEdition(dict):
    key = "/books/OL1M"


def test_an_isbn_answer_goes_under_the_key_for_its_length(monkeypatch):
    monkeypatch.setattr(save, "editions_with_isbn", lambda isbn: [])
    assert save.answer_changes(FakeEdition(), "isbn", "978-0-14-044926-6") == {"isbn_13": ["9780140449266"]}
    assert save.answer_changes(FakeEdition(isbn_10=["0306406152"]), "isbn", "0140449264") == {"isbn_10": ["0306406152", "0140449264"]}


def test_an_isbn_already_on_another_edition_is_refused(monkeypatch):
    monkeypatch.setattr(save, "editions_with_isbn", lambda isbn: ["/books/OL1M", "/books/OL7M"])
    with pytest.raises(save.InvalidAnswer, match="OL7M"):
        save.answer_changes(FakeEdition(), "isbn", "9780140449266")
    with pytest.raises(save.InvalidAnswer, match="valid ISBN"):
        save.answer_changes(FakeEdition(), "isbn", "9780140449267")


@pytest.mark.parametrize(("raw", "expected"), [("2005", "2005"), ("  March   2005 ", "March 2005"), ("c1987", "c1987")])
def test_a_publish_date_is_kept_as_typed(raw, expected):
    assert save.answer_changes(FakeEdition(), "publish_date", raw) == {"publish_date": expected}


@pytest.mark.parametrize(("raw", "match"), [("March", "with its year"), ("85", "with its year"), ("1066", "doesn't look right"), ("9999", "doesn't look right")])
def test_a_publish_date_needs_a_plausible_year(raw, match):
    with pytest.raises(save.InvalidAnswer, match=match):
        save.answer_changes(FakeEdition(), "publish_date", raw)
