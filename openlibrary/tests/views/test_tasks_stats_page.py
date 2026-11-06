"""Tests for the numbers /stats/tasks renders server-side (openlibrary.views.loanstats)."""

import pytest

from openlibrary.contribute import initiatives
from openlibrary.core import admin
from openlibrary.fastapi import stats
from openlibrary.utils.request_context import RequestContextVars, req_context
from openlibrary.views import loanstats


@pytest.fixture
def request_lang():
    token = req_context.set(RequestContextVars(x_forwarded_for=None, user_agent=None, lang="en", solr_editions=False, print_disabled=False))
    yield
    req_context.reset(token)


def test_change_reads_as_a_percentage_with_a_direction():
    assert loanstats.format_change(120, 100) == {"direction": "up", "text": "20.0%"}
    assert loanstats.format_change(90, 100) == {"direction": "down", "text": "10.0%"}
    assert loanstats.format_change(100, 100)["direction"] == "flat"


def test_change_needs_an_earlier_count():
    assert loanstats.format_change(5, None) is None
    assert loanstats.format_change(5, 0) is None
    assert loanstats.format_change(None, 5) is None


def test_cards_show_dashes_until_the_counts_exist():
    cards = loanstats.build_tasks_stats_cards({"tasks_saves_28d": {"latest": 1200, "earlier": 1000}})
    assert [c["metric"] for c in cards] == ["editors", "new_editors", "saves", "tasks_editors"]
    assert cards[0]["value"] == "—"
    assert cards[0]["change"] is None
    assert cards[2]["value"] == "1,200"


def test_guardrail_compares_tasks_with_the_same_fields_filled_elsewhere():
    counts = {
        "tasks_saves_undone_28d": {"latest": 6},
        "tasks_saves_28d": {"latest": 50},
        "other_fills_undone_28d": {"latest": 2},
        "other_fills_28d": {"latest": 40},
    }
    guardrail = loanstats.build_guardrail(counts)
    assert guardrail["tasks"] == {"undone": "6", "total": "50", "share": "12.0%"}
    assert guardrail["other"] == {"undone": "2", "total": "40", "share": "5.0%"}


def test_guardrail_hides_a_share_with_too_few_saves_behind_it():
    counts = {"tasks_saves_undone_28d": {"latest": 6}, "tasks_saves_28d": {"latest": 19}}
    guardrail = loanstats.build_guardrail(counts)
    assert guardrail["tasks"] == {"undone": "6", "total": "19", "share": None}
    assert guardrail["other"]["share"] is None


MOST_READ, TAGS = initiatives.MOST_READ, initiatives.TAGS


def test_initiative_counts_read_the_nested_snapshot_and_the_older_flat_keys():
    nested = {"initiatives": {TAGS.slug: {"open": 5}}, "initiative_slug": MOST_READ.slug, "initiative_open_gaps": 9}
    assert admin.initiative_counts(nested) == {TAGS.slug: {"open": 5}}
    flat = {"initiative_slug": MOST_READ.slug, "initiative_open_gaps": 9, "initiative_people": 4}
    assert admin.initiative_counts(flat) == {MOST_READ.slug: {"open": 9, "people": 4}}
    assert admin.initiative_counts({"saves": 3}) == {}


def test_every_initiative_gets_a_card_headline_first_selected(request_lang):
    projects = loanstats.build_initiatives([])
    assert [p["slug"] for p in projects] == [i.slug for i in initiatives.INITIATIVES]
    assert [p["on"] for p in projects] == [i is initiatives.ACTIVE for i in initiatives.INITIATIVES]
    assert all(p["percent"] == "—" for p in projects)


def test_initiative_percent_counts_every_field_it_asks_about_on_every_book(request_lang):
    # 2 books x 4 fields = 8 slots, 3 open: 62%, rounded down
    docs = [{"initiative_slug": MOST_READ.slug, "initiative_open_gaps": 3, "initiative_editions": 2, "initiative_done_editions": 1}]
    most_read = loanstats.build_initiatives(docs)[0]
    assert len(MOST_READ.fields) == 4
    assert (most_read["percent"], most_read["done"], most_read["not_found"]) == ("62%", "1", "—")


def test_each_initiative_reads_its_own_latest_snapshot(request_lang):
    docs = [
        {"initiatives": {TAGS.slug: {"open": 10, "editions": 5, "people": 1}}},
        {"initiatives": {MOST_READ.slug: {"open": 2, "editions": 2, "people": 1200}}},
    ]
    by_slug = {p["slug"]: p for p in loanstats.build_initiatives(docs)}
    assert by_slug[MOST_READ.slug]["open"] == "2"
    assert by_slug[MOST_READ.slug]["people"] == "<b>1,200</b> people have helped"
    # Today's doc has no genres snapshot yet, so yesterday's stands.
    assert by_slug[TAGS.slug]["open"] == "10"
    assert by_slug[TAGS.slug]["people"] == "<b>1</b> person has helped"


def test_series_has_a_line_per_initiative_aligned_to_the_days():
    days = [{}, {"initiative_slug": MOST_READ.slug, "initiative_open_gaps": 9}, {"initiatives": {MOST_READ.slug: {"open": 8}, TAGS.slug: {"open": 40}}}]
    assert stats.initiative_series(days) == {MOST_READ.slug: [None, 9, 8], TAGS.slug: [None, None, 40]}


def test_saves_by_field_add_up_across_days_most_first():
    docs = [
        {"tasks_saves_by_field_1d": {"publishers": 1, "number_of_pages": 2}},
        {},
        {"tasks_saves_by_field_1d": {"number_of_pages": 5, "mystery_field": 2}},
    ]
    rows = loanstats.build_saves_by_field(docs)
    assert [(r["label"], r["count"], r["share"], r["width"]) for r in rows] == [
        ("Page count", "7", "70%", 100),
        ("mystery_field", "2", "20%", 29),
        ("Publisher", "1", "10%", 14),
    ]
    assert loanstats.build_saves_by_field([]) == []
