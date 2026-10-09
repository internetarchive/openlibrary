import pytest

from openlibrary.first_edits import ranking, supply, tasks
from openlibrary.first_edits.scope import parse_scope
from openlibrary.first_edits.tasks import Task

SCOPE = parse_scope(
    {
        "fields": {
            "languages": {"enabled": True, "points": 15},
            "number_of_pages": {"enabled": False, "points": 10},
            "publishers": {"enabled": True, "points": 2},
            "lccn": {"enabled": True, "points": 25},
        }
    }
)


class FakeEdition(dict):
    key = "/books/OL1M"


def _task(fld):
    return Task("/books/OL1M", "OL1M", fld)


def test_missing_query_ors_the_fields_it_can_filter():
    q = supply.missing_query(("languages", "number_of_pages", "lccn"))
    assert q == "type:edition AND isbn:* AND ((*:* -language:*) OR (*:* -lccn:*))"


def test_tasks_are_the_enabled_empty_fields_most_valuable_first():
    ed = FakeEdition(publishers=[], languages=None, lccn=["75425165"])
    assert [t.field for t in tasks.tasks_for_edition(ed, SCOPE)] == ["languages", "publishers"]


def test_points_come_from_scope():
    assert ranking.task_points(_task("lccn"), SCOPE) == 25
    assert ranking.task_points(_task("subtitle"), SCOPE) == 0


def test_impact_is_readers_times_points():
    assert ranking.impact(100, _task("publishers"), SCOPE) == 200
    assert ranking.impact(None, _task("languages"), SCOPE) == 15


def test_scope_rejects_bad_points():
    with pytest.raises(ValueError, match="points for languages"):
        parse_scope({"fields": {"languages": {"enabled": True, "points": -1}}})
