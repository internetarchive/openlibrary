import pytest

from openlibrary.first_edits import identifiers
from openlibrary.utils.oclc import normalize_oclc


@pytest.fixture(autouse=True)
def _lang(monkeypatch):
    # gettext needs a request language; these tests only care about structure.
    for mod in ("identifiers", "tasks"):
        monkeypatch.setattr(f"openlibrary.first_edits.{mod}._", lambda s, **kw: s % kw if kw else s)


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


def _display(fld, value):
    return ", ".join(str(v) for v in value) if isinstance(value, list) else str(value or "")


OURS = {"publish_date": "2002", "publishers": ["HarperCollins"], "number_of_pages": 323, "languages": ["eng"]}


def test_match_rows_flag_a_different_printing():
    theirs = {"publish_date": "1988", "publishers": ["Warner Books"], "number_of_pages": 281, "languages": ["eng"]}
    rows = identifiers.match_rows(OURS, theirs, _display)
    check = identifiers.check_match(rows)
    assert check.state == "fail"
    assert "year" in check.message
    assert "publisher" in check.message


def test_match_rows_pass_when_the_record_is_this_edition():
    rows = identifiers.match_rows(OURS, dict(OURS), _display)
    assert identifiers.check_match(rows).state == "pass"
    assert all(r.agrees for r in rows)


def test_match_is_only_a_warning_when_there_is_nothing_to_compare():
    assert identifiers.check_match(identifiers.match_rows(OURS, {}, _display)).state == "warn"


class _Ed(dict):
    """Just enough of an edition for the collision scan."""

    key = "/books/OL1M"

    def get(self, k, default=None):
        return dict.get(self, k, default)


def test_collision_with_a_sibling_edition_is_a_hard_fail():
    spec = identifiers.get_specs()["oclc_numbers"]
    sibling = _Ed(oclc_numbers=["ocm00047810608"])  # same number, different form
    assert identifiers.check_collision(spec, "47810608", [sibling]).state == "fail"
    assert identifiers.check_collision(spec, "999", [sibling]).state == "pass"


def test_format_check_names_the_url_mistake():
    spec = identifiers.get_specs()["oclc_numbers"]
    value, check = identifiers.check_format(spec, "not a number/at all")
    assert value is None
    assert check.state == "fail"
    assert "web address" in check.message


def test_worst_state_is_the_gate():
    ok = identifiers.Check("a", "pass", "")
    warn = identifiers.Check("b", "warn", "")
    bad = identifiers.Check("c", "fail", "")
    assert identifiers.worst_state([ok, ok]) == "pass"
    assert identifiers.worst_state([ok, warn]) == "warn"
    assert identifiers.worst_state([ok, warn, bad]) == "fail"
