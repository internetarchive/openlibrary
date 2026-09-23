"""Practice tasks: a real-looking task with a known answer and an instant verdict.

Built from fixtures only. The chooser posts the same fields a real task
would, and the verdict compares the chosen value with the fixture's truth.
"""

from dataclasses import dataclass

from openlibrary.first_edits import fixtures
from openlibrary.first_edits.compare import values_agree
from openlibrary.first_edits.evidence import FieldEvidence, build_field_evidence

OUTCOMES = ("correct", "unsure", "wrong")


@dataclass(frozen=True)
class PracticeVerdict:
    outcome: str
    message: str
    lesson: str


def practice_evidence(practice: dict, language_names: dict[str, str] | None = None) -> FieldEvidence:
    return build_field_evidence(practice["field"], practice["ol_values"], practice["evidence"], language_names)


def resolve_answer(practice: dict, choice: str, value: str | None) -> object:
    """Map the chooser's posted answer to a raw field value, or None for unsure."""
    fld = practice["field"]
    if choice == "unsure":
        return None
    if choice == "suggestion":
        return practice_evidence(practice).suggestion_raw
    if choice == "keep":
        return practice["ol_values"].get(fld)
    if choice.startswith("source:"):
        source_id = choice.split(":", 1)[1]
        for src in practice["evidence"]["sources"]:
            if src["id"] == source_id:
                return src["fields"].get(fld)
        return None
    return _coerce(fld, value)


def _coerce(fld: str, value: str | None):
    if value is None or not value.strip():
        return None
    value = value.strip()
    if fld == "number_of_pages":
        return int(value) if value.isdigit() else None
    if fld in ("publishers", "languages"):
        return [value]
    return value


def judge(practice: dict, choice: str, value: str | None) -> PracticeVerdict:
    answer = resolve_answer(practice, choice, value)
    verdicts = practice["verdicts"]
    if choice == "unsure":
        return PracticeVerdict("unsure", verdicts["unsure"], practice["lesson"])
    if answer is not None and values_agree(practice["field"], answer, practice["truth"]):
        return PracticeVerdict("correct", verdicts["correct"], practice["lesson"])
    return PracticeVerdict("wrong", verdicts["wrong"], practice["lesson"])


def next_practice(current_key: str) -> dict | None:
    items = fixtures.load_practice()
    keys = [p["key"] for p in items]
    if current_key not in keys:
        return items[0] if items else None
    idx = keys.index(current_key) + 1
    return items[idx] if idx < len(items) else None
