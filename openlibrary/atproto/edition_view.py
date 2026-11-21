"""Project OpenLibrary editions onto the lexicon's ``defs#editionView``.

Pure builders: everything here takes an infogami ``Thing`` (or a plain mapping)
and returns wire-shaped data. The only side effect is the coverstore base URL
lookup.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Sequence
from typing import Any

from openlibrary.atproto.errors import RecordError
from openlibrary.atproto.models import Contributor, EditionView, Identifier, Publisher, Series
from openlibrary.plugins.upstream.utils import get_coverstore_public_url
from openlibrary.utils.isbn import to_isbn_13

OPENLIBRARY_ISSUER = "openlibrary"
OPENLIBRARY_BASE = "https://openlibrary.org"

AUDIO_FORMAT_HINTS = ("audio", "audiobook", "cassette", "mp3")
EBOOK_FORMAT_HINTS = ("ebook", "e-book", "electronic", "kindle", "pdf", "epub")
BCP47_TAG_PATTERN = re.compile(r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")


def olid_from_key(key: str) -> str:
    """``/books/OL1M`` -> ``OL1M``."""
    return key.rsplit("/", 1)[-1]


def as_list(value: Any) -> list:
    """Normalize an OL field that is typed as a list but may hold a scalar."""
    if not value:
        return []
    return value if isinstance(value, list) else [value]


def rfc3339(value: dt.datetime | str) -> str:
    """Render a datetime as RFC3339 with a ``Z`` suffix; naive means UTC."""
    if isinstance(value, str):
        value = dt.datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.UTC)
    return value.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")


def normalize_published_date(value: Any) -> str | None:
    """Return ``value`` when it is a real calendar date at its own precision.

    Only ``YYYY``, ``YYYY-MM`` and ``YYYY-MM-DD`` are representable as the
    lexicon's ``publishedDate``; free text such as ``May 1998`` or ``c1998`` is
    dropped rather than guessed at.
    """
    if not isinstance(value, str):
        return None
    value = value.strip()
    if len(value) == 4 and value.isdigit() and int(value) > 0:
        return value
    if len(value) == 7 and value[4] == "-":
        year, month = value.split("-")
        if year.isdigit() and int(year) > 0 and month.isdigit() and 1 <= int(month) <= 12:
            return value
        return None
    if len(value) == 10:
        try:
            dt.date.fromisoformat(value)
        except ValueError:
            return None
        return value
    return None


def format_value(physical_format: Any) -> str | None:
    if not isinstance(physical_format, str):
        return None
    text = physical_format.strip().lower()
    if not text:
        return None
    if any(hint in text for hint in AUDIO_FORMAT_HINTS):
        return "audio"
    if any(hint in text for hint in EBOOK_FORMAT_HINTS):
        return "ebook"
    return "physical"


def description_text(value: Any) -> str | None:
    """Editions store descriptions as a string or as a ``{"value": ...}`` dict."""
    if hasattr(value, "get"):
        value = value.get("value")
    if not isinstance(value, str):
        return None
    return value.strip() or None


def first_language_tag(tags: Sequence[str]) -> str | None:
    """The first BCP 47 tag the provider resolved for the edition."""
    for tag in tags:
        if BCP47_TAG_PATTERN.match(tag):
            return tag
    return None


def cover_url(edition) -> str | None:
    for cover in as_list(edition.get("covers")):
        if isinstance(cover, int) and cover > 0:
            return f"{get_coverstore_public_url()}/b/id/{cover}-L.jpg"
    return None


def page_count(edition) -> int | None:
    try:
        pages = int(edition.get("number_of_pages"))
    except TypeError, ValueError:
        return None
    return pages if pages > 0 else None


def identifier_bag(edition) -> list[Identifier]:
    """The edition's identifiers, always led by its OpenLibrary OLID."""
    olid = olid_from_key(edition["key"])
    identifiers = [Identifier(issuer=OPENLIBRARY_ISSUER, value=olid, url=f"{OPENLIBRARY_BASE}/books/{olid}")]
    seen = {(OPENLIBRARY_ISSUER, olid)}

    candidates: list[tuple[str, str]] = []
    for raw in [*as_list(edition.get("isbn_13")), *as_list(edition.get("isbn_10"))]:
        if isinstance(raw, str) and (isbn_13 := to_isbn_13(raw)):
            candidates.append(("isbn13", isbn_13))
    for issuer, field in (("oclc", "oclc_numbers"), ("lccn", "lccn")):
        for raw in as_list(edition.get(field)):
            if isinstance(raw, str) and (raw := raw.strip()):
                candidates.append((issuer, raw))
    for raw in as_list((edition.get("identifiers") or {}).get("amazon")):
        if isinstance(raw, str) and (raw := raw.strip()):
            candidates.append(("asin", raw))

    for issuer, value in candidates:
        if (issuer, value) in seen:
            continue
        seen.add((issuer, value))
        identifiers.append(Identifier(issuer=issuer, value=value))
    return identifiers


def contributor_value(author) -> Contributor | None:
    display_name = author.get("name") or author.get("personal_name")
    if not isinstance(display_name, str) or not (display_name := display_name.strip()):
        return None
    identifiers = []
    key = author.get("key")
    if isinstance(key, str) and (olid := olid_from_key(key)):
        identifiers.append(Identifier(issuer=OPENLIBRARY_ISSUER, value=olid))
    return Contributor(displayName=display_name, identifiers=identifiers)


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _first_string(edition, field: str) -> str | None:
    """The first nonblank string in a field that OL types as a list."""
    for value in as_list(edition.get(field)):
        if text := _text(value):
            return text
    return None


def publisher_value(edition) -> Publisher | None:
    name = _first_string(edition, "publishers")
    return Publisher(name=name) if name else None


def series_value(edition) -> Series | None:
    name = _first_string(edition, "series")
    return Series(name=name) if name else None


def build_edition_view(edition, authors, languages: Sequence[str] = ()) -> EditionView:
    """Build one ``editionView``, raising ``RecordError`` if it is unrepresentable."""
    title = _text(edition.get("title"))
    if not title:
        raise RecordError(f"{edition.get('key')} has no title")
    created = edition.get("created")
    if not created:
        raise RecordError(f"{edition.get('key')} has no creation timestamp")

    return EditionView(
        title=title,
        identifiers=identifier_bag(edition),
        contributors=[contributor for author in authors if (contributor := contributor_value(author))],
        createdAt=rfc3339(created),
        subtitle=_text(edition.get("subtitle")),
        language=first_language_tag(languages),
        publishedDate=normalize_published_date(edition.get("publish_date")),
        publisher=publisher_value(edition),
        format=format_value(edition.get("physical_format")),
        pages=page_count(edition),
        series=series_value(edition),
        bookEdition=_text(edition.get("edition_name")),
        description=description_text(edition.get("description")),
        coverUrl=cover_url(edition),
    )
