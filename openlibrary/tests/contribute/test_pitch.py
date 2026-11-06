from types import SimpleNamespace

import pytest
from markupsafe import Markup

from openlibrary.contribute import initiatives, pitch
from openlibrary.core.jinja import get_jinja_env, render_jinja_template
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


def test_encode_names_the_headline_initiative_with_its_tasks_left(gaps):
    gaps({MOST_READ.slug: rows(MOST_READ, 2), TAGS.slug: rows(TAGS)})
    assert pitch.encode() == f"{MOST_READ.slug}:2"


def test_encode_prefers_the_initiative_that_lists_the_saved_book(gaps):
    gaps({MOST_READ.slug: rows(MOST_READ, 2), TAGS.slug: rows(TAGS, first_key="/books/OL9M")})
    assert pitch.encode(["/books/OL9M"]) == f"{TAGS.slug}:1"


def test_a_saved_book_with_nothing_left_for_the_initiative_does_not_win(gaps):
    done = [["/books/OL9M", 9, [], []], *rows(TAGS)]
    gaps({MOST_READ.slug: rows(MOST_READ), TAGS.slug: done})
    assert pitch.encode(["/books/OL9M"]) == f"{MOST_READ.slug}:1"


def test_encode_skips_a_finished_initiative(gaps):
    gaps({MOST_READ.slug: [["/books/OL1M", 9, [], []]], TAGS.slug: rows(TAGS)})
    assert pitch.encode() == f"{TAGS.slug}:1"
    gaps({MOST_READ.slug: [], TAGS.slug: []})
    assert pitch.encode() == ""


def test_encode_names_a_list_that_is_still_being_built_without_a_count(gaps):
    gaps({})
    assert pitch.encode() == f"{MOST_READ.slug}:"


def test_banner_links_the_initiative_with_its_tasks_left():
    saved = build_edit_saved(f"{TAGS.slug}:3760")
    assert (saved.project.slug, saved.project.url, saved.project.left) == (TAGS.slug, f"/tasks?initiative={TAGS.slug}", "3,760\xa0tasks\xa0left")
    assert saved.dismiss_cookie == pitch.dismiss_cookie()
    headline = build_edit_saved(f"{MOST_READ.slug}:485").project
    assert (headline.url, headline.left, headline.title) == ("/tasks", "485\xa0tasks\xa0left", initiative_copy(MOST_READ)["title"])


@pytest.mark.parametrize("payload", ["", "no-such-initiative:5", "<script>:1", ":"])
def test_banner_is_the_thank_you_alone_when_nothing_names_an_initiative(payload):
    assert build_edit_saved(payload) == pitch.EditSaved()


@pytest.mark.parametrize("count", ["<b>", "99999999", "-5", f"1,{TAGS.slug}:2"])
def test_banner_shows_no_count_it_cannot_trust(count):
    """The flash message comes back in a cookie, so a count that isn't a plain number is dropped."""
    project = build_edit_saved(f"{MOST_READ.slug}:{count}").project
    assert (project.slug, project.left) == (MOST_READ.slug, "")


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


@pytest.fixture
def render(monkeypatch):
    # The icon macro is Templetor's, which these tests don't load.
    monkeypatch.setitem(get_jinja_env().globals, "icon", lambda name, **kw: Markup(f'<svg data-icon="{name}"></svg>'))
    return lambda saved: render_jinja_template("shell/edit_saved.html.jinja", layout=SimpleNamespace(edit_saved=saved))


def test_banner_links_the_project_and_remembers_being_closed(render):
    html = render(build_edit_saved(f"{TAGS.slug}:485"))
    assert "Thank you for improving the Open Library catalog!" in html
    assert 'data-icon="circle-check"' in html
    assert f'dismiss-id="{pitch.dismiss_cookie()}"' in html
    assert "data-dismiss-on-link" in html
    assert html.count("<ol-chip") == 1
    assert f'href="/tasks?initiative={TAGS.slug}"' in html
    assert 'count="485\xa0tasks\xa0left"' in html


def test_banner_names_a_list_still_being_built_without_a_count(render):
    html = render(build_edit_saved(f"{MOST_READ.slug}:"))
    assert 'href="/tasks"' in html
    assert "count=" not in html


def test_banner_is_the_thank_you_alone_without_a_project(render):
    html = render(pitch.EditSaved())
    assert "Thank you for improving the Open Library catalog!" in html
    assert "ol-chip" not in html
    assert "dismiss-id" not in html


def test_no_banner_without_an_edit_saved_flash(render):
    assert render(None).strip() == ""
