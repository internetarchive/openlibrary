"""Saving a work task: the literary form, the genres, and the two together as one edit."""

from types import SimpleNamespace

import pytest
import web

from openlibrary.contribute import save, tasks
from openlibrary.plugins.openlibrary import contribute
from openlibrary.utils.request_context import site as site_context

FICTION = "/tags/OL1T"


@pytest.fixture
def saved(monkeypatch):
    """A site whose ``save`` records what it was given, with every /tags/OL…T key a known tag."""
    calls = []
    monkeypatch.setattr(save, "find_tag", lambda fld, key: key.startswith("/tags/OL"))
    monkeypatch.setattr(web.ctx, "site", SimpleNamespace(save=lambda doc, **kw: calls.append({"doc": doc} | kw)), raising=False)
    site_context.set(web.ctx.site)
    return calls


def work():
    return SimpleNamespace(dict=lambda: {"key": "/works/OL1W", "title": "T"})


def test_both_answers_save_as_one_revision_in_the_order_picked_without_repeats(saved):
    save.save_work_answers(work(), {"literary_forms": [FICTION], "genres": ["/tags/OL3T", "/tags/OL2T", "/tags/OL3T"]}, "Literary form and Genres")
    [call] = saved
    assert call["doc"] == {"key": "/works/OL1W", "title": "T", "literary_forms": [{"key": FICTION}], "genres": [{"key": "/tags/OL3T"}, {"key": "/tags/OL2T"}]}
    assert call["comment"] == "Filled in Literary form and Genres from Open Library Tasks"
    assert call["action"] == "edit-book"
    assert call["data"] == {"source": "contribute", "field": "literary_forms", "fields": ["literary_forms", "genres"]}


def test_a_genre_answer_alone_names_only_itself(saved):
    save.save_work_answers(work(), {"genres": ["/tags/OL2T"]}, "Genres", note="From the back cover")
    assert saved[0]["doc"]["genres"] == [{"key": "/tags/OL2T"}]
    assert saved[0]["comment"] == "From the back cover"
    assert saved[0]["data"] == {"source": "contribute", "field": "genres", "fields": ["genres"]}


def test_a_save_names_the_initiative_it_counts_toward(saved):
    save.save_work_answers(work(), {"genres": ["/tags/OL2T"]}, "Genres", initiative="genres-2026-11")
    assert saved[0]["data"] == {"source": "contribute", "field": "genres", "initiative": "genres-2026-11", "fields": ["genres"]}
    save.save_answer(SimpleNamespace(dict=dict, get=lambda k: None), "publishers", "Penguin", "Publisher", initiative="most-read-2026-11")
    assert saved[1]["data"] == {"source": "contribute", "field": "publishers", "initiative": "most-read-2026-11"}


def test_empty_and_unknown_picks_are_refused(saved):
    with pytest.raises(save.InvalidAnswer, match="at least one genre"):
        save.save_work_answers(work(), {"genres": ["", "  "]}, "Genres")
    with pytest.raises(save.InvalidAnswer, match="one of the options"):
        save.save_work_answers(work(), {"literary_forms": [""]}, "Literary form")
    with pytest.raises(save.InvalidAnswer, match="one of the options"):
        save.save_work_answers(work(), {"genres": ["/nope"]}, "Genres")
    assert saved == []


@pytest.fixture
def fiction_opens_genres(monkeypatch):
    monkeypatch.setattr(contribute, "tag_key_named", lambda fld, name: FICTION if name == "fiction" else None)


def test_the_genres_ride_along_with_a_fiction_answer_when_the_book_is_open_for_them(monkeypatch, fiction_opens_genres):
    monkeypatch.setattr(tasks, "task_for", lambda edition, fld: tasks.Task("OL1M", fld))
    i = SimpleNamespace(value=FICTION, genres=["/tags/OL2T"])
    assert contribute.build_work_answers({}, "literary_forms", i) == {"literary_forms": [FICTION], "genres": ["/tags/OL2T"]}
    # Nonfiction has no genres, whatever the chips say; the picks are dropped rather than saved.
    assert contribute.build_work_answers({}, "literary_forms", SimpleNamespace(value="/tags/OL9T", genres=["/tags/OL2T"])) == {"literary_forms": ["/tags/OL9T"]}
    assert contribute.build_work_answers({}, "genres", SimpleNamespace(value="", genres=["/tags/OL2T"])) == {"genres": ["/tags/OL2T"]}


def test_the_genres_stay_home_when_the_work_already_has_some(monkeypatch, fiction_opens_genres):
    monkeypatch.setattr(tasks, "task_for", lambda edition, fld: None)
    i = SimpleNamespace(value=FICTION, genres=["/tags/OL2T"])
    assert contribute.build_work_answers({}, "literary_forms", i) == {"literary_forms": [FICTION]}


def test_the_edit_comment_names_both_fields():
    assert contribute.answers_label(["literary_forms", "genres"]) == "Literary form and Genres"
    assert contribute.answers_label(["genres"]) == "Genres"


@pytest.fixture(autouse=True)
def restore_site_context():
    token = site_context.set(site_context.get(None))
    yield
    site_context.reset(token)
