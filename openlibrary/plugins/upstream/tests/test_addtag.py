"""Tests for openlibrary.plugins.upstream.addtag."""

import pytest

from openlibrary.core.models import Tag
from openlibrary.plugins.upstream.addtag import SUBJECT_SUB_TYPES, TAG_TYPES, parse_slugs


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
