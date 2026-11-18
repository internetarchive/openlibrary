"""Tests for projecting OL editions onto the lexicon's ``defs#editionView``."""

from __future__ import annotations

import datetime as dt

import pytest
import web

from openlibrary.atproto.edition_view import (
    build_edition_view,
    first_language_tag,
    format_value,
    normalize_published_date,
    rfc3339,
)
from openlibrary.atproto.errors import RecordError

CREATED = dt.datetime(2009, 4, 1, 12, 30, tzinfo=dt.UTC)
AUTHOR = web.storage({"key": "/authors/OL2A", "name": "Ada Lovelace"})


def _edition(**overrides) -> web.storage:
    data = {
        "key": "/books/OL1M",
        "title": "Pattern Recognition",
        "created": CREATED,
        "authors": [{"key": "/authors/OL2A"}],
        "isbn_10": ["059035342X"],
        "publishers": ["Scholastic"],
        "publish_date": "1998",
        "physical_format": "Hardcover",
        "covers": [123],
    }
    data.update(overrides)
    return web.storage(data)


def _wire(view) -> dict:
    """Serialize an ``EditionView`` exactly as the endpoint does."""
    return view.model_dump(exclude_none=True)


def test_rfc3339_treats_infobase_naive_datetimes_as_utc():
    assert rfc3339(dt.datetime(2009, 4, 1, 12, 30, 0, 123456)) == "2009-04-01T12:30:00.123456Z"
    assert rfc3339(dt.datetime(2009, 4, 1, 12, 30, tzinfo=dt.UTC)) == "2009-04-01T12:30:00Z"


def test_build_edition_view_maps_required_and_optional_fields(coverstore):
    view = _wire(build_edition_view(_edition(), [AUTHOR]))

    assert view["title"] == "Pattern Recognition"
    assert view["contributors"] == [{"displayName": "Ada Lovelace", "role": "A01", "identifiers": [{"issuer": "openlibrary", "value": "OL2A"}]}]
    assert view["identifiers"][0] == {"issuer": "openlibrary", "value": "OL1M", "url": "https://openlibrary.org/books/OL1M"}
    assert {"issuer": "isbn13", "value": "9780590353427"} in view["identifiers"]
    assert view["publisher"] == {"name": "Scholastic"}
    assert view["publishedDate"] == "1998"
    assert view["format"] == "physical"
    assert view["coverUrl"] == "https://covers.openlibrary.org/b/id/123-L.jpg"
    assert view["createdAt"] == "2009-04-01T12:30:00Z"
    assert "cover" not in view
    assert "atproto" not in view
    assert "pages" not in view


@pytest.mark.parametrize("description", ["  A novel.  ", {"type": "/type/text", "value": "A novel."}])
def test_build_edition_view_accepts_both_description_shapes(coverstore, description):
    assert _wire(build_edition_view(_edition(description=description), []))["description"] == "A novel."


def test_build_edition_view_uses_the_resolved_bcp47_tag(coverstore):
    assert _wire(build_edition_view(_edition(), [], ["en"]))["language"] == "en"
    assert "language" not in _wire(build_edition_view(_edition(), [], []))
    assert "language" not in _wire(build_edition_view(_edition(), [], ["not a tag!"]))


def test_first_language_tag_skips_unusable_tags():
    assert first_language_tag([]) is None
    assert first_language_tag(["en"]) == "en"
    assert first_language_tag(["!!", "ast"]) == "ast"


def test_build_edition_view_omits_unrepresentable_optional_fields(coverstore):
    view = _wire(build_edition_view(_edition(publish_date="May 1998", physical_format="", covers=[-1]), []))
    assert "publishedDate" not in view
    assert "format" not in view
    assert "coverUrl" not in view


@pytest.mark.parametrize("value", ["May 1998", "c1998", "2023-02-29", "1998-13", "1998-00-10", "0000", "0000-05", "98", "", None, 1998])
def test_normalize_published_date_rejects_non_calendar_values(value):
    assert normalize_published_date(value) is None


@pytest.mark.parametrize("value", ["1998", " 1998 ", "1998-05", "1998-05-01"])
def test_normalize_published_date_keeps_calendar_values(value):
    assert normalize_published_date(value) == value.strip()


@pytest.mark.parametrize(
    ("physical_format", "expected"),
    [
        ("Audio CD", "audio"),
        ("Audiobook", "audio"),
        ("Ebook", "ebook"),
        ("Kindle Edition", "ebook"),
        ("Paperback", "physical"),
        ("CD", "physical"),
        ("", None),
        (None, None),
    ],
)
def test_format_value(physical_format, expected):
    assert format_value(physical_format) == expected


@pytest.mark.parametrize("overrides", [{"title": "  "}, {"title": None}, {"created": None}])
def test_unrepresentable_editions_raise_record_error(coverstore, overrides):
    with pytest.raises(RecordError):
        build_edition_view(_edition(**overrides), [])
