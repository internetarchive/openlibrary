import pytest

from openlibrary.contribute import initiatives, supply, tasks
from openlibrary.contribute.tasks import Task

NONFICTION = "/tags/OL9T"


class FakeEdition(dict):
    key = "/books/OL1M"


class FakeWork(dict):
    key = "/works/OL1W"


@pytest.fixture(autouse=True)
def nonfiction_by_key(monkeypatch):
    """Spare the tests a site: a work is nonfiction when its literary form is the NONFICTION key."""
    monkeypatch.setattr(tasks, "is_nonfiction", lambda work: work.get("literary_forms") == [NONFICTION])


def test_tasks_are_the_empty_fields_most_valuable_first():
    ed = FakeEdition(covers=[1], publishers=[], languages=None, lccn=["75425165"], number_of_pages=320)
    assert [t.field for t in tasks.tasks_for_edition(ed)] == ["oclc_numbers", "languages", "publishers"]
    ed["covers"] = []
    assert tasks.tasks_for_edition(ed)[0].field == "covers"


def test_the_literary_form_is_a_task_on_the_edition_when_its_work_has_none():
    work = FakeWork()
    ed = FakeEdition(works=[work])
    assert tasks.is_missing(ed, "literary_forms")
    assert tasks.is_missing(ed, "literary_forms", work=FakeWork(literary_forms=[{"key": "/tags/OL1T"}])) is False
    # A bare key, as the tags migration stored genres, counts as filled too.
    work["literary_forms"] = "/tags/OL1T"
    assert not tasks.is_missing(ed, "literary_forms")
    # An orphan edition has no work to put the answer on.
    assert not tasks.is_missing(FakeEdition(), "literary_forms")


def test_genres_are_a_task_until_the_work_has_some_or_is_nonfiction():
    ed = FakeEdition(works=[FakeWork()])
    assert tasks.is_missing(ed, "genres")
    assert tasks.is_missing(ed, "genres", work=FakeWork(literary_forms=["/tags/OL1T"]))
    assert not tasks.is_missing(ed, "genres", work=FakeWork(genres=["/tags/OL2T"]))
    # The genre vocabulary is for fiction: a nonfiction work has nothing to fill in.
    assert not tasks.is_missing(ed, "genres", work=FakeWork(literary_forms=[NONFICTION]))
    assert not tasks.is_missing(FakeEdition(), "genres")


def test_the_genres_follow_the_literary_form_as_its_companion():
    assert tasks.COMPANIONS == {"literary_forms": "genres"}
    assert {"literary_forms", "genres"} == tasks.WORK_FIELDS


def test_a_cover_is_missing_with_only_deleted_covers_but_not_on_a_scanned_book():
    assert tasks.is_missing(FakeEdition(covers=[-1]), "covers")
    assert not tasks.is_missing(FakeEdition(covers=[-1, 8478242]), "covers")
    assert not tasks.is_missing(FakeEdition(ocaid="goody"), "covers")


def test_impact_is_readers_times_points():
    assert tasks.impact(100, Task("OL1M", "publishers")) == 200
    assert tasks.impact(None, Task("OL1M", "languages")) == 15
    assert tasks.impact(5, Task("OL1M", "subtitle")) == 0


def test_candidates_are_none_while_the_gaps_build(monkeypatch):
    monkeypatch.setattr(supply.initiatives, "get_gaps", lambda initiative: None)
    assert supply.candidates(initiatives.MOST_READ, ("languages",)) is None


def test_candidates_are_the_initiative_s_editions_with_an_open_gap_in_the_fields(monkeypatch):
    gaps = [
        ["/books/OL1M", 10, ["languages"], []],
        ["/books/OL2M", 20, ["publishers"], ["lccn"]],
        ["/books/OL3M", 30, [], ["languages"]],
    ]
    asked = []
    monkeypatch.setattr(supply.initiatives, "get_gaps", lambda initiative: asked.append(initiative) or gaps)
    loaded = []
    monkeypatch.setattr(supply, "_load", lambda picks, batch: loaded.extend(picks) or iter(()))
    list(supply.candidates(initiatives.TAGS, ("languages", "publishers")))
    assert asked == [initiatives.TAGS]
    assert sorted(loaded) == [["/books/OL1M", 10, []], ["/books/OL2M", 20, ["lccn"]]]
