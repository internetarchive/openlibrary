"""The books for a project someone sets up: pasted IDs, or an Open Library list, resolved to editions.

A task is an edition and a field, so everything named ends up as an edition: an edition as itself, an ISBN as the
edition that carries it, a work as one of its editions. Whatever can't be used is reported back with the reason.
"""

import re
from dataclasses import dataclass, field

from openlibrary.contribute import tasks
from openlibrary.utils.isbn import get_isbn_10_and_13

# A list this long is read and checked in one request when the project is created.
MAX_BOOKS = 5000
OLID = re.compile(r"OL\d+[MW]")
LIST_KEY = re.compile(r"(?:/people/[^/\s?#]+)?/lists/OL\d+L")
# How many of a work's editions to look through for one with an ISBN.
WORK_EDITIONS = 20


@dataclass
class Resolved:
    # ``[[edition key, readers], ...]`` in the order named; readers are unknown for a hand-made list.
    picks: list[list] = field(default_factory=list)
    # ``{"entry": what was named, "reason": a code from manage.skip_reasons}``
    skipped: list[dict] = field(default_factory=list)


def edition_for_isbn(site, isbn: str) -> str | None:
    isbn_10, isbn_13 = get_isbn_10_and_13(isbn)
    for name, value in (("isbn_13", isbn_13), ("isbn_10", isbn_10)):
        if value and (keys := site.things({"type": "/type/edition", name: value, "limit": 1})):
            return keys[0]
    return None


def edition_for_work(site, work_key: str):
    """One of the work's editions: the first with an ISBN, else the first. None for a work with none."""
    keys = site.things({"type": "/type/edition", "works": work_key, "limit": WORK_EDITIONS})
    editions = site.get_many(keys) if keys else []
    return next((e for e in editions if e.get("isbn_13") or e.get("isbn_10")), editions[0] if editions else None)


def to_key(site, entry: str) -> tuple[str | None, str]:
    """The edition or work key an entry names, or None with the reason it names nothing."""
    if match := OLID.search(entry):
        olid = match.group()
        return f"/{'books' if olid.endswith('M') else 'works'}/{olid}", ""
    digits = re.sub(r"[\s-]", "", entry)
    if re.fullmatch(r"\d{9}[\dXx]|\d{13}", digits):
        return (key, "") if (key := edition_for_isbn(site, digits)) else (None, "no_isbn")
    return None, "unknown"


def resolve(site, entries: list[str], one_per_work: bool = False) -> Resolved:
    """The editions ``entries`` name, in order, at most ``MAX_BOOKS``. With ``one_per_work``, a work's second edition is skipped."""
    result = Resolved()
    named: list[tuple[str, str]] = []
    for entry in entries:
        key, reason = to_key(site, entry)
        if key:
            named.append((entry, key))
        else:
            result.skipped.append({"entry": entry, "reason": reason})
    docs: dict = {}
    keys = list(dict.fromkeys(key for _entry, key in named))
    for i in range(0, len(keys), 100):
        docs |= {d.key: d for d in site.get_many(keys[i : i + 100])}
    taken: set[str] = set()
    taken_works: set[str] = set()
    for entry, key in named:
        doc = docs.get(key)
        if doc is not None and doc.type.key == "/type/work":
            doc = edition_for_work(site, key)
            reason = "no_edition"
        else:
            reason = "missing" if doc is None else "not_book"
        if doc is None or doc.type.key != "/type/edition":
            result.skipped.append({"entry": entry, "reason": reason})
            continue
        work = tasks.work_of(doc)
        if doc.key in taken:
            result.skipped.append({"entry": entry, "reason": "duplicate"})
        elif one_per_work and work is not None and work.key in taken_works:
            result.skipped.append({"entry": entry, "reason": "same_work"})
        elif len(result.picks) >= MAX_BOOKS:
            result.skipped.append({"entry": entry, "reason": "over_limit"})
        else:
            taken.add(doc.key)
            if work is not None:
                taken_works.add(work.key)
            result.picks.append([doc.key, None])
    return result


def split_entries(text: str) -> list[str]:
    """Pasted IDs, one per line or separated by commas or spaces. A hyphenated ISBN stays in one piece."""
    return [e for e in re.split(r"[\s,;]+", text) if e]


def resolve_list(site, url: str, one_per_work: bool = False) -> Resolved | None:
    """The books on an Open Library list, by its URL or key. None when it isn't a list we can find."""
    if not (match := LIST_KEY.search(url)):
        return None
    lst = site.get(match.group())
    if lst is None or lst.type.key != "/type/list":
        return None
    # A list can also hold authors and subjects, which name no one book.
    return resolve(site, [seed.key for seed in lst.get_seeds()], one_per_work)
