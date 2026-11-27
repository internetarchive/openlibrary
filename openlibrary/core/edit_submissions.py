"""BookWorm edit submissions: patches to existing versioned records.

Part of the move from direct bulk write access toward a submission + review
process (issue #14750, part of #13775). The batch-import system already lets any
account submit *new* records for review. This module extends it to accept
*edits* to existing records, submitted as a sparse patch played on top of a
specific base version of the current document and routed through the same
``pending``/``needs_review`` queue as imports.

A submission names the target record, the proposed changes, and the base version
it was authored against::

    {"key": "/books/OL123M", "title": "A better title", "v": "3"}

-> a patch to be played on top of **v3** of ``/books/OL123M``.

What this prototype does:

- :func:`is_edit_submission` distinguishes an edit (has an existing ``key``) from
  a new-record import (no ``key`` -- today's behaviour).
- :func:`validate_edit_submission` checks the shape before it is queued.
- :func:`apply_patch` is the pure, isolated merge step.
- :func:`apply_edit_submission` fetches the live document and, when the live
  version still equals the submitted base version ``v``, applies the patch and
  saves it. When the live version has moved on, it reports a conflict for review
  instead of blindly overwriting.

Deliberately deferred (see the issue's "Challenges" / "Out of scope"):

- **field-level 3-way merge / rebasing** when the live version has drifted past
  ``v`` -- this prototype routes drift to review rather than auto-merging.
- **labels / per-patron provenance** -- issue #14751.
- **OAuth on-behalf-of auth** -- issue #14446.
- **per-field trust model, rate limits, list remove-semantics.**
"""

import logging
from dataclasses import dataclass
from enum import StrEnum

import web

logger = logging.getLogger("openlibrary.imports")

# Structural / infogami-managed fields a patch may never set. ``v`` is the
# submission's own base-version marker, not a document field.
RESERVED_FIELDS: frozenset[str] = frozenset(
    {
        "key",
        "type",
        "v",
        "revision",
        "latest_revision",
        "created",
        "last_modified",
        "id",
        "_key",
        "_revision",
    }
)


class EditOutcome(StrEnum):
    """The result of trying to apply an edit submission to the live catalog."""

    APPLIED = "applied"  # patch applied and saved
    CONFLICT = "conflict"  # live version drifted past the base version; needs review/rebase
    MISSING = "missing"  # the target key does not exist
    INVALID = "invalid"  # the submission is malformed


@dataclass
class EditResult:
    outcome: EditOutcome
    key: str | None = None
    message: str | None = None


def is_edit_submission(record: object) -> bool:
    """Whether ``record`` is an edit to an existing document.

    An edit submission targets an existing record and so carries a ``key``. A
    new-record import has no ``key`` -- that is today's batch-import behaviour,
    left untouched.
    """
    return isinstance(record, dict) and bool(record.get("key"))


def extract_patch(record: dict) -> dict:
    """The proposed field changes, with the submission's control fields removed."""
    return {field: value for field, value in record.items() if field not in RESERVED_FIELDS}


def validate_edit_submission(record: dict) -> list[str]:
    """Return a list of human-readable validation errors (empty list = valid).

    An edit submission must name a valid target ``key``, declare the integer base
    version ``v`` it was authored against, and change at least one field.
    """
    errors: list[str] = []

    key = record.get("key")
    if not isinstance(key, str) or not key.startswith("/"):
        errors.append("edit submission must have a valid `key` (e.g. /books/OL123M)")

    v = record.get("v")
    if v is None:
        errors.append("edit submission must specify the base version `v` it was authored against")
    else:
        try:
            int(v)
        except TypeError, ValueError:
            errors.append("edit submission `v` must be an integer version number")

    if not extract_patch(record):
        errors.append("edit submission must change at least one field")

    return errors


def apply_patch(doc: dict, patch: dict) -> dict:
    """Return a new document with ``patch`` applied on top of ``doc``.

    Prototype merge semantics -- deliberately simple and non-destructive. The
    field-level 3-way merge and list *remove* semantics the issue calls for are
    follow-up work; this step is isolated here so that work can swap it out.

    - Reserved / structural fields in the patch are ignored (see
      :data:`RESERVED_FIELDS`).
    - A list field is **union-added**: patched entries are appended only if not
      already present, so a patch never silently drops existing members
      (authors, subjects). Removal is not expressible yet.
    - Any other field is **replaced** with the patched value.
    """
    merged = dict(doc)
    for field, value in patch.items():
        if field in RESERVED_FIELDS:
            continue
        existing = merged.get(field)
        if isinstance(value, list) and isinstance(existing, list):
            combined = list(existing)
            for entry in value:
                if entry not in combined:
                    combined.append(entry)
            merged[field] = combined
        else:
            merged[field] = value
    return merged


def apply_edit_submission(record: dict, comment: str | None = None) -> EditResult:
    """Apply an edit submission to the live catalog, if it is safe to do so.

    The live document is fetched and its version compared to the submitted base
    version ``v``:

    - live ``== v`` -> apply the patch and ``save`` it, attributed via the
      ``comment``; returns :attr:`EditOutcome.APPLIED`.
    - live ``!= v`` -> do **not** apply; returns :attr:`EditOutcome.CONFLICT` so
      the caller can route the submission to review for a rebase.

    This function does not touch the import queue; it is the pure apply step so
    it can be unit-tested against a mock site. The queue glue lives in
    :meth:`openlibrary.core.imports.ImportItem.apply_edit`.
    """
    if errors := validate_edit_submission(record):
        return EditResult(EditOutcome.INVALID, key=record.get("key"), message="; ".join(errors))

    key = record["key"]
    base_version = int(record["v"])

    doc = web.ctx.site.get(key)
    if doc is None:
        return EditResult(EditOutcome.MISSING, key=key, message=f"no document at {key}")

    if (live_version := doc.revision) != base_version:
        return EditResult(
            EditOutcome.CONFLICT,
            key=key,
            message=f"authored against v{base_version} but live is v{live_version}; needs rebase/review",
        )

    patch = extract_patch(record)
    merged = apply_patch(doc.dict(), patch)

    comment = comment or f"BookWorm edit submission (base v{base_version})"
    web.ctx.site.save(merged, comment=comment, action="edit-book")

    logger.info("edit submission applied to %s (base v%s): fields %s", key, base_version, sorted(patch))
    return EditResult(EditOutcome.APPLIED, key=key, message=comment)
