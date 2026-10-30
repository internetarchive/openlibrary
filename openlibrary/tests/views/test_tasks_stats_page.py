"""Tests for the numbers /stats/tasks renders server-side (openlibrary.views.loanstats)."""

from openlibrary.views import loanstats


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


def test_undone_share_is_of_saves_in_the_same_window():
    undone = loanstats.build_undone({"tasks_saves_undone_28d": {"latest": 6}, "tasks_saves_28d": {"latest": 50}})
    assert undone == {"undone": "6", "saves": "50", "share": "12.0%"}
    assert loanstats.build_undone({})["share"] == "—"


def test_initiative_percent_counts_every_field_on_every_book():
    counts = {key: {"latest": value} for key, value in {"initiative_open_gaps": 3, "initiative_editions": 2, "initiative_done_editions": 1}.items()}
    # 2 books x 6 fields = 12 slots, 3 open: 75%
    initiative = loanstats.build_initiative(counts)
    assert initiative["percent"] == "75%"
    assert initiative["done"] == "1"
    assert initiative["not_found"] == "—"
    assert loanstats.build_initiative({})["percent"] == "—"


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
