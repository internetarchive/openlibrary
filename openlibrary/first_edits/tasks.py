"""A task is derived, never stored: one edition, one field, one decision.

``tasks_for_edition`` reads the edition's own values, the evidence document
for its ISBN, and the scope, and returns the fields a newcomer may act on.
"""

from dataclasses import dataclass

from openlibrary.first_edits import fixtures
from openlibrary.first_edits.evidence import FieldEvidence, build_field_evidence
from openlibrary.first_edits.scope import Scope, load_scope

QUICK_WIN_LEVEL = "strong"


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

    @property
    def quick_win(self) -> bool:
        return self.mode == "fill" and self.evidence.level == QUICK_WIN_LEVEL


def edition_values(edition) -> dict:
    """The edition's fields in the shape the comparators expect."""
    languages = [lang.key.split("/")[-1] if hasattr(lang, "key") else str(lang).split("/")[-1] for lang in (edition.get("languages") or [])]
    return {
        "publishers": list(edition.get("publishers") or []),
        "publish_date": edition.get("publish_date"),
        "number_of_pages": edition.get("number_of_pages"),
        "languages": languages,
        "subtitle": edition.get("subtitle"),
    }


def evidence_for_edition(edition) -> dict | None:
    isbn = edition.get_isbn13() if hasattr(edition, "get_isbn13") else None
    return fixtures.load_evidence(isbn) if isbn else None


def field_evidence(edition, fld: str, language_names: dict[str, str] | None = None) -> FieldEvidence:
    doc = evidence_for_edition(edition) or {"sources": []}
    return build_field_evidence(fld, edition_values(edition), doc, language_names)


def tasks_for_edition(edition, scope: Scope | None = None, language_names: dict[str, str] | None = None) -> list[Task]:
    scope = scope or load_scope()
    olid = edition.key.split("/")[-1]
    out = []
    for fld in scope.enabled_fields():
        ev = field_evidence(edition, fld, language_names)
        mode = ev.mode
        if mode and scope.fields[fld].allows(mode, ev.level):
            out.append(Task(edition.key, olid, fld, mode, ev))
    # Fills first, then checks, then confirmations; strongest evidence first within each.
    order = {"fill": 0, "check": 1, "confirm": 2}
    out.sort(key=lambda t: (order[t.mode], -t.evidence.level_index))
    return out


def task_for(edition, fld: str, scope: Scope | None = None, language_names: dict[str, str] | None = None) -> Task | None:
    return next((t for t in tasks_for_edition(edition, scope, language_names) if t.field == fld), None)
