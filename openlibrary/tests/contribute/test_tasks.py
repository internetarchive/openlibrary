from openlibrary.contribute import supply, tasks
from openlibrary.contribute.tasks import Task


class FakeEdition(dict):
    key = "/books/OL1M"


def test_missing_query_ors_the_fields_it_can_filter():
    q = supply.missing_query(("languages", "number_of_pages", "lccn"))
    assert q == "type:edition AND isbn:* AND ((*:* -language:*) OR (*:* -lccn:*))"


def test_missing_cover_also_skips_scanned_books():
    q = supply.missing_query(("covers",))
    assert q == "type:edition AND isbn:* AND ((*:* -cover_i:* -ia:*))"


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


def test_solr_candidates_are_none_while_the_picks_build_and_empty_for_unlisted_fields(monkeypatch):
    monkeypatch.setattr(supply.pool, "get", lambda *a, **kw: None)
    assert supply.solr_candidates(("languages",)) is None
    assert list(supply.solr_candidates(("number_of_pages",))) == []


def test_solr_candidates_are_empty_not_pending_when_the_picks_came_back_empty(monkeypatch):
    monkeypatch.setattr(supply.pool, "get", lambda *a, **kw: [])
    assert list(supply.solr_candidates(("languages",))) == []
