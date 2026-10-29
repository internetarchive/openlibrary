from openlibrary.contribute import supply, tasks
from openlibrary.contribute.tasks import Task


class FakeEdition(dict):
    key = "/books/OL1M"


def test_tasks_are_the_empty_fields_most_valuable_first():
    ed = FakeEdition(covers=[1], publishers=[], languages=None, lccn=["75425165"], number_of_pages=320)
    assert [t.field for t in tasks.tasks_for_edition(ed)] == ["oclc_numbers", "languages", "publishers"]
    ed["covers"] = []
    assert tasks.tasks_for_edition(ed)[0].field == "covers"


def test_a_cover_is_missing_with_only_deleted_covers_but_not_on_a_scanned_book():
    assert tasks.is_missing(FakeEdition(covers=[-1]), "covers")
    assert not tasks.is_missing(FakeEdition(covers=[-1, 8478242]), "covers")
    assert not tasks.is_missing(FakeEdition(ocaid="goody"), "covers")


def test_impact_is_readers_times_points():
    assert tasks.impact(100, Task("OL1M", "publishers")) == 200
    assert tasks.impact(None, Task("OL1M", "languages")) == 15
    assert tasks.impact(5, Task("OL1M", "subtitle")) == 0


def test_candidates_are_none_while_the_gaps_build(monkeypatch):
    monkeypatch.setattr(supply.initiatives, "get_gaps", lambda: None)
    assert supply.candidates(("languages",)) is None


def test_candidates_are_the_editions_with_an_open_gap_in_the_fields(monkeypatch):
    gaps = [
        ["/books/OL1M", 10, ["languages"], []],
        ["/books/OL2M", 20, ["publishers"], ["lccn"]],
        ["/books/OL3M", 30, [], ["languages"]],
    ]
    monkeypatch.setattr(supply.initiatives, "get_gaps", lambda: gaps)
    loaded = []
    monkeypatch.setattr(supply, "_load", lambda picks, batch: loaded.extend(picks) or iter(()))
    list(supply.candidates(("languages", "publishers")))
    assert sorted(loaded) == [["/books/OL1M", 10, []], ["/books/OL2M", 20, ["lccn"]]]
