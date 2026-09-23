import pytest

from openlibrary.first_edits import fixtures, practice


@pytest.fixture(autouse=True)
def _lang(monkeypatch):
    monkeypatch.setattr("openlibrary.first_edits.evidence._", lambda s, **kw: s % kw if kw else s)
    monkeypatch.setattr("openlibrary.first_edits.sources._", lambda s, **kw: s % kw if kw else s)


def test_suggestion_matches_truth_on_the_strong_practice():
    p = fixtures.get_practice("ruptured-publisher")
    assert practice.judge(p, "suggestion", "").outcome == "correct"
    assert practice.judge(p, "unsure", "").outcome == "unsure"
    assert practice.judge(p, "other", "Penguin").outcome == "wrong"


def test_keep_is_right_when_ol_already_agrees():
    p = fixtures.get_practice("beloved-publisher")
    assert practice.judge(p, "keep", "").outcome == "correct"
    assert practice.judge(p, "other", "Knopf").outcome == "correct"
    assert practice.judge(p, "other", "Vintage").outcome == "wrong"


def test_conflict_practice_accepts_the_imprint():
    p = fixtures.get_practice("gatsby-publisher")
    assert practice.judge(p, "source:loc", "").outcome == "correct"
    assert practice.judge(p, "source:googlebooks", "").outcome == "wrong"
    assert practice.judge(p, "other", "Scribner").outcome == "correct"


def test_next_practice_walks_in_order():
    keys = [p["key"] for p in fixtures.load_practice()]
    assert practice.next_practice(keys[0])["key"] == keys[1]
    assert practice.next_practice(keys[-1]) is None
