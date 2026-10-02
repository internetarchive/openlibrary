"""A task is derived, never stored: one edition, one field, one decision.

``tasks_for_edition`` reads the edition's own values, the evidence document
for its ISBN, and the scope, and returns the fields a newcomer may act on.
"""

from dataclasses import dataclass, replace

from openlibrary.first_edits import fixtures, identifiers
from openlibrary.first_edits.evidence import FieldEvidence, build_field_evidence, display_value
from openlibrary.first_edits.scope import Scope, load_scope
from openlibrary.i18n import gettext as _


@dataclass(frozen=True)
class Task:
    edition_key: str
    olid: str
    field: str
    mode: str
    evidence: FieldEvidence

    @property
    def key(self) -> str:
        return f"{self.olid}/{self.field}"


def edition_values(edition) -> dict:
    """The edition's fields in the shape the comparators expect."""
    languages = [lang.key.split("/")[-1] if hasattr(lang, "key") else str(lang).split("/")[-1] for lang in (edition.get("languages") or [])]
    return {
        "publishers": list(edition.get("publishers") or []),
        "publish_date": edition.get("publish_date"),
        "number_of_pages": edition.get("number_of_pages"),
        "languages": languages,
        "subtitle": edition.get("subtitle"),
        "lccn": identifiers.normalized("lccn", edition.get("lccn")),
        "oclc_numbers": identifiers.normalized("oclc_numbers", edition.get("oclc_numbers")),
    }


def evidence_for_edition(edition) -> dict | None:
    isbn = edition.get_isbn13() if hasattr(edition, "get_isbn13") else None
    doc = fixtures.load_evidence(isbn) if isbn else None
    return _normalize_ids(doc) if doc else None


def _normalize_ids(doc: dict) -> dict:
    """Identifiers arrive from sources in whatever form that catalog prints them."""
    out = dict(doc)
    out["sources"] = []
    for src in doc.get("sources", []):
        src = dict(src)
        flds = dict(src.get("fields", {}))
        for fld in ("lccn", "oclc_numbers"):
            if fld in flds:
                flds[fld] = identifiers.normalized(fld, flds[fld])
        src["fields"] = flds
        out["sources"].append(src)
    return out


def field_evidence(edition, fld: str, language_names: dict[str, str] | None = None) -> FieldEvidence:
    doc = evidence_for_edition(edition) or {"sources": []}
    values = edition_values(edition)
    ev = build_field_evidence(fld, values, doc, language_names)
    if identifiers.is_identifier_field(fld):
        ev = _with_corroboration_level(ev, values, doc, language_names)
    return ev


def corroboration(fld: str, ol_values: dict, doc: dict, language_names: dict[str, str] | None = None):
    """The source record an identifier points at, and how well it matches this edition.

    For an ordinary field, confidence is how many catalogs agree. That reasoning
    is circular for an identifier: of course the Library of Congress record
    carries its own number. What matters is whether that record is this edition,
    so the level comes from the details around the identifier instead.
    """
    src = next((s for s in doc.get("sources", []) if s.get("fields", {}).get(fld)), None)
    if not src:
        return None, [], None
    rows = identifiers.match_rows(ol_values, src.get("fields", {}), lambda f, v: display_value(f, v, language_names))
    return src, rows, identifiers.check_match(rows)


def _with_corroboration_level(ev: FieldEvidence, ol_values: dict, doc: dict, language_names) -> FieldEvidence:
    src, rows, check = corroboration(ev.field, ol_values, doc, language_names)
    if not src:
        return ev
    agreed = [r for r in rows if r.agrees is True]
    if check.state != "pass":
        level, sentence = "weak", check.message
    elif len(agreed) >= 3:
        level = "strong"
        sentence = _strong_sentence(len(agreed))
    elif len(agreed) == 2:
        level = "fair"
        sentence = _fair_sentence()
    else:
        level, sentence = "weak", _weak_sentence()
    return replace(ev, level=level, sentence=sentence)


def _strong_sentence(count: int) -> str:
    return _("Strong: the record this number points at matches this edition on all %(count)s details we can compare.", count=count)


def _fair_sentence() -> str:
    return _("Fair: the record matches on two details. Open the record and check the rest before you send it.")


def _weak_sentence() -> str:
    return _("Weak: there is too little on that record to tell these two printings apart.")


def tasks_for_edition(edition, scope: Scope | None = None, language_names: dict[str, str] | None = None) -> list[Task]:
    scope = scope or load_scope()
    olid = edition.key.split("/")[-1]
    out = []
    for fld in scope.enabled_fields():
        ev = field_evidence(edition, fld, language_names)
        mode = ev.mode
        if mode and scope.fields[fld].allows(mode, ev.level):
            out.append(Task(edition.key, olid, fld, mode, ev))
    # Fills first, then checks; strongest evidence first within each.
    order = {"fill": 0, "check": 1}
    out.sort(key=lambda t: (order[t.mode], -t.evidence.level_index))
    return out


def task_for(edition, fld: str, scope: Scope | None = None, language_names: dict[str, str] | None = None) -> Task | None:
    return next((t for t in tasks_for_edition(edition, scope, language_names) if t.field == fld), None)
