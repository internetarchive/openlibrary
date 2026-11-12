import pytest

from openlibrary.plugins.openlibrary import contribute
from openlibrary.utils.request_context import RequestContextVars, req_context

ACTIVE = contribute.initiatives.MOST_READ
# One open task out of the fields the initiative asks about, on one book.
GAPS = [["/books/OL1M", 9, [ACTIVE.fields[0]], []]]


@pytest.fixture
def cards(monkeypatch):
    token = req_context.set(RequestContextVars(x_forwarded_for=None, user_agent=None, lang="en", solr_editions=False, print_disabled=False))

    def build(gaps=GAPS, docs=()):
        monkeypatch.setattr(contribute.initiatives, "get_gaps", lambda initiative: gaps)
        monkeypatch.setattr(contribute.admin, "get_count_docs", lambda ndays: list(docs))
        return {card["slug"]: card for card in contribute.build_initiative_cards(ACTIVE)}

    yield build
    req_context.reset(token)


def test_only_the_open_initiative_is_on(cards):
    built = cards()
    assert [slug for slug, card in built.items() if card["on"]] == [ACTIVE.slug]
    assert len(built) == len(contribute.initiatives.BUILTIN)


def test_blank_while_the_gaps_are_being_built(cards):
    card = cards(gaps=None)[ACTIVE.slug]
    assert card["percent"] is None
    assert card["tasks_left"] == ""
    assert card["people"] is None


def test_tasks_left_uses_the_plural_and_groups_thousands(cards):
    assert cards()[ACTIVE.slug]["tasks_left"] == "1 task left"
    many = [[f"/books/OL{i}M", 9, list(ACTIVE.fields[:2]), []] for i in range(600)]
    assert cards(gaps=many)[ACTIVE.slug]["tasks_left"] == "1,200 tasks left"


@pytest.mark.parametrize(
    ("people", "expected"),
    [
        (contribute.MIN_PEOPLE_SHOWN - 1, None),
        (contribute.MIN_PEOPLE_SHOWN, f"{contribute.MIN_PEOPLE_SHOWN} people helping"),
        (1200, "1,200 people helping"),
    ],
)
def test_people_line_hides_low_counts(cards, people, expected):
    assert cards(docs=[{"initiative_slug": ACTIVE.slug, "initiative_people": people}])[ACTIVE.slug]["people"] == expected


def test_people_line_waits_for_the_stats_job(cards):
    assert cards()[ACTIVE.slug]["people"] is None
    assert cards(docs=[{"saves": 3}])[ACTIVE.slug]["people"] is None


def test_people_prefers_todays_count_and_falls_back_to_yesterdays(cards):
    yesterday = {"initiative_slug": ACTIVE.slug, "initiative_people": 8}
    assert cards(docs=[yesterday, {"initiative_slug": ACTIVE.slug, "initiative_people": 9}])[ACTIVE.slug]["people"] == "9 people helping"
    assert cards(docs=[yesterday, {"saves": 3}])[ACTIVE.slug]["people"] == "8 people helping"


def test_people_read_from_the_nested_snapshot(cards):
    other = next(i for i in contribute.initiatives.BUILTIN if i is not ACTIVE)
    built = cards(docs=[{"initiatives": {ACTIVE.slug: {"people": 6}, other.slug: {"people": 12}}}])
    assert built[ACTIVE.slug]["people"] == "6 people helping"
    assert built[other.slug]["people"] == "12 people helping"


def test_people_count_goes_to_the_initiative_it_names(cards):
    other = next(i for i in contribute.initiatives.BUILTIN if i is not ACTIVE)
    built = cards(docs=[{"initiative_slug": other.slug, "initiative_people": 50}])
    assert built[ACTIVE.slug]["people"] is None
    assert built[other.slug]["people"] == "50 people helping"


ENDED = {"slug": "october-sprint", "title": "October Sprint", "fields": ["covers"], "starts_at": "2026-10-01", "ends_at": "2026-10-31", "size": 3}


@pytest.fixture
def ended(cards, monkeypatch):
    monkeypatch.setattr(contribute.initiatives, "cached_definitions", lambda: [ENDED])
    return next(i for i in contribute.initiatives.listed() if i.slug == ENDED["slug"])


def test_a_finished_project_comes_last_and_says_how_it_finished(cards, ended):
    built = cards()
    assert list(built)[-1] == ended.slug
    assert (built[ended.slug]["finished"], built[ended.slug]["finished_label"]) == (True, "Finished · 0% filled")
    assert built[ACTIVE.slug]["finished"] is False
    assert cards(gaps=None)[ended.slug]["finished_label"] == "Finished"


def test_a_finished_project_shows_a_closing_note_and_the_project_to_go_to(cards, ended):
    built = cards()
    assert contribute.build_finished(built[ACTIVE.slug]) is None
    finished = contribute.build_finished(built[ended.slug])
    assert finished["note"] == "0% of its details were filled in. Thank you to everyone who helped."
    assert (finished["next_url"], finished["next_label"]) == ("/tasks", "Go to Fill the Gaps")
    crowd = cards(docs=[{"initiatives": {ended.slug: {"people": 12}}}])[ended.slug]
    assert contribute.build_finished(crowd)["note"] == "12 people filled in 0% of its details. Thank you."


def test_the_fine_print_of_a_finished_project_says_when_it_ran(cards, ended):
    site = type("Site", (), {"store": {ended.store_key: {"frozen_at": "2026-10-01T00:00:00+00:00"}}})()
    assert contribute.initiatives.fine_print(ended, site) == "3 books · Ran October 1, 2026 to October 30, 2026"
