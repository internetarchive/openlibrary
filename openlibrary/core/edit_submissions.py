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


# This prototype only accepts edits to catalog records (books, works, authors).
# Everything else -- accounts (/people/), types, templates, redirects, deleted
# docs -- is out of scope and must not be patchable just because a revision
# number happens to match. The per-field / per-type trust model is a follow-up
# (see the issue's "Trust model"); this is the coarse safety floor.
EDITABLE_KEY_PREFIXES: tuple[str, ...] = ("/books/", "/works/", "/authors/")
EDITABLE_TYPES: frozenset[str] = frozenset({"/type/edition", "/type/work", "/type/author"})


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


def _parse_version(v: object) -> int | None:
    """Coerce a base version ``v`` to a non-negative int, or None if it is not one.

    Accepts an int or an all-digits string (``3`` or ``"3"``). Rejects booleans,
    floats, and non-integer strings (``"3.0"``, ``"latest"``) so a malformed
    version cannot silently coerce to the wrong revision.
    """
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v if v >= 0 else None
    if isinstance(v, str) and v.isdigit():
        return int(v)
    return None


def validate_edit_submission(record: dict) -> list[str]:
    """Return a list of human-readable validation errors (empty list = valid).

    An edit submission must name a valid target ``key``, declare the integer base
    version ``v`` it was authored against, and change at least one field.
    """
    errors: list[str] = []

    key = record.get("key")
    if not isinstance(key, str) or not key.startswith("/"):
        errors.append("edit submission must have a valid `key` (e.g. /books/OL123M)")
    elif not key.startswith(EDITABLE_KEY_PREFIXES):
        errors.append(f"edit submission target must be a book, work, or author (one of {', '.join(EDITABLE_KEY_PREFIXES)})")

    if _parse_version(record.get("v")) is None:
        errors.append("edit submission must specify an integer base version `v`")

    if not extract_patch(record):
        errors.append("edit submission must change at least one field")

    return errors


def _type_key(doc: dict) -> str | None:
    """The ``/type/...`` key from a doc's serialised dict (``doc.dict()``).

    In that form ``type`` is ``{"key": "/type/edition"}`` or a bare string --
    not a lazy Thing -- so reading it never triggers a fetch.
    """
    doc_type = doc.get("type")
    if isinstance(doc_type, str):
        return doc_type
    if isinstance(doc_type, dict):
        return doc_type.get("key")
    return None


def _same_entry(a: object, b: object) -> bool:
    """Whether two list members denote the same thing.

    Reference dicts (``{"key": "/authors/OL1A"}``) are compared by their ``key``
    so a reference is not duplicated when the live value and the patch value
    carry different surrounding fields; everything else by equality.
    """
    if isinstance(a, dict) and isinstance(b, dict) and "key" in a and "key" in b:
        return a["key"] == b["key"]
    return a == b


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
                if not any(_same_entry(entry, present) for present in combined):
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

    doc_dict = doc.dict()

    # Guard the document type too, not just the key prefix: a redirect or a
    # deleted record can live under /books/ or /works/, and patching one would
    # corrupt it. Only genuine editions/works/authors are editable here.
    if (doc_type := _type_key(doc_dict)) not in EDITABLE_TYPES:
        return EditResult(EditOutcome.INVALID, key=key, message=f"{key} is not an editable record (type {doc_type})")

    if (live_version := doc_dict.get("revision")) != base_version:
        return EditResult(
            EditOutcome.CONFLICT,
            key=key,
            message=f"authored against v{base_version} but live is v{live_version}; needs rebase/review",
        )

    patch = extract_patch(record)
    merged = apply_patch(doc_dict, patch)

    comment = comment or f"BookWorm edit submission (base v{base_version})"
    web.ctx.site.save(merged, comment=comment, action="edit-book")

    logger.info("edit submission applied to %s (base v%s): fields %s", key, base_version, sorted(patch))
    return EditResult(EditOutcome.APPLIED, key=key, message=comment)
