import json
from datetime import datetime

import pytest

from openlibrary.plugins.worksearch.sort_menu import SortMenu, with_query

NOW = datetime(2026, 1, 2, 3, 4, 5)


def build(selected_sort, path="/search", params=None, **kwargs) -> SortMenu:
    return SortMenu.build(selected_sort, path=path, params=params if params is not None else {"q": "tolkien"}, now=NOW, **kwargs)


def test_with_query_changes_and_drops_keys():
    params = {"q": "a b&c", "page": "3", "sort": "new"}
    assert with_query("/search", params, page=None, sort="old") == "/search?q=a+b%26c&sort=old"
    assert with_query("/search", {"page": "2"}, page=None) == "/search"
    # The caller's params are left alone
    assert params == {"q": "a b&c", "page": "3", "sort": "new"}


def test_works_menu_defaults_to_relevance_and_links_drop_page():
    menu = build(None, params={"q": "tolkien", "page": "2"})
    assert (menu.selected_value, menu.selected_label) == ("relevance", "Relevance")
    urls = {item.value: item.url for item in menu.items}
    # The default sort carries no sort param, and every link goes back to page 1
    assert urls["relevance"] == "/search?q=tolkien"
    assert urls["new"] == "/search?q=tolkien&sort=new"
    assert menu.shuffle_href is None


def test_reading_log_sub_sorts_are_nested_without_repeating_the_parent():
    menu = build("want_to_read")
    assert menu.selected_label == "Want to Read"
    reading_log = [item for item in menu.items if item.track.startswith("ReadingLog")]
    assert [(i.value, i.nested) for i in reading_log] == [
        ("readinglog", False),
        ("want_to_read", True),
        ("currently_reading", True),
        ("already_read", True),
        ("stopped_reading", True),
    ]
    assert all(i.track == "ReadingLogSubSort" for i in reading_log[1:])


def test_items_json_matches_what_sort_options_js_reads():
    items = json.loads(build("want_to_read").items_json)
    assert items[0] == {"value": "relevance", "label": "Relevance", "url": "/search?q=tolkien", "track": "Relevance"}
    nested = next(i for i in items if i["value"] == "want_to_read")
    assert list(nested) == ["value", "label", "nested", "url", "track"]


@pytest.mark.parametrize("is_bot", [False, True])
def test_random_sort_selects_random_and_offers_shuffle_to_people(is_bot):
    menu = build("random_123", is_bot=is_bot)
    assert menu.selected_value == "random"
    assert menu.shuffle_href == (None if is_bot else f"/search?q=tolkien&sort=random_{NOW.timestamp()}")


def test_unknown_sort_falls_back_to_the_default():
    menu = build("nonsense", scheme="languages", default_sort="count")
    assert (menu.selected_value, menu.selected_label) == ("count", "Work Count")


@pytest.mark.parametrize(
    ("scheme", "selected", "beta", "beta_key"),
    [
        ("works", None, False, None),
        ("works", None, True, "title"),
        ("works", "title", False, "title"),  # already sorted by it, so it stays visible
        ("authors", None, True, "birth_date asc"),
        ("authors", "birth_date desc", False, "birth_date asc"),
    ],
)
def test_beta_sorts_show_for_librarians_or_when_selected(scheme, selected, beta, beta_key):
    values = [item.value for item in build(selected, scheme=scheme, can_see_beta_sorts=beta).items]
    beta_values = {"title", "birth_date asc"}
    assert [v for v in values if v in beta_values] == ([beta_key] if beta_key else [])


def test_exclude_keeps_templetors_in_test():
    # The author page passes a string; reading log passes a list
    assert "relevance" not in [i.value for i in build(None, exclude="relevance", default_sort="editions").items]
    menu = build(None, scheme="reading_log", default_sort="desc", exclude=["rating", "want_to_read"])
    assert [i.value for i in menu.items] == ["desc", "asc", "title", "old"]
