"""The genre page's hints: the subjects that name a genre outline its chip and show emphasized on the record."""

from types import SimpleNamespace

import pytest

from openlibrary.contribute import tasks
from openlibrary.plugins.openlibrary import contribute

HORROR = "/tags/OL2T"
FANTASY = "/tags/OL3T"


@pytest.fixture
def genres(monkeypatch):
    """A genre vocabulary of two, with Horror named by any "horror" subject."""
    options = [{"value": HORROR, "label": "Horror"}, {"value": FANTASY, "label": "Fantasy"}]
    monkeypatch.setattr(contribute, "tag_options", lambda fld: options)
    monkeypatch.setattr(
        contribute, "subject_matches", lambda fld, subjects: {HORROR: hits} if (hits := [s for s in subjects if "horror" in s.casefold()]) else {}
    )
    monkeypatch.setattr(contribute, "work_tag_names", lambda work, fld: [])


class FakeEdition(dict):
    @property
    def works(self):
        return self["works"]


def edition(*subjects):
    work = SimpleNamespace(get=lambda k, default=None: {"subjects": list(subjects)}.get(k, default), get_edition_count=lambda: 1)
    return FakeEdition(works=[work])


def test_the_subjects_behind_a_hint_show_emphasized_in_the_record(genres):
    rows = contribute.build_work_field_rows(edition("Horror stories", "Monsters"), "genres", hits=["Horror stories"])
    [subjects] = [r for r in rows if r["label"] == "Subjects"]
    assert subjects["parts"] == [{"text": "Horror stories", "hit": True}, {"text": "Monsters", "hit": False}]
    # Without a hint the row is plain text, as before.
    rows = contribute.build_work_field_rows(edition("Monsters"), "genres")
    assert "parts" not in next(r for r in rows if r["label"] == "Subjects")


def test_the_hinted_chips_carry_their_reasons_but_are_not_picked(genres):
    many = contribute.build_many(contribute.get_field_guides()["genres"], selected=[FANTASY], suggested={HORROR: ["Horror stories", "Ghost stories"]})
    assert many["suggested"] == {HORROR: {"subjects": ["Horror stories", "Ghost stories"], "why": "Subjects mention “Horror stories”, “Ghost stories”"}}
    assert many["selected"] == [FANTASY]


def test_the_hints_come_from_the_subjects_on_the_genre_page_and_the_form_page(genres, monkeypatch):
    assert contribute.genre_hints(edition("Horror stories", "Monsters")) == {HORROR: ["Horror stories"]}
    assert contribute.genre_hints(FakeEdition(works=[])) == {}
    # The companion genres on the literary form page carry the same hints.
    monkeypatch.setattr(tasks, "task_for", lambda ed, fld: tasks.Task("OL1M", fld))
    companion = contribute.build_companion(edition("Horror"), "literary_form", [], suggested={HORROR: ["Horror"]})
    assert companion["field"] == "genres"
    assert companion["suggested"][HORROR]["subjects"] == ["Horror"]
