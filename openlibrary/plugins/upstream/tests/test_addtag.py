"""Tests for openlibrary.plugins.upstream.addtag."""

import pytest

from openlibrary.core.models import Tag
from openlibrary.plugins.upstream.addtag import parse_slugs


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
