"""A task is derived, never stored: one edition, one empty field.

Open Library fetches nothing from outside catalogs. The task page points the
librarian at them, and the answer is theirs.
"""

from dataclasses import dataclass

from openlibrary.first_edits.scope import Scope, load_scope


@dataclass(frozen=True)
class Task:
    edition_key: str
    olid: str
    field: str

    @property
    def key(self) -> str:
        return f"{self.olid}/{self.field}"


def is_missing(edition, fld: str) -> bool:
    return edition.get(fld) in (None, "", [])


def tasks_for_edition(edition, scope: Scope | None = None) -> list[Task]:
    """The enabled fields this edition leaves empty, most valuable first."""
    scope = scope or load_scope()
    olid = edition.key.split("/")[-1]
    out = [Task(edition.key, olid, fld) for fld in scope.enabled_fields() if is_missing(edition, fld)]
    out.sort(key=lambda t: -scope.fields[t.field].points)
    return out


def task_for(edition, fld: str, scope: Scope | None = None) -> Task | None:
    return next((t for t in tasks_for_edition(edition, scope) if t.field == fld), None)
