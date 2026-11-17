import web

from openlibrary.plugins.openlibrary import contribute


class FakeUser:
    key = "/people/reader"


def test_member_skips_intro_after_clicking_through_or_saving_a_task(monkeypatch):
    monkeypatch.setattr(web, "cookies", dict)
    assert not contribute.has_seen_intro([])

    monkeypatch.setattr(web, "cookies", lambda: {contribute.INTRO_COOKIE: "1"})
    assert contribute.has_seen_intro([])

    monkeypatch.setattr(web, "cookies", dict)
    assert contribute.has_seen_intro([object()])


def test_member_cta_goes_to_a_task_and_dismisses_the_intro():
    cta = contribute.build_cta(FakeUser())
    assert cta["href"] == "/tasks/one"
    assert [link["href"] for link in cta["secondary"]] == ["/tasks"]
    assert cta["intro"] == {"cookie": contribute.INTRO_COOKIE, "days": contribute.INTRO_COOKIE_DAYS}


def test_visitor_cta_asks_for_an_account_and_never_sets_the_cookie():
    cta = contribute.build_cta(None)
    assert cta["href"].startswith("/account/create")
    assert cta["intro"] is None


def test_rail_links_only_the_initiative_s_own_filters():
    tracks = [f["track"] for f in contribute.build_filter_rail("", contribute.initiatives.MOST_READ)["filters"]]
    assert tracks == ["covers", "languages", "number_of_pages", "publishers"]
    # Every filter still works by URL.
    assert contribute.normalize_filter("identifiers") == "identifiers"
    tag_rail = contribute.build_filter_rail("", contribute.initiatives.TAGS)
    assert [f["track"] for f in tag_rail["filters"]] == ["literary_forms", "genres"]
    assert tag_rail["all"]["url"] == "/tasks?initiative=genres-2026-11"
    assert tag_rail["filters"][1]["url"] == "/tasks?initiative=genres-2026-11&task=genres"


def test_filter_chips_count_the_open_tasks_in_their_fields():
    gaps = [["/books/OL1M", 9, ["covers", "languages"], []], ["/books/OL2M", 3, ["covers", "lccn"], ["publishers"]]]
    rail = contribute.build_filter_rail("covers", contribute.initiatives.MOST_READ, gaps)
    # lccn isn't one of the initiative's fields, and a field nobody could find isn't open.
    assert rail["all"]["count"] == "3"
    assert {f["track"]: f["count"] for f in rail["filters"]} == {"covers": "2", "languages": "1", "number_of_pages": "0", "publishers": "0"}
    assert rail["filters"][0]["on"] is True
    # While the gaps build there's nothing to count.
    assert contribute.build_filter_rail("", contribute.initiatives.MOST_READ)["all"]["count"] == ""


def test_urls_name_the_initiative_only_when_it_is_not_the_headline_one():
    assert contribute.initiative_param(contribute.initiatives.MOST_READ) == ""
    assert contribute.get_initiative("") is contribute.initiatives.MOST_READ
    assert contribute.get_initiative("nope") is contribute.initiatives.MOST_READ
    assert contribute.get_initiative("genres-2026-11") is contribute.initiatives.TAGS
    task = contribute.tasks.Task("OL1M", "genres")
    assert contribute.build_task_url(task, "genres", "genres-2026-11") == "/tasks/task/OL1M/genres?back=genres&initiative=genres-2026-11"
    assert (
        contribute.build_next_url("", task, saved=True, initiative="genres-2026-11")
        == "/tasks/one?initiative=genres-2026-11&field=genres&exclude=OL1M&saved=OL1M%2Fgenres"
    )
    assert contribute.build_done_url("OL1M", "genres", "saved", "", "") == "/tasks/task/OL1M/genres/done?choice=saved"
