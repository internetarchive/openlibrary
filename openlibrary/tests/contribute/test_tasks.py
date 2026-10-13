from openlibrary.contribute import supply, tasks
from openlibrary.contribute.tasks import Task


class FakeEdition(dict):
    key = "/books/OL1M"


def test_missing_query_ors_the_fields_it_can_filter():
    q = supply.missing_query(("languages", "number_of_pages", "lccn"))
    assert q == "type:edition AND isbn:* AND ((*:* -language:*) OR (*:* -lccn:*))"


def test_tasks_are_the_empty_fields_most_valuable_first():
    ed = FakeEdition(publishers=[], languages=None, lccn=["75425165"], number_of_pages=320)
    assert [t.field for t in tasks.tasks_for_edition(ed)] == ["oclc_numbers", "languages", "publishers"]


def test_impact_is_readers_times_points():
    assert tasks.impact(100, Task("OL1M", "publishers")) == 200
    assert tasks.impact(None, Task("OL1M", "languages")) == 15
    assert tasks.impact(5, Task("OL1M", "subtitle")) == 0
