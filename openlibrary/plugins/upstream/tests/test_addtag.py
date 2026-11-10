"""Tests for openlibrary.plugins.upstream.addtag."""

import pytest
import web

from openlibrary.core.models import Tag
from openlibrary.plugins.upstream import addtag
from openlibrary.plugins.upstream.addtag import (
    SUBJECT_SUB_TYPES,
    TAG_TYPES,
    parse_slugs,
    tag_edit,
    validate_subject_tag,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Horror", "horror"),
        ("  cooking  ", "cooking"),
        ("Science Fiction", "science_fiction"),
        ("[Horror]", "horror"),
        ("!@<Horror>;:", "!horror"),
        ("!@(Horror);:", "!(horror)"),
        ("", ""),
    ],
)
def test_tag_normalize(name, expected):
    assert Tag.normalize(name) == expected


@pytest.mark.parametrize(
    ("name", "slugs_input", "expected"),
    [
        ("Computer Science", "", ["computer_science"]),
        ("Computer Science", "cs", ["computer_science", "cs"]),
        ("Horror", "horror, scary", ["horror", "scary"]),
        ("Horror", "HORROR", ["horror"]),  # deduped after normalize
        ("Horror", "  ", ["horror"]),  # whitespace-only input ignored
    ],
)
def test_parse_slugs(name, slugs_input, expected):
    assert parse_slugs(name, slugs_input) == expected


@pytest.mark.parametrize(
    "tag_type",
    ["genre", "subgenre", "content_format", "literary_form", "mood"],
)
def test_new_subject_sub_types_in_subject_sub_types(tag_type):
    assert tag_type in SUBJECT_SUB_TYPES


@pytest.mark.parametrize(
    "tag_type",
    ["genre", "subgenre", "content_format", "literary_form", "mood"],
)
def test_new_subject_sub_types_in_tag_types(tag_type):
    assert tag_type in TAG_TYPES


@pytest.mark.parametrize(
    "tag_type",
    ["genre", "subgenre", "content_format", "literary_form", "mood"],
)
def test_new_types_pass_validate_subject_tag(tag_type):
    """New tag types must pass validate_subject_tag so edits are accepted."""
    data = web.storage(
        name="Thriller",
        tag_type=tag_type,
        tag_description="A description",
        body="Some body content",
        slugs=["thriller"],
    )
    assert validate_subject_tag(data)


@pytest.mark.parametrize(
    "tag_type",
    ["genre", "subgenre", "content_format", "literary_form", "mood"],
)
def test_tag_edit_validate_accepts_new_types(tag_type):
    """tag_edit.validate must accept new subject tag types so saving slugs works."""
    handler = tag_edit()
    data = web.storage(
        name="Thriller",
        tag_type=tag_type,
        tag_description="A description",
        body="Some body content",
        slugs=["thriller"],
    )
    assert handler.validate(data, tag_type)


def test_tag_edit_delete_skips_form_validation(monkeypatch):
    """A bare `_delete` POST must delete the tag without a full, valid tag form."""
    key = "/tags/OL1T"
    saved = {}

    class FakeDoc:
        def __init__(self, data):
            self.data = data

        def _save(self, comment=None, action=None):
            saved.update(data=self.data, comment=comment, action=action)

    class FakeSite:
        def get(self, k):
            return web.storage(key=k, tag_type="subject")

        def new(self, k, data):
            return FakeDoc(data)

    class Redirect(Exception):
        pass

    monkeypatch.setattr(web.ctx, "site", FakeSite(), raising=False)
    monkeypatch.setattr(web, "input", lambda **kw: web.storage(kw, _delete="true", _comment="bye"))
    monkeypatch.setattr(tag_edit, "has_permission", lambda self, tag: True)
    monkeypatch.setattr(addtag, "safe_seeother", Redirect)

    with pytest.raises(Redirect):
        tag_edit().POST(key)

    assert saved == {
        "data": {"key": key, "type": {"key": "/type/delete"}},
        "comment": "bye",
        "action": "delete-tag",
    }
