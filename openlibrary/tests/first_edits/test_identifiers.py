import pytest

from openlibrary.first_edits import identifiers
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
    assert identifiers.normalize_lccn_value(raw) == expected


def test_normalized_drops_unusable_values():
    assert identifiers.normalized("oclc_numbers", ["ocm0004781", "junk"]) == ["4781"]
    assert identifiers.normalized("lccn", None) == []
