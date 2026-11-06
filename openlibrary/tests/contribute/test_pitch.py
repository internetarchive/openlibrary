from types import SimpleNamespace

import pytest

from openlibrary.contribute import initiatives, pitch
from openlibrary.core.jinja import render_jinja_template
from openlibrary.plugins.openlibrary.contribute import build_edit_saved, initiative_copy
from openlibrary.utils.request_context import RequestContextVars, req_context

MOST_READ, TAGS = initiatives.MOST_READ, initiatives.TAGS


def rows(initiative, count=1, first_key="/books/OL1M"):
    """``count`` books on ``initiative``'s list, each with one of its fields still open."""
    return [[first_key if i == 0 else f"/books/OL{i + 1}M", 9, [initiative.fields[0]], []] for i in range(count)]


@pytest.fixture(autouse=True)
def english():
    token = req_context.set(RequestContextVars(x_forwarded_for=None, user_agent=None, lang="en", solr_editions=False, print_disabled=False))
    yield
    req_context.reset(token)


@pytest.fixture
def gaps(monkeypatch):
    def set_gaps(by_slug):
        monkeypatch.setattr(initiatives, "get_gaps", lambda initiative: by_slug.get(initiative.slug))

    return set_gaps


def test_encode_leads_with_the_headline_initiative_and_counts_tasks_left(gaps):
    gaps({MOST_READ.slug: rows(MOST_READ, 2), TAGS.slug: rows(TAGS)})
    assert pitch.encode() == f"{MOST_READ.slug}:2,{TAGS.slug}:1"


def test_encode_leads_with_the_initiative_that_lists_the_saved_book(gaps):
    gaps({MOST_READ.slug: rows(MOST_READ, 2), TAGS.slug: rows(TAGS, first_key="/books/OL9M")})
    assert pitch.encode(["/books/OL9M"]) == f"{TAGS.slug}:1,{MOST_READ.slug}:2"


def test_a_saved_book_with_nothing_left_for_the_initiative_does_not_reorder(gaps):
    done = [["/books/OL9M", 9, [], []], *rows(TAGS)]
    gaps({MOST_READ.slug: rows(MOST_READ), TAGS.slug: done})
    assert pitch.encode(["/books/OL9M"]).startswith(MOST_READ.slug)


def test_encode_drops_a_finished_initiative(gaps):
    gaps({MOST_READ.slug: [["/books/OL1M", 9, [], []]], TAGS.slug: rows(TAGS)})
    assert pitch.encode() == f"{TAGS.slug}:1"
    gaps({MOST_READ.slug: [], TAGS.slug: []})
    assert pitch.encode() == ""


def test_encode_keeps_a_list_that_is_still_being_built_without_a_count(gaps):
    gaps({})
    assert pitch.encode() == f"{MOST_READ.slug}:,{TAGS.slug}:"


def test_past_three_initiatives_the_last_slot_is_see_all(gaps, monkeypatch):
    extra = [initiatives.Initiative(f"extra-{i}", 10, initiatives.pick_most_shelved, MOST_READ.fields) for i in range(2)]
    monkeypatch.setattr(initiatives, "INITIATIVES", (MOST_READ, TAGS, *extra))
    gaps({i.slug: rows(i) for i in initiatives.INITIATIVES})
    payload = pitch.encode()
    assert payload == f"{MOST_READ.slug}:1,{TAGS.slug}:1,{pitch.MORE}"
    saved = build_edit_saved(payload)
    assert [p.slug for p in saved.projects] == [MOST_READ.slug, TAGS.slug]
    assert saved.more


def test_banner_links_each_initiative_with_its_tasks_left():
    saved = build_edit_saved(f"{TAGS.slug}:3760,{MOST_READ.slug}:485")
    assert [(p.slug, p.url, p.left) for p in saved.projects] == [
        (TAGS.slug, f"/tasks?initiative={TAGS.slug}", "3,760\xa0left"),
        (MOST_READ.slug, "/tasks", "485\xa0left"),
    ]
    assert saved.projects[1].title == initiative_copy(MOST_READ)["title"]
    assert not saved.more
    assert saved.dismiss_cookie == pitch.dismiss_cookie()


@pytest.mark.parametrize("payload", ["", "no-such-initiative:5", "<script>:1", ":", pitch.MORE])
def test_banner_is_the_thank_you_alone_when_nothing_names_an_initiative(payload):
    assert build_edit_saved(payload) == pitch.EditSaved()


def test_banner_trusts_nothing_in_a_forged_cookie():
    saved = build_edit_saved(",".join([f"{MOST_READ.slug}:<b>", f"{MOST_READ.slug}:99999999", "bogus:1"] + [f"{TAGS.slug}:1"] * 20))
    assert len(saved.projects) == pitch.MAX_LINKS
    assert [p.left for p in saved.projects[:2]] == ["", ""]
    assert {p.slug for p in saved.projects} == {MOST_READ.slug, TAGS.slug}


def test_wanted_until_seen_today_or_closed():
    assert pitch.wanted({})
    assert not pitch.wanted({pitch.SEEN_COOKIE: "1"})
    assert not pitch.wanted({pitch.dismiss_cookie(): "1"})


def test_a_new_initiative_brings_a_closed_pitch_back(monkeypatch):
    closed = {pitch.dismiss_cookie(): "1"}
    monkeypatch.setattr(
        initiatives, "INITIATIVES", (*initiatives.INITIATIVES, initiatives.Initiative("new-one", 10, initiatives.pick_most_shelved, MOST_READ.fields))
    )
    assert pitch.wanted(closed)


def render(saved):
    return render_jinja_template("shell/edit_saved.html.jinja", layout=SimpleNamespace(edit_saved=saved))


def test_banner_links_each_project_and_remembers_being_closed():
    html = render(build_edit_saved(f"{MOST_READ.slug}:485,{TAGS.slug}:"))
    assert "Thank you for improving the Open Library catalog!" in html
    assert f'dismiss-id="{pitch.dismiss_cookie()}"' in html
    assert "data-dismiss-on-link" in html
    assert 'href="/tasks"' in html
    assert 'count="485\xa0left"' in html
    assert f'href="/tasks?initiative={TAGS.slug}"' in html
    # A list still being built is named without a count.
    assert html.count("count=") == 1
    assert "See all projects" not in html


def test_banner_is_the_thank_you_alone_without_projects():
    html = render(pitch.EditSaved())
    assert "Thank you for improving the Open Library catalog!" in html
    assert "ol-chip" not in html
    assert "dismiss-id" not in html


def test_no_banner_without_an_edit_saved_flash():
    assert render(None).strip() == ""
