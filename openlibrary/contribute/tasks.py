"""A task is derived, never stored: one edition, one empty field.

A work field (the literary form) is still keyed by the edition, so the initiative list and the task
URLs stay one shape; its answer saves to the edition's work.
"""

from dataclasses import dataclass

from openlibrary.core.tags import LITERARY_FORM, work_tag_keys

# The fields on offer, most valuable first. Four weights match a same-named Edition Scorecard
# check exactly: covers == ``cover`` (35), languages == ``language`` (15), publishers == ``publisher`` (2),
# number_of_pages == ``page_count`` (10). The scorecard has no check specific to lccn or oclc,
# though an OCLC number (like an ISBN) satisfies its ``library_options`` check (score 25, which is
# why oclc_numbers is weighted 25 here); lccn has no scorecard counterpart at all. Kept local
# rather than imported because the scorecard exposes no field -> weight mapping: its checks are
# attributes spread across section classes, under their own names.
# The literary form has no scorecard counterpart either; it sits with the page count as a quick, useful answer.

POINTS = {
    "covers": 35,
    "lccn": 25,
    "oclc_numbers": 25,
    "languages": 15,
    "number_of_pages": 10,
    LITERARY_FORM: 10,
    "publishers": 2,
}
# Fields that live on the work rather than the edition.
WORK_FIELDS = frozenset({LITERARY_FORM})
# Fields only the tags whitelist sees, until the feature opens up.
BETA_FIELDS = frozenset({LITERARY_FORM})


def visible_fields(can_edit_tags: bool) -> tuple[str, ...]:
    return tuple(f for f in POINTS if can_edit_tags or f not in BETA_FIELDS)


def work_of(edition):
    """The edition's work as a lazy reference, or None for an orphan."""
    works = edition.get("works") or []
    return works[0] if works else None


@dataclass(frozen=True)
class Task:
    olid: str
    field: str

    @property
    def key(self) -> str:
        return f"{self.olid}/{self.field}"


def is_missing(edition, fld: str, work=None) -> bool:
    """``work`` is the edition's work when the caller has it loaded; otherwise it is fetched when a work field asks."""
    if fld == "covers":
        # -1 marks a deleted cover. A scanned book shows its first page as the cover, so it isn't missing one.
        return not edition.get("ocaid") and not any(c and c != -1 for c in edition.get("covers") or [])
    if fld in WORK_FIELDS:
        # An orphan edition has no work to put the answer on, so it has no such task.
        work = work if work is not None else work_of(edition)
        return work is not None and not work_tag_keys(work, fld)
    return edition.get(fld) in (None, "", [])


def tasks_for_edition(edition, work=None) -> list[Task]:
    """The fields this edition leaves empty, most valuable first."""
    olid = edition.key.split("/")[-1]
    return [Task(olid, fld) for fld in POINTS if is_missing(edition, fld, work)]


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
