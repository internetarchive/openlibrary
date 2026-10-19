"""Inline task page: the multi-language save path and the record/receipt builders.

The inline page (``/tasks/languages``) lets a librarian put more than one language on an edition at once,
so ``save.answer_value`` for languages must accept a comma-separated list of codes, not a single value.
"""

import pytest
import web

from openlibrary.contribute import save


@pytest.fixture
def fake_languages(monkeypatch):
    """Three languages, keyed by code, as ``get_languages`` returns them (web.storage behaves like a Thing)."""
    langs = {
        f"/languages/{code}": web.storage(key=f"/languages/{code}", name=name, code=code)
        for code, name in [
            ("eng", "English"),
            ("fre", "French"),
            ("spa", "Spanish"),
            ("enm", "English, Middle (1100-1500)"),  # a real MARC language name that contains a comma
        ]
    }
    monkeypatch.setattr(save, "get_languages", lambda: langs)
    return langs


def test_one_language_resolves_to_one_key(fake_languages):
    assert save.answer_value({}, "languages", "eng") == [{"key": "/languages/eng"}]


def test_a_language_name_resolves_too(fake_languages):
    assert save.answer_value({}, "languages", "French") == [{"key": "/languages/fre"}]


def test_multiple_languages_keep_their_order(fake_languages):
    assert save.answer_value({}, "languages", "eng,fre") == [
        {"key": "/languages/eng"},
        {"key": "/languages/fre"},
    ]


def test_a_language_name_containing_a_comma_resolves_whole(fake_languages):
    # Split-on-comma-first would break the 14 real language names that contain a comma; a single
    # name must resolve as one language, not as fragments.
    assert save.answer_value({}, "languages", "English, Middle (1100-1500)") == [{"key": "/languages/enm"}]


def test_duplicate_languages_are_dropped(fake_languages):
    assert save.answer_value({}, "languages", "eng,eng,fre") == [
        {"key": "/languages/eng"},
        {"key": "/languages/fre"},
    ]


def test_whitespace_and_empty_parts_are_ignored(fake_languages):
    assert save.answer_value({}, "languages", " eng , , fre ") == [
        {"key": "/languages/eng"},
        {"key": "/languages/fre"},
    ]


def test_an_unknown_language_in_the_list_is_rejected(fake_languages):
    with pytest.raises(save.InvalidAnswer):
        save.answer_value({}, "languages", "eng,klingon")


def test_an_all_empty_value_is_rejected(fake_languages):
    with pytest.raises(save.InvalidAnswer):
        save.answer_value({}, "languages", " , ")
