import pytest

from openlibrary.plugins.openlibrary import contribute
from openlibrary.utils.request_context import RequestContextVars, req_context

ACTIVE = contribute.initiatives.ACTIVE
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
    assert len(built) == len(contribute.initiatives.INITIATIVES)


def test_blank_while_the_gaps_are_being_built(cards):
    card = cards(gaps=None)[ACTIVE.slug]
    assert card["percent"] is None
    assert card["tasks_left"] == ""
    assert card["people"] is None


def test_tasks_left_uses_the_plural_and_groups_thousands(cards):
    assert cards()[ACTIVE.slug]["tasks_left"] == "<b>1</b> task left"
    many = [[f"/books/OL{i}M", 9, list(ACTIVE.fields[:2]), []] for i in range(600)]
    assert cards(gaps=many)[ACTIVE.slug]["tasks_left"] == "<b>1,200</b> tasks left"


@pytest.mark.parametrize(
    ("people", "expected"),
    [
        (contribute.MIN_PEOPLE_SHOWN - 1, None),
        (contribute.MIN_PEOPLE_SHOWN, f"{contribute.MIN_PEOPLE_SHOWN} people have helped"),
        (1200, "1,200 people have helped"),
    ],
)
def test_people_line_hides_low_counts(cards, people, expected):
    assert cards(docs=[{"initiative_slug": ACTIVE.slug, "initiative_people": people}])[ACTIVE.slug]["people"] == expected


def test_people_line_waits_for_the_stats_job(cards):
    assert cards()[ACTIVE.slug]["people"] is None
    assert cards(docs=[{"saves": 3}])[ACTIVE.slug]["people"] is None


def test_people_prefers_todays_count_and_falls_back_to_yesterdays(cards):
    yesterday = {"initiative_slug": ACTIVE.slug, "initiative_people": 8}
    assert cards(docs=[yesterday, {"initiative_slug": ACTIVE.slug, "initiative_people": 9}])[ACTIVE.slug]["people"] == "9 people have helped"
    assert cards(docs=[yesterday, {"saves": 3}])[ACTIVE.slug]["people"] == "8 people have helped"


def test_people_read_from_the_nested_snapshot(cards):
    other = next(i for i in contribute.initiatives.INITIATIVES if i is not ACTIVE)
    built = cards(docs=[{"initiatives": {ACTIVE.slug: {"people": 6}, other.slug: {"people": 12}}}])
    assert built[ACTIVE.slug]["people"] == "6 people have helped"
    assert built[other.slug]["people"] == "12 people have helped"


def test_people_count_goes_to_the_initiative_it_names(cards):
    other = next(i for i in contribute.initiatives.INITIATIVES if i is not ACTIVE)
    built = cards(docs=[{"initiative_slug": other.slug, "initiative_people": 50}])
    assert built[ACTIVE.slug]["people"] is None
    assert built[other.slug]["people"] == "50 people have helped"
