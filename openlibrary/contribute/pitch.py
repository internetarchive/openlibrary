"""The Tasks pitch under the thank-you an edit-page save lands on: "Got a minute? Help with a community project", and a link to one initiative.

The save decides what to pitch, where reading the cache and the cookies is ordinary work, and hands it to the next page as the
flash message's text. The shell that shows it then needs only the registry, so rendering the site layout still does no I/O.
The banner's wording and links are built beside the Tasks pages, in ``plugins/openlibrary/contribute.py``.
"""

import zlib
from collections.abc import Collection, Mapping
from dataclasses import dataclass

from openlibrary.contribute import initiatives

# The flash message type the edit pages save with; its text is ``encode``'s.
FLASH_TYPE = "edit-saved"
# Set when the pitch is shown, so someone saving many edits in a sitting sees it once a day.
SEEN_COOKIE = "tasks_pitch_seen"
# How long closing the pitch, or following its link, keeps it away.
DISMISS_DAYS = 365


@dataclass(frozen=True)
class Project:
    slug: str
    title: str
    url: str
    # "485 tasks left", or "" while the initiative's list is still being built.
    left: str


@dataclass(frozen=True)
class EditSaved:
    """What the thank-you banner shows. With no project it is the thank-you alone."""

    project: Project | None = None
    dismiss_cookie: str = ""
    dismiss_days: int = DISMISS_DAYS


def dismiss_cookie() -> str:
    """The cookie that closing the pitch sets. Named for the initiatives running now: closing silences all of them, and a new one brings the pitch back."""
    slugs = ",".join(sorted(i.slug for i in initiatives.running()))
    return f"tasks_pitch_{zlib.crc32(slugs.encode()):08x}"


def wanted(cookies: Mapping[str, str]) -> bool:
    """Whether this reader is due the pitch: not shown it today, and not closed while these initiatives ran."""
    return SEEN_COOKIE not in cookies and dismiss_cookie() not in cookies


def encode(book_keys: Collection[str] = ()) -> str:
    """``slug:tasks left`` for the one initiative to pitch; "" when none has anything left.

    An initiative that lists one of ``book_keys`` with a gap still open wins, then the headline one, then the registry's order.
    One whose list is still being built is named with no count.
    """
    ranked = []
    headline = initiatives.headline().slug
    for initiative in initiatives.running():
        gaps = initiatives.get_gaps(initiative)
        left = None if gaps is None else initiatives.progress(gaps, initiative.fields)["open"]
        if left == 0:
            continue
        fields = set(initiative.fields)
        has_book = any(key in book_keys and fields.intersection(open_fields) for key, _readers, open_fields, *_rest in gaps or [])
        ranked.append((not has_book, initiative.slug != headline, f"{initiative.slug}:{'' if left is None else left}"))
    # min keeps the first of equals, so initiatives that tie fall back to the registry's order.
    return min(ranked, key=lambda r: r[:2])[2] if ranked else ""


def decode(payload: str) -> tuple[initiatives.Initiative, int] | None:
    """The initiative a flash message from ``encode`` names, with its tasks left (0 when unknown).

    The text comes back in a cookie, so nothing in it is taken as written: the slug has to name an initiative, the count has to be a number.
    """
    slug, _sep, count = payload.partition(":")
    if not (initiative := initiatives.get(slug)):
        return None
    return initiative, int(count) if count.isascii() and count.isdigit() and len(count) < 8 else 0
