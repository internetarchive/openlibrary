"""A task is derived, never stored: one edition, one empty field."""

from dataclasses import dataclass

# The fields on offer, most valuable first. Points are the Edition Scorecard weights.
POINTS = {
    "lccn": 25,
    "oclc_numbers": 25,
    "languages": 15,
    "number_of_pages": 10,
    "publishers": 2,
}


@dataclass(frozen=True)
class Task:
    olid: str
    field: str

    @property
    def key(self) -> str:
        return f"{self.olid}/{self.field}"


def is_missing(edition, fld: str) -> bool:
    return edition.get(fld) in (None, "", [])


def tasks_for_edition(edition) -> list[Task]:
    """The fields this edition leaves empty, most valuable first."""
    olid = edition.key.split("/")[-1]
    return [Task(olid, fld) for fld in POINTS if is_missing(edition, fld)]


def task_for(edition, fld: str) -> Task | None:
    return next((t for t in tasks_for_edition(edition) if t.field == fld), None)


def impact(readers: int | None, task: Task) -> int:
    """Readers times the task's points. A book nobody has logged still counts by its task."""
    return max(readers or 0, 1) * POINTS.get(task.field, 0)


def field_values(edition, fld: str) -> list:
    """The edition's values for ``fld`` as a flat list; languages as their codes."""
    raw = edition.get(fld)
    if raw in (None, "", []):
        return []
    if fld == "languages":
        return [lang.key.split("/")[-1] if hasattr(lang, "key") else str(lang).split("/")[-1] for lang in raw]
    return list(raw) if isinstance(raw, list) else [raw]
