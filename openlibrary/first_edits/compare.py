"""Field comparators: does one value agree with another?

Five comparators ported from Bookie, nothing more. Each takes raw values in
Open Library's shape (a list of publisher strings, a date string, an int,
a list of language codes, a subtitle string) and returns True when a
cataloguer would call them the same.
"""

import re
from collections.abc import Callable
from difflib import SequenceMatcher
from typing import Any

PUBLISHER_IGNORE = {
    "books",
    "book",
    "press",
    "publishing",
    "publishers",
    "publisher",
    "publications",
    "co",
    "company",
    "inc",
    "ltd",
    "llc",
    "group",
    "house",
    "editions",
    "verlag",
    "the",
    "and",
    "distributed",
    "by",
}
PAGE_TOLERANCE = 4
SUBTITLE_THRESHOLD = 0.75


def norm_text(s: str) -> str:
    s = re.sub(r"[^\w\s]", " ", (s or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def publisher_tokens(s: str) -> set[str]:
    return {t for t in norm_text(s).split() if t not in PUBLISHER_IGNORE}


def publishers_agree(a: list[str] | None, b: list[str] | None) -> bool:
    """Any pair sharing half its meaningful tokens counts as the same publisher."""
    for x in a or []:
        for y in b or []:
            tx, ty = publisher_tokens(x), publisher_tokens(y)
            if not tx or not ty:
                continue
            overlap = len(tx & ty) / min(len(tx), len(ty))
            if overlap >= 0.5:
                return True
    return False


def year_of(s: str | None) -> int | None:
    m = re.search(r"(1[5-9]\d\d|20\d\d)", s or "")
    return int(m.group(1)) if m else None


def dates_agree(a: str | None, b: str | None) -> bool:
    ya, yb = year_of(a), year_of(b)
    return ya is not None and ya == yb


def pages_agree(a: int | None, b: int | None) -> bool:
    return a is not None and b is not None and abs(int(a) - int(b)) <= PAGE_TOLERANCE


def languages_agree(a: list[str] | None, b: list[str] | None) -> bool:
    return bool(set(a or []) & set(b or []))


def ids_agree(a: list[str] | None, b: list[str] | None) -> bool:
    """Identifiers are equal or they are not. Both sides arrive already normalized."""
    return bool({str(x) for x in a or []} & {str(y) for y in b or []})


def subtitles_agree(a: str | None, b: str | None) -> bool:
    na, nb = norm_text(a or ""), norm_text(b or "")
    return bool(na and nb) and SequenceMatcher(None, na, nb).ratio() >= SUBTITLE_THRESHOLD


COMPARATORS: dict[str, Callable[[Any, Any], bool]] = {
    "publishers": publishers_agree,
    "publish_date": dates_agree,
    "number_of_pages": pages_agree,
    "languages": languages_agree,
    "subtitle": subtitles_agree,
    "lccn": ids_agree,
    "oclc_numbers": ids_agree,
}


def values_agree(field: str, a, b) -> bool:
    if a in (None, "", []) or b in (None, "", []):
        return False
    return COMPARATORS[field](a, b)
