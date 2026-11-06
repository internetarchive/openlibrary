"""The Tasks pitch under the thank-you an edit-page save lands on: "Keep going with a community project", a link per initiative.

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
# How long closing the pitch, or following one of its links, keeps it away.
DISMISS_DAYS = 365
# A link each for up to this many projects; past it the last slot goes to "See all projects".
MAX_LINKS = 3
MORE = "+"


@dataclass(frozen=True)
class Project:
    slug: str
    title: str
    url: str
    # "485 left", or "" while the initiative's list is still being built.
    left: str


@dataclass(frozen=True)
class EditSaved:
    """What the thank-you banner shows. With no projects it is the thank-you alone."""

    projects: tuple[Project, ...] = ()
    more: bool = False
    dismiss_cookie: str = ""
    dismiss_days: int = DISMISS_DAYS


def dismiss_cookie() -> str:
    """The cookie that closing the pitch sets. Named for the initiatives running now: closing silences all of them, and a new one brings the pitch back."""
    slugs = ",".join(sorted(i.slug for i in initiatives.INITIATIVES))
    return f"tasks_pitch_{zlib.crc32(slugs.encode()):08x}"


def wanted(cookies: Mapping[str, str]) -> bool:
    """Whether this reader is due the pitch: not shown it today, and not closed while these initiatives ran."""
    return SEEN_COOKIE not in cookies and dismiss_cookie() not in cookies


def encode(book_keys: Collection[str] = ()) -> str:
    """``slug:tasks left`` for each initiative with something left, comma-separated; "" when there is nothing to pitch.

    An initiative that lists one of ``book_keys`` with a gap still open comes first, then the headline one.
    A list that is still being built keeps its place, with no count.
    """
    ranked = []
    for initiative in initiatives.INITIATIVES:
        gaps = initiatives.get_gaps(initiative)
        left = None if gaps is None else initiatives.progress(gaps, initiative.fields)["open"]
        if left == 0:
            continue
        fields = set(initiative.fields)
        has_book = any(key in book_keys and fields.intersection(open_fields) for key, _readers, open_fields, _skipped in gaps or [])
        ranked.append((not has_book, initiative is not initiatives.ACTIVE, f"{initiative.slug}:{'' if left is None else left}"))
    # Stable, so initiatives that tie keep the registry's order.
    entries = [entry for _no_book, _not_headline, entry in sorted(ranked, key=lambda r: r[:2])]
    if len(entries) > MAX_LINKS:
        entries = [*entries[: MAX_LINKS - 1], MORE]
    return ",".join(entries)


def decode(payload: str) -> tuple[list[tuple[initiatives.Initiative, int]], bool]:
    """The initiatives a flash message from ``encode`` names, each with its tasks left (0 when unknown), and whether there are more.

    The text comes back in a cookie, so nothing in it is taken as written: a slug has to name an initiative, a count has to be a number.
    """
    entries = payload.split(",")
    named = []
    for entry in entries:
        slug, _sep, count = entry.partition(":")
        if initiative := initiatives.get(slug):
            named.append((initiative, int(count) if count.isascii() and count.isdigit() and len(count) < 8 else 0))
    return named[:MAX_LINKS], bool(named) and MORE in entries
