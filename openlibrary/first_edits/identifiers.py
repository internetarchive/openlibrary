"""Non-IA identifiers: what they are, how to clean one up, and how to tell
whether the record one points at is really this edition.

An identifier is not a property of the book the way a page count is. It is a
pointer into somebody else's catalog, and it is right only when the record at
the other end describes *this* edition. So the checks here are about the
target record, not about the string.

Only the two library identifiers are offered for now. Both already arrive
normalized from ``openlibrary.catalog.marc.parse`` when a MARC record is read
(``read_lccn`` from field 010, ``read_oclc`` from 001/035), so a Library of
Congress lookup yields both without a WorldCat key.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from openlibrary.first_edits.compare import values_agree
from openlibrary.i18n import gettext as _
from openlibrary.utils.lccn import normalize_lccn
from openlibrary.utils.oclc import normalize_oclc

# The fields corroborated against the target record, most telling first.
MATCH_FIELDS = ("publish_date", "publishers", "number_of_pages", "languages")


@dataclass(frozen=True)
class IdentifierSpec:
    field: str
    label: str
    level: str
    normalize: Callable[[str], str | None]
    record_url: Callable[[str], str]
    search_url: Callable[[str], str]


def _strip_url(raw: str, *patterns: str) -> str:
    for pattern in patterns:
        if m := re.search(pattern, raw):
            return m.group(1)
    return raw


def normalize_lccn_value(raw: str) -> str | None:
    s = _strip_url((raw or "").strip().lower(), r"lccn\.loc\.gov/(\S+)")
    return normalize_lccn(re.sub(r"^lccn:?", "", s))


def get_specs() -> dict[str, IdentifierSpec]:
    """Built per request so the labels pick up the visitor's language."""
    return {
        "lccn": IdentifierSpec(
            field="lccn",
            label=_("Library of Congress number (LCCN)"),
            level="edition",
            normalize=normalize_lccn_value,
            record_url=lambda v: f"https://lccn.loc.gov/{v}",
            search_url=lambda isbn: f"https://catalog.loc.gov/vwebv/search?searchArg={isbn}&searchCode=GKEY%5E*&searchType=0",
        ),
        "oclc_numbers": IdentifierSpec(
            field="oclc_numbers",
            label=_("OCLC/WorldCat number"),
            level="edition",
            normalize=normalize_oclc,
            record_url=lambda v: f"https://search.worldcat.org/title/{v}",
            search_url=lambda isbn: f"https://search.worldcat.org/search?q=bn:{isbn}",
        ),
    }


def is_identifier_field(field: str) -> bool:
    return field in ("lccn", "oclc_numbers")


def normalized(field: str, raw) -> list[str]:
    """Identifier values in the one form everything downstream compares."""
    spec = get_specs().get(field)
    if not spec or raw in (None, "", []):
        return []
    values = raw if isinstance(raw, list) else [raw]
    return [v for v in (spec.normalize(str(x)) for x in values) if v]


# --- the three live checks -------------------------------------------------


@dataclass(frozen=True)
class Check:
    id: str
    state: str  # pass | warn | fail
    message: str


@dataclass(frozen=True)
class MatchRow:
    field: str
    label: str
    ol_display: str
    target_display: str
    agrees: bool | None


def check_format(spec: IdentifierSpec, raw: str) -> tuple[str | None, Check]:
    """Clean the value up, and say plainly what was wrong when it will not clean."""
    if not (raw or "").strip():
        return None, Check("format", "fail", _("Nothing to check yet."))
    value = spec.normalize(raw)
    if not value:
        if "http" in raw or "/" in raw:
            return None, Check("format", "fail", _("That looks like a web address. Paste only the number from it."))
        return None, Check("format", "fail", _("That is not a %(label)s. Check you copied from the right place.", label=spec.label))
    if value != raw.strip():
        return value, Check("format", "pass", _("Tidied to %(value)s, which is the form Open Library stores.", value=value))
    return value, Check("format", "pass", _("The format looks right."))


def check_collision(spec: IdentifierSpec, value: str, siblings: list) -> Check:
    """Two editions carrying one identifier means one of them is wrong, or they are duplicates."""
    for ed in siblings:
        existing = [spec.normalize(str(v)) for v in (ed.get(spec.field) or [])]
        if value in existing:
            title = ed.key.split("/")[-1]
            return Check(
                "collision",
                "fail",
                _(
                    "Another edition of this work (%(olid)s) already has this number. "
                    "Only one edition can, so either this is the wrong edition or those two records are duplicates. "
                    "Choose “Not sure” and say so in the note.",
                    olid=title,
                ),
            )
    return Check("collision", "pass", _("No other edition of this work claims this number."))


def match_rows(ol_values: dict, target_fields: dict, display: Callable[[str, object], str]) -> list[MatchRow]:
    """Field-by-field: does the record this identifier points at describe our edition?"""
    labels = {
        "publish_date": _("Year"),
        "publishers": _("Publisher"),
        "number_of_pages": _("Pages"),
        "languages": _("Language"),
    }
    rows = []
    for fld in MATCH_FIELDS:
        ours, theirs = ol_values.get(fld), target_fields.get(fld)
        if ours in (None, "", []) and theirs in (None, "", []):
            continue
        agrees = values_agree(fld, ours, theirs) if ours not in (None, "", []) and theirs not in (None, "", []) else None
        rows.append(MatchRow(fld, labels[fld], display(fld, ours), display(fld, theirs), agrees))
    return rows


def check_match(rows: list[MatchRow]) -> Check:
    """The one that catches the wrong-edition mistake: a differing year or publisher means a different edition."""
    compared = [r for r in rows if r.agrees is not None]
    if not compared:
        return Check("match", "warn", _("There is nothing on this record to compare against, so nobody can tell these apart automatically."))
    disagreeing = [r for r in compared if not r.agrees]
    if not disagreeing:
        return Check("match", "pass", _("All %(count)s details that can be compared match.", count=len(compared)))
    names = ", ".join(str(r.label).lower() for r in disagreeing)
    return Check(
        "match",
        "fail",
        _(
            "The %(fields)s do not match. That usually means this number belongs to a different printing, not to the edition on this page.",
            fields=names,
        ),
    )


def worst_state(checks: list[Check]) -> str:
    for state in ("fail", "warn"):
        if any(c.state == state for c in checks):
            return state
    return "pass"
