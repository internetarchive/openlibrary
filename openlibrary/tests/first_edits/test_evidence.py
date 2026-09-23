import pytest

from openlibrary.first_edits import fixtures
from openlibrary.first_edits.evidence import build_field_evidence
from openlibrary.first_edits.scope import load_scope, parse_scope

GB = {
    "id": "googlebooks",
    "match": "isbn13",
    "url": "https://books.google.com/x",
    "fields": {"publishers": ["Harvard University Press"], "number_of_pages": 406, "languages": ["eng"]},
}
LOC = {
    "id": "loc",
    "match": "isbn13",
    "url": "https://lccn.loc.gov/x",
    "fields": {"publishers": ["Harvard University Press"], "number_of_pages": 384, "languages": ["eng"]},
}


@pytest.fixture(autouse=True)
def _lang(monkeypatch):
    # gettext needs a request language; the tests only care about structure.
    monkeypatch.setattr("openlibrary.first_edits.evidence._", lambda s, **kw: s % kw if kw else s)
    monkeypatch.setattr("openlibrary.first_edits.sources._", lambda s, **kw: s % kw if kw else s)


def test_missing_with_two_agreeing_sources_is_strong_fill():
    ev = build_field_evidence("publishers", {"publishers": []}, {"sources": [GB, LOC]})
    assert ev.verdict == "missing"
    assert ev.level == "strong"
    assert ev.mode == "fill"
    assert ev.suggestion_display == "Harvard University Press"
    assert ev.suggestion_sources == ["googlebooks", "loc"]
    assert ev.sentence.startswith("Strong")


def test_sources_that_disagree_become_conflict_with_no_suggestion():
    ev = build_field_evidence("number_of_pages", {"number_of_pages": None}, {"sources": [GB, LOC]})
    assert ev.verdict == "conflict"
    assert ev.mode is None
    assert ev.suggestion_display == ""
    assert ev.sentence.startswith("Needs judgment")


def test_single_source_is_fair():
    ev = build_field_evidence("publishers", {"publishers": ["HarperPerennial ModernClassics"]}, {"sources": [LOC]})
    assert ev.level == "fair"
    assert ev.verdict == "differs"
    assert ev.mode == "check"
    assert ev.values[0].agrees_with_ol is False


def test_agreeing_ol_value_is_confirm():
    ev = build_field_evidence("publishers", {"publishers": ["Harvard Univ. Press"]}, {"sources": [GB, LOC]})
    assert ev.verdict == "agrees"
    assert ev.mode == "confirm"


def test_no_sources_is_unverifiable():
    ev = build_field_evidence("subtitle", {"subtitle": None}, {"sources": []})
    assert ev.verdict == "unverifiable"
    assert ev.level == "none"


def test_language_display_uses_names():
    ev = build_field_evidence("languages", {"languages": []}, {"sources": [GB, LOC]}, {"eng": "English"})
    assert ev.suggestion_display == "English"


def test_scope_file_parses_and_rejects_unknowns():
    scope = load_scope()
    assert "publishers" in scope.enabled_fields()
    assert scope.fields["publishers"].allows("fill", "strong")
    assert not scope.fields["subtitle"].allows("fill", "strong")
    with pytest.raises(ValueError, match="unknown field"):
        parse_scope({"fields": {"isbn": {"enabled": True}}})
    with pytest.raises(ValueError, match="unknown mode"):
        parse_scope({"fields": {"publishers": {"enabled": True, "modes": ["merge"]}}})


def test_fixtures_load_and_practice_has_truth():
    assert fixtures.load_demo_books()
    for book in fixtures.load_demo_books():
        assert fixtures.load_evidence(book["isbn13"]) is not None
    for practice in fixtures.load_practice():
        assert practice["truth"]
        assert set(practice["verdicts"]) == {"correct", "unsure", "wrong"}
