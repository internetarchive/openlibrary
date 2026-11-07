import pytest

from openlibrary.plugins.openlibrary import contribute
from openlibrary.utils.request_context import RequestContextVars, req_context

SLUG = contribute.initiatives.ACTIVE.slug
# One open task out of the four offered on one book.
GAPS = [["/books/OL1M", 9, ["covers"], []]]


@pytest.fixture
def progress(monkeypatch):
    token = req_context.set(RequestContextVars(x_forwarded_for=None, user_agent=None, lang="en", solr_editions=False, print_disabled=False))

    def build(gaps=GAPS, docs=()):
        monkeypatch.setattr(contribute.initiatives, "get_gaps", lambda: gaps)
        monkeypatch.setattr(contribute.admin, "get_count_docs", lambda ndays: list(docs))
        return contribute.build_progress()

    yield build
    req_context.reset(token)


def test_none_while_the_gaps_are_being_built(progress):
    assert progress(gaps=None) is None


def test_tasks_left_uses_the_plural_and_groups_thousands(progress):
    assert progress()["tasks_left"] == "<b>1</b> task left"
    many = [[f"/books/OL{i}M", 9, ["covers", "languages"], []] for i in range(600)]
    assert progress(gaps=many)["tasks_left"] == "<b>1,200</b> tasks left"


@pytest.mark.parametrize(
    ("people", "expected"),
    [
        (contribute.MIN_PEOPLE_SHOWN - 1, None),
        (contribute.MIN_PEOPLE_SHOWN, f"{contribute.MIN_PEOPLE_SHOWN} people have helped so far"),
        (1200, "1,200 people have helped so far"),
    ],
)
def test_people_line_hides_low_counts(progress, people, expected):
    assert progress(docs=[{"initiative_slug": SLUG, "initiative_people": people}])["people"] == expected


def test_people_line_waits_for_the_stats_job(progress):
    assert progress()["people"] is None
    assert progress(docs=[{"saves": 3}])["people"] is None


def test_people_prefers_todays_count_and_falls_back_to_yesterdays(progress):
    yesterday = {"initiative_slug": SLUG, "initiative_people": 8}
    assert progress(docs=[yesterday, {"initiative_slug": SLUG, "initiative_people": 9}])["people"] == "9 people have helped so far"
    assert progress(docs=[yesterday, {"saves": 3}])["people"] == "8 people have helped so far"


def test_people_from_another_initiative_dont_carry_over(progress):
    assert progress(docs=[{"initiative_slug": "an-older-list", "initiative_people": 50}])["people"] is None
