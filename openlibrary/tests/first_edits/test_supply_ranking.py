import pytest

from openlibrary.first_edits import ranking, supply
from openlibrary.first_edits.scope import parse_scope
from openlibrary.first_edits.tasks import Task


@pytest.fixture(autouse=True)
def _lang(monkeypatch):
    monkeypatch.setattr("openlibrary.first_edits.supply._", lambda s, **kw: s % kw if kw else s)


class FakeEdition:
    def __init__(self, key, isbn13=None):
        self.key = key
        self._isbn = isbn13

    def get_isbn13(self):
        return self._isbn


def test_pick_edition_prefers_the_logged_one(monkeypatch):
    monkeypatch.setattr(supply.fixtures, "load_evidence", lambda isbn: {"sources": []} if isbn == "9780000000002" else None)
    eds = [FakeEdition("/books/OL1M", "9780000000001"), FakeEdition("/books/OL2M", "9780000000002"), FakeEdition("/books/OL3M", "9780000000003")]
    assert supply.pick_edition(eds, "/books/OL3M").key == "/books/OL3M"


def test_pick_edition_falls_back_to_evidence_then_isbn(monkeypatch):
    monkeypatch.setattr(supply.fixtures, "load_evidence", lambda isbn: {"sources": []} if isbn == "9780000000002" else None)
    eds = [FakeEdition("/books/OL1M", "9780000000001"), FakeEdition("/books/OL2M", "9780000000002")]
    assert supply.pick_edition(eds, None).key == "/books/OL2M"
    monkeypatch.setattr(supply.fixtures, "load_evidence", lambda isbn: None)
    assert supply.pick_edition(eds, None).key == "/books/OL1M"
    assert supply.pick_edition([FakeEdition("/books/OL9M")], None) is None


def test_split_logged_keeps_logged_editions_with_evidence_and_scans_the_rest():
    rows = [
        supply.LoggedRow("/works/OL1W", "/books/OL1M", "already-read"),  # logged edition, evidence
        supply.LoggedRow("/works/OL2W", "/books/OL2M", "already-read"),  # logged edition, no evidence
        supply.LoggedRow("/works/OL3W", None, "want-to-read"),  # no edition logged
        supply.LoggedRow("/works/OL4W", "/books/OL4M", "currently-reading"),  # edition record missing
    ]
    isbn_of = {"/books/OL1M": "9780000000001", "/books/OL2M": "9780000000002", "/books/OL4M": None}
    ready, scan = supply.split_logged(rows, isbn_of, frozenset({"9780000000001"}))
    assert [r.work_key for r in ready] == ["/works/OL1W"]
    assert [r.work_key for r in scan] == ["/works/OL2W", "/works/OL3W", "/works/OL4W"]


SCOPE = parse_scope(
    {
        "fields": {
            "languages": {"enabled": True, "modes": ["fill"], "points": 15},
            "publishers": {"enabled": True, "modes": ["fill", "check"], "points": 2},
            "lccn": {"enabled": True, "modes": ["fill"], "min_level": "strong", "points": 25},
        }
    }
)


def _task(fld):
    return Task("/books/OL1M", "OL1M", fld, "fill", evidence=None)


def test_points_come_from_scope():
    assert ranking.task_points(_task("lccn"), SCOPE) == 25
    assert ranking.top_points([_task("publishers"), _task("languages")], SCOPE) == 15
    assert ranking.top_points([], SCOPE) == 0


def test_impact_orders_by_readers_times_best_task():
    rows = [
        (supply.Candidate(None, readers=100), [_task("publishers")]),  # 200
        (supply.Candidate(None, readers=10), [_task("lccn")]),  # 250
        (supply.Candidate(None, readers=None), [_task("languages")]),  # 15
    ]
    ordered = ranking.order_rows(rows, "impact", SCOPE)
    assert [r[0].readers for r in ordered] == [10, 100, None]


def test_points_ordering_keeps_groups_then_ignores_readers_and_is_stable():
    rows = [
        (supply.Candidate(None, readers=1000, group=0), [_task("publishers")]),
        (supply.Candidate(None, readers=None, group=1), [_task("lccn")]),  # higher points, later shelf
        (supply.Candidate(None, readers=None, group=0), [_task("languages")]),
        (supply.Candidate(None, readers=None, group=0), [_task("publishers")]),
    ]
    ordered = ranking.order_rows(rows, "points", SCOPE)
    assert [r[1][0].field for r in ordered] == ["languages", "publishers", "publishers", "lccn"]
    assert ordered[1][0].readers == 1000


def test_scope_rejects_bad_points():
    with pytest.raises(ValueError, match="points for languages"):
        parse_scope({"fields": {"languages": {"enabled": True, "modes": ["fill"], "points": -1}}})
