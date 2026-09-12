"""Librarian batch operations: preview, apply, request, revert.

One entry point (``run``) takes an action name, the records it applies to and
the action's parameters, and either returns a preview (what would change, with
warnings) or applies it as a single ``save_many`` recorded in
``librarian_batches`` so it can be reverted as a unit.

Role split: a super-librarian *applies*; a librarian *requests*, which files
the batch in the community edits queue for a super-librarian to apply. The
endpoint checks the same groups the UI uses to show the button.

Every key goes through redirect resolution before anything else, and every
item may carry the revision the client saw; apply refuses the whole batch if
any has moved.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, ClassVar

from openlibrary.core import stats
from openlibrary.core.edits import CommunityEditsQueue
from openlibrary.core.librarian_batches import LibrarianBatches
from openlibrary.core.record_context import (
    RecordType,
    checks_for,
    doc_type,
    key_type,
    load_docs,
    normalize_key,
    olid,
    ref_keys,
    resolve_key,
)
from openlibrary.utils import uniq
from openlibrary.utils.request_context import site

logger = logging.getLogger("openlibrary.batch_ops")

MAX_ITEMS = 200
AUTHOR_ROLE = {"key": "/type/author_role"}

SUBJECT_FIELDS = ("subjects", "subject_people", "subject_places", "subject_times")

# Fields set_field may touch, per record type. Titles and author links are
# deliberately absent: they have their own actions with their own checks.
SETTABLE_FIELDS: dict[RecordType, dict[str, str]] = {
    "edition": {
        "publishers": "list",
        "publish_date": "str",
        "publish_places": "list",
        "languages": "keys",
        "physical_format": "str",
        "number_of_pages": "int",
        "edition_name": "str",
        "series": "list",
    },
    "work": {
        "original_languages": "keys",
    },
}


class BatchError(Exception):
    def __init__(self, message: str, status: int = 400, **extra: Any):
        super().__init__(message)
        self.message = message
        self.status = status
        self.extra = extra


@dataclass
class Plan:
    docs: list[dict[str, Any]] = field(default_factory=list)
    changes: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    creates: list[str] = field(default_factory=list)
    summary: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Ctx:
    username: str
    is_super: bool
    dry_run: bool = True


NEW_WORK_KEY = "/works/new"


def editions_of(work_keys: list[str], limit: int = 1000) -> list[str]:
    """Edition keys of each work, one query per work: the things query takes one
    reference per property, not a list."""
    out: list[str] = []
    for wk in work_keys:
        out.extend(site.get().things({"type": "/type/edition", "works": wk, "limit": limit}))
    return uniq(out)


def _change(key: str, fld: str, before: Any, after: Any, **extra: Any) -> dict[str, Any]:
    return {"key": key, "field": fld, "from": before, "to": after, **extra}


def _warn(level: str, code: str, text: str, key: str | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {"level": level, "code": code, "text": text}
    if key:
        d["key"] = key
    return d


def _title(doc: dict[str, Any]) -> str:
    return doc.get("title") or doc.get("name") or olid(doc["key"])


def _load_target(value: str | None, want: str, label: str) -> dict[str, Any]:
    key = normalize_key(value or "")
    if not key:
        raise BatchError(f"{label} is required.")
    rkey, doc, _chain = resolve_key(key)
    if not doc:
        raise BatchError(f"{label} {key} does not exist.", 404)
    if doc_type(doc) != want:
        raise BatchError(f"{label} {rkey} is not a {want.rsplit('/', 1)[-1]}.")
    return doc


# ── Actions ──────────────────────────────────────────────────────────


class Action:
    name: ClassVar[str] = ""
    label: ClassVar[str] = ""
    applies_to: ClassVar[frozenset[RecordType]] = frozenset()
    super_only: ClassVar[bool] = False
    needs_items: ClassVar[bool] = True
    # Editions in the selection are folded to their work for work-level actions.
    fold_editions_to_works: ClassVar[bool] = False

    def plan(self, docs: dict[str, dict[str, Any]], params: dict[str, Any], ctx: Ctx) -> Plan:
        raise NotImplementedError


class TagAction(Action):
    name = "tag"
    label = "Manage subjects"
    applies_to = frozenset({"work"})
    fold_editions_to_works = True

    def plan(self, docs, params, ctx):
        adds = {f: uniq(params.get("add", {}).get(f) or []) for f in SUBJECT_FIELDS}
        removes = {f: set(params.get("remove", {}).get(f) or []) for f in SUBJECT_FIELDS}
        plan = Plan()
        n_add = n_remove = 0
        for key, doc in docs.items():
            new_doc = dict(doc)
            touched = False
            for f in SUBJECT_FIELDS:
                before = uniq(doc.get(f) or [])
                after = uniq(before + adds[f])
                after = [s for s in after if s not in removes[f]]
                if after != before:
                    touched = True
                    n_add += len(set(after) - set(before))
                    n_remove += len(set(before) - set(after))
                    new_doc[f] = after
                    plan.changes.append(_change(key, f, before, after))
            if touched:
                plan.docs.append(new_doc)
        names_add = [n for f in SUBJECT_FIELDS for n in adds[f]]
        names_remove = [n for f in SUBJECT_FIELDS for n in removes[f]]
        works = f"{len(plan.docs)} work{'s' if len(plan.docs) != 1 else ''}"
        if 0 < len(names_add) + len(names_remove) <= 3:
            parts = [f"+{n}" for n in names_add] + [f"-{n}" for n in names_remove]
            plan.summary = f"Subjects {', '.join(parts)} on {works}"
        else:
            plan.summary = f"Subjects: +{n_add} -{n_remove} across {works}"
        plan.extra = {"added": n_add, "removed": n_remove}
        return plan


class MoveEditionsAction(Action):
    name = "move_editions"
    label = "Move editions"
    applies_to = frozenset({"edition"})

    def plan(self, docs, params, ctx):
        plan = Plan()
        target_param = params.get("target")
        if target_param == "new":
            first = next(iter(docs.values()), None)
            if not first:
                raise BatchError("Nothing to move.")
            # A preview must not consume a key; the placeholder is swapped on apply.
            key = NEW_WORK_KEY if ctx.dry_run else site.get().new_key("/type/work")
            work = {
                "key": key,
                "type": {"key": "/type/work"},
                "title": (params.get("new_title") or first.get("title") or "Untitled").strip(),
            }
            if first.get("subtitle") and not params.get("new_title"):
                work["subtitle"] = first["subtitle"]
            if authors := ref_keys(first.get("authors")):
                work["authors"] = [{"author": {"key": a}, "type": AUTHOR_ROLE} for a in authors]
            if first.get("covers"):
                work["covers"] = [c for c in first["covers"] if c and c > 0][:1]
            plan.docs.append(work)
            plan.creates.append(key)
            plan.changes.append(_change(key, "(new work)", None, work["title"], kind="create"))
            target = work
        else:
            target = _load_target(target_param, "/type/work", "Target work")
        plan.extra["target"] = target
        moved = 0
        for key, doc in docs.items():
            before = ref_keys(doc.get("works"))
            if before == [target["key"]]:
                continue
            new_doc = dict(doc)
            new_doc["works"] = [{"key": target["key"]}]
            plan.docs.append(new_doc)
            plan.changes.append(_change(key, "works", before, [target["key"]]))
            moved += 1
        plan.summary = f"Move {moved} edition{'s' if moved != 1 else ''} to {_title(target)} ({olid(target['key'])})"
        return plan


class SetAuthorAction(Action):
    name = "set_author"
    label = "Set author"
    applies_to = frozenset({"work", "edition"})

    def plan(self, docs, params, ctx):
        plan = Plan()
        author = _load_target(params.get("author"), "/type/author", "Author")
        akey = author["key"]
        replace = normalize_key(params.get("replace") or "")
        mode = params.get("mode") or ("replace" if replace else "add")
        include_editions = bool(params.get("include_editions"))
        plan.extra["author"] = author
        works, editions = 0, 0
        for key, doc in docs.items():
            rtype = key_type(key)
            if rtype == "edition" and not include_editions:
                continue
            before = ref_keys(doc.get("authors"))
            if mode == "set":
                after = [akey]
            elif mode == "replace":
                after = [akey if k == replace else k for k in before] if replace in before else before
            else:
                after = before if akey in before else [*before, akey]
            after = uniq(after)
            if after == before:
                continue
            new_doc = dict(doc)
            if rtype == "work":
                new_doc["authors"] = [{"author": {"key": k}, "type": AUTHOR_ROLE} for k in after]
                works += 1
            else:
                new_doc["authors"] = [{"key": k} for k in after]
                editions += 1
            plan.docs.append(new_doc)
            plan.changes.append(_change(key, "authors", before, after))
        # Keep editions in step with their works when asked (#9863, #13265).
        if include_editions and works:
            work_keys = [k for k in docs if key_type(k) == "work"]
            ed_keys = [k for k in editions_of(work_keys) if k not in docs]
            if ed_keys:
                ed_docs, _r, _m = load_docs(ed_keys)
                for key, doc in ed_docs.items():
                    before = ref_keys(doc.get("authors"))
                    if not before:
                        continue
                    if mode == "replace":
                        after = [akey if k == replace else k for k in before] if replace in before else before
                    elif mode == "set":
                        after = [akey]
                    else:
                        after = before if akey in before else [*before, akey]
                    after = uniq(after)
                    if after == before:
                        continue
                    new_doc = dict(doc)
                    new_doc["authors"] = [{"key": k} for k in after]
                    plan.docs.append(new_doc)
                    plan.changes.append(_change(key, "authors", before, after, via="work"))
                    editions += 1
        verb = {"set": "Set author to", "replace": "Replace author with", "add": "Add author"}[mode]
        plan.summary = f"{verb} {_title(author)} on {works} works" + (f" and {editions} editions" if editions else "")
        return plan


class MergeEditionsAction(Action):
    name = "merge_editions"
    label = "Merge editions"
    applies_to = frozenset({"edition"})

    LIST_FIELDS: ClassVar[tuple[str, ...]] = (
        "isbn_10",
        "isbn_13",
        "lccn",
        "oclc_numbers",
        "source_records",
        "covers",
        "languages",
        "publishers",
        "publish_places",
        "contributions",
        "subjects",
        "genres",
        "series",
        "local_id",
        "uris",
        "links",
        "authors",
    )

    def plan(self, docs, params, ctx):
        plan = Plan()
        if len(docs) < 2:
            raise BatchError("Select at least two editions to merge.")
        master_key = normalize_key(params.get("master") or "")
        if master_key not in docs:
            master_key = min(docs, key=lambda k: int(olid(k)[2:-1]))
        master = dict(docs[master_key])
        dupes = [d for k, d in docs.items() if k != master_key]
        for dup in dupes:
            for f in self.LIST_FIELDS:
                a, b = master.get(f) or [], dup.get(f) or []
                merged = uniq(list(a) + list(b), key=str)
                if merged != a:
                    plan.changes.append(_change(master_key, f, a, merged))
                    master[f] = merged
            if isinstance(master.get("identifiers"), dict) or isinstance(dup.get("identifiers"), dict):
                ids = dict(dup.get("identifiers") or {})
                ids.update(master.get("identifiers") or {})
                if ids != (master.get("identifiers") or {}):
                    plan.changes.append(_change(master_key, "identifiers", master.get("identifiers"), ids))
                    master["identifiers"] = ids
            for f in (
                "ocaid",
                "number_of_pages",
                "physical_format",
                "publish_date",
                "subtitle",
                "by_statement",
                "description",
                "notes",
                "pagination",
                "weight",
                "physical_dimensions",
            ):
                if not master.get(f) and dup.get(f):
                    plan.changes.append(_change(master_key, f, master.get(f), dup[f]))
                    master[f] = dup[f]
            plan.changes.append(_change(dup["key"], "type", "/type/edition", "/type/redirect", to_key=master_key))
            plan.docs.append({"key": dup["key"], "type": {"key": "/type/redirect"}, "location": master_key})
        plan.docs.append(master)
        plan.extra["master"] = master_key
        plan.summary = f"Merge {len(dupes)} edition{'s' if len(dupes) != 1 else ''} into {olid(master_key)}"
        return plan


class FlagAction(Action):
    name = "flag"
    label = "Flag for review"
    applies_to = frozenset({"work", "edition", "author"})

    def plan(self, docs, params, ctx):
        reason = params.get("reason") or "review"
        if reason not in ("spam", "non_book", "duplicate", "delete", "review"):
            raise BatchError("Unknown flag reason.")
        plan = Plan()
        plan.summary = f"Flag {len(docs)} record{'s' if len(docs) != 1 else ''} as {reason.replace('_', '-')}"
        plan.extra["reason"] = reason
        return plan


class DeleteAction(Action):
    name = "delete"
    label = "Delete"
    applies_to = frozenset({"work", "edition", "author"})
    super_only = True

    def plan(self, docs, params, ctx):
        plan = Plan()
        keys = list(docs)
        if params.get("include_editions"):
            work_keys = [k for k in keys if key_type(k) == "work"]
            if work_keys:
                keys += [k for k in editions_of(work_keys) if k not in docs]
        for key in keys:
            plan.docs.append({"key": key, "type": {"key": "/type/delete"}})
            plan.changes.append(_change(key, "type", doc_type(docs.get(key)) or "/type/edition", "/type/delete"))
        plan.summary = f"Delete {len(keys)} record{'s' if len(keys) != 1 else ''}"
        return plan


class SetFieldAction(Action):
    name = "set_field"
    label = "Set field"
    applies_to = frozenset({"work", "edition"})

    def plan(self, docs, params, ctx):
        fld = params.get("field") or ""
        value = params.get("value")
        mode = params.get("mode") or "set"
        plan = Plan()
        for key, doc in docs.items():
            rtype = key_type(key)
            kinds = SETTABLE_FIELDS.get(rtype or "work", {})
            if fld not in kinds:
                raise BatchError(f"Field {fld!r} cannot be set on {rtype}s.")
            kind = kinds[fld]
            before = doc.get(fld)
            if kind == "list":
                vals = value if isinstance(value, list) else [value]
                after = uniq(list(before or []) + vals) if mode == "append" else uniq(vals)
            elif kind == "keys":
                vals = value if isinstance(value, list) else [value]
                refs = [{"key": v if str(v).startswith("/") else f"/languages/{v}"} for v in vals]
                after = uniq(list(before or []) + refs, key=lambda r: r["key"]) if mode == "append" else refs
            elif kind == "int":
                after = int(value)
            else:
                after = str(value or "").strip()
            if after == before:
                continue
            new_doc = dict(doc)
            new_doc[fld] = after
            plan.docs.append(new_doc)
            plan.changes.append(_change(key, fld, before, after))
        plan.summary = f"Set {fld} on {len(plan.docs)} record{'s' if len(plan.docs) != 1 else ''}"
        return plan


class SetIdentifierAction(Action):
    """“Use this ID” from the lookup panel: one identifier onto one or more records."""

    name = "set_identifier"
    label = "Set identifier"
    applies_to = frozenset({"author", "edition", "work"})

    AUTHOR_IDS: ClassVar[set[str]] = {
        "wikidata",
        "viaf",
        "lc_naf",
        "isni",
        "goodreads",
        "amazon",
        "librarything",
        "imdb",
        "gnd",
        "bookbrainz",
        "musicbrainz",
        "storygraph",
        "youtube",
        "inventaire",
    }

    def plan(self, docs, params, ctx):
        fld = (params.get("field") or "").strip()
        value = str(params.get("value") or "").strip()
        if not fld or not value:
            raise BatchError("field and value are required.")
        plan = Plan()
        for key, doc in docs.items():
            rtype = key_type(key)
            new_doc = dict(doc)
            if rtype == "author":
                if fld not in self.AUTHOR_IDS:
                    raise BatchError(f"{fld!r} is not an author identifier.")
                ids = dict(doc.get("remote_ids") or {})
                if ids.get(fld) == value:
                    continue
                plan.changes.append(_change(key, f"remote_ids.{fld}", ids.get(fld), value))
                ids[fld] = value
                new_doc["remote_ids"] = ids
            elif rtype == "edition" and fld == "ocaid":
                if doc.get("ocaid") == value:
                    continue
                plan.changes.append(_change(key, "ocaid", doc.get("ocaid"), value))
                new_doc["ocaid"] = value
            elif rtype == "edition" and fld in ("isbn_10", "isbn_13", "lccn", "oclc_numbers"):
                before = list(doc.get(fld) or [])
                if value in before:
                    continue
                new_doc[fld] = [*before, value]
                plan.changes.append(_change(key, fld, before, new_doc[fld]))
            else:
                ids = dict(doc.get("identifiers") or {})
                before = list(ids.get(fld) or [])
                if value in before:
                    continue
                ids[fld] = [*before, value]
                new_doc["identifiers"] = ids
                plan.changes.append(_change(key, f"identifiers.{fld}", before, ids[fld]))
            plan.docs.append(new_doc)
        plan.summary = f"Set {fld} = {value} on {len(plan.docs)} record{'s' if len(plan.docs) != 1 else ''}"
        return plan


ACTIONS: dict[str, Action] = {
    a.name: a
    for a in (TagAction(), MoveEditionsAction(), SetAuthorAction(), MergeEditionsAction(), FlagAction(), DeleteAction(), SetFieldAction(), SetIdentifierAction())
}

# The endpoint refuses anything not listed here; the workbench offers the same set.
ENABLED_ACTIONS: frozenset[str] = frozenset(ACTIONS)


# ── Orchestration ────────────────────────────────────────────────────


def _prepare(
    action: str, items: list[dict[str, Any]], params: dict[str, Any], ctx: Ctx
) -> tuple[Action, dict[str, dict[str, Any]], Plan, list[dict[str, Any]], dict[str, str]]:
    act = ACTIONS.get(action)
    if not act:
        raise BatchError(f"Unknown action {action!r}.")
    if act.super_only and not ctx.is_super:
        raise BatchError("Only super-librarians can run this action.", 403)
    if len(items) > MAX_ITEMS:
        raise BatchError(f"A batch is limited to {MAX_ITEMS} records.")
    keys: list[str] = []
    for it in items:
        if k := normalize_key(it.get("key", "")):
            keys.append(k)
    if act.needs_items and not keys:
        raise BatchError("No records selected.")
    docs, resolved, missing = load_docs(keys)
    warnings: list[dict[str, Any]] = []
    warnings.extend(_warn("info", "redirect_followed", f"{olid(k)} redirects to {olid(v)}; using {olid(v)}.", key=v) for k, v in resolved.items())
    warnings.extend(_warn("warn", "missing", f"{olid(k)} does not exist and was skipped.", key=k) for k in missing)

    if act.fold_editions_to_works:
        work_keys = []
        for k, d in list(docs.items()):
            if key_type(k) == "edition":
                wk = next(iter(ref_keys(d.get("works"))), None)
                docs.pop(k)
                if wk:
                    work_keys.append(wk)
                    warnings.append(_warn("info", "edition_folded", f"{olid(k)} is an edition; its work {olid(wk)} is used instead.", key=wk))
        if work_keys:
            more, _r, _m = load_docs([w for w in work_keys if w not in docs])
            docs.update(more)

    skipped = [k for k in docs if key_type(k) not in act.applies_to]
    for k in skipped:
        docs.pop(k)
        warnings.append(_warn("info", "skipped_type", f"{olid(k)} is not a {' or '.join(sorted(act.applies_to))}; skipped.", key=k))
    if act.needs_items and not docs:
        raise BatchError("None of the selected records apply to this action.")

    plan = act.plan(docs, params, ctx)
    warnings.extend(plan.warnings)
    warnings.extend(checks_for(action, docs, params, plan.extra))
    return act, docs, plan, warnings, resolved


def _public_plan(plan: Plan) -> dict[str, Any]:
    target = plan.extra.get("master") or (plan.extra.get("target") or {}).get("key")
    return {"changes": plan.changes, "creates": plan.creates, "summary": plan.summary, "docs_touched": len(plan.docs), "target": target}


def _stored_items(docs: dict[str, dict[str, Any]], creates: list[str]) -> list[dict[str, Any]]:
    """What the batch row remembers per record: key, pre-batch revision, and a title for listings."""
    items = [{"key": k, "before_revision": d.get("revision"), "title": _title(d)} for k, d in docs.items()]
    return items + [{"key": k, "before_revision": 0} for k in creates]


def run(
    user: Any,
    action: str,
    items: list[dict[str, Any]],
    params: dict[str, Any] | None = None,
    dry_run: bool = True,
    overrides: list[str] | None = None,
    comment: str | None = None,
) -> dict[str, Any]:
    params = params or {}
    overrides = list(overrides or [])
    ctx = Ctx(username=user.key.split("/")[-1], is_super=bool(user.is_super_librarian_or_higher()), dry_run=dry_run)
    act, docs, plan, warnings, resolved = _prepare(action, items, params, ctx)

    blocks = [w for w in warnings if w["level"] == "block" and w["code"] not in overrides]
    mode = "request" if (act.name == "flag" or not ctx.is_super) else "apply"
    # A request may carry unacknowledged blocks: the super-librarian who applies
    # it sees them again and must acknowledge them then.
    can_apply = mode == "request" or not blocks
    revisions = {k: d.get("revision") for k, d in docs.items()}

    out: dict[str, Any] = {
        "action": action,
        "label": act.label,
        "mode": mode,
        "can_apply": can_apply and bool(plan.docs or act.name == "flag"),
        "resolved": resolved,
        "revisions": revisions,
        "warnings": warnings,
        **_public_plan(plan),
    }
    if dry_run:
        return out

    if not out["can_apply"]:
        raise BatchError("The batch has unresolved blocking warnings.", 409, warnings=warnings)

    # Revisions the client saw must still be current.
    wanted = {nk: it["expected_revision"] for it in items if it.get("expected_revision") is not None and (nk := normalize_key(it["key"]))}
    stale = {}
    for k, rev in wanted.items():
        rk = resolved.get(k, k)
        if rk in revisions and revisions[rk] != rev:
            stale[rk] = revisions[rk]
    if stale:
        raise BatchError("Some records changed since the preview; reload and try again.", 409, stale=stale, revisions=revisions)

    stored_items = _stored_items(docs, plan.creates)

    if mode == "request":
        batch_id = LibrarianBatches.create(
            ctx.username, action, params, stored_items, plan.changes, warnings, overrides, status="requested", comment=comment, summary=plan.summary
        )
        title = f"{act.label}: {plan.summary}"
        if act.name == "flag":
            title = (
                f"Flag as {plan.extra.get('reason', 'review').replace('_', '-')}: "
                + ", ".join(_title(d) for d in list(docs.values())[:3])
                + (" …" if len(docs) > 3 else "")
            )
        mrid = CommunityEditsQueue.submit_request(
            url=f"/librarians/batch/{batch_id}",
            submitter=ctx.username,
            title=title[:200],
            comment=comment,
            mr_type=CommunityEditsQueue.TYPE["BATCH"],
        )
        LibrarianBatches.update(batch_id, mrid=mrid)
        stats.increment(f"ol.librarians.batch.{action}.requested")
        return {**out, "batch_id": batch_id, "mrid": mrid, "status": "requested"}

    return _apply(ctx, act, plan, params, stored_items, warnings, overrides, comment, existing_id=None, mrid=None)


def _apply(
    ctx: Ctx,
    act: Action,
    plan: Plan,
    params: dict[str, Any],
    stored_items: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    overrides: list[str],
    comment: str | None,
    existing_id: int | None,
    mrid: int | None,
) -> dict[str, Any]:
    if existing_id is None:
        batch_id = LibrarianBatches.create(
            ctx.username, act.name, params, stored_items, plan.changes, warnings, overrides, status="applying", comment=comment, mrid=mrid, summary=plan.summary
        )
    else:
        batch_id = existing_id
        LibrarianBatches.update(
            batch_id, status="applying", items=stored_items, changes=plan.changes, warnings=warnings, overrides=overrides, summary=plan.summary
        )
    save_comment = (comment or plan.summary or act.label)[:250]
    try:
        result = site.get().save_many(
            plan.docs,
            comment=f"{save_comment} (batch #{batch_id})",
            action="librarian-batch",
            data={"batch_id": batch_id, "action": act.name, "params": {k: v for k, v in params.items() if k != "comment"}},
        )
    except Exception as e:
        LibrarianBatches.update(batch_id, status="failed")
        logger.exception("batch %s failed", batch_id)
        raise BatchError(f"Saving failed: {getattr(e, 'message', str(e))}", 500, batch_id=batch_id) from e
    after = {r["key"]: r["revision"] for r in result or []}
    for it in stored_items:
        it["after_revision"] = after.get(it["key"])
    LibrarianBatches.update(batch_id, status="applied", items=stored_items)
    if mrid:
        CommunityEditsQueue.update_request_status(mrid, CommunityEditsQueue.STATUS["MERGED"], ctx.username, comment=comment)
    stats.increment(f"ol.librarians.batch.{act.name}.applied")
    stats.increment(f"ol.librarians.batch.{act.name}.records", n=len(plan.docs))
    for code in overrides:
        stats.increment(f"ol.librarians.batch.override.{code}")
    return {
        "status": "applied",
        "batch_id": batch_id,
        "applied": len(after),
        "failed": max(0, len(plan.docs) - len(after)),
        "summary": plan.summary,
        "changes": plan.changes,
        "creates": plan.creates,
        "revisions": after,
        "warnings": warnings,
    }


def apply_requested(user: Any, batch_id: int, comment: str | None = None, overrides: list[str] | None = None) -> dict[str, Any]:
    """A super-librarian applies a batch a librarian requested. The plan is rebuilt
    against current records, and blocks must be acknowledged by the applier."""
    batch = LibrarianBatches.get(batch_id)
    if not batch:
        raise BatchError("Batch not found.", 404)
    if batch["status"] != "requested":
        raise BatchError(f"Batch is {batch['status']}, not requested.", 409)
    ctx = Ctx(username=user.key.split("/")[-1], is_super=bool(user.is_super_librarian_or_higher()), dry_run=False)
    if not ctx.is_super:
        raise BatchError("Only super-librarians can apply requested batches.", 403)
    items = [{"key": it["key"]} for it in batch["items"] if it.get("before_revision")]
    act, docs, plan, warnings, _resolved = _prepare(batch["action"], items, batch["params"] or {}, ctx)
    if act.name == "flag":
        raise BatchError("A flag is a report, not an edit; act on it with delete or merge.", 400)
    overrides = uniq(list(batch.get("overrides") or []) + list(overrides or []))
    blocks = [w for w in warnings if w["level"] == "block" and w["code"] not in overrides]
    if blocks:
        raise BatchError("The batch has blocking warnings; acknowledge them to apply.", 409, warnings=warnings)
    stored_items = _stored_items(docs, plan.creates)
    return _apply(
        ctx, act, plan, batch["params"] or {}, stored_items, warnings, overrides, comment or batch.get("comment"), existing_id=batch_id, mrid=batch.get("mrid")
    )


def decline_requested(user: Any, batch_id: int, comment: str | None = None) -> dict[str, Any]:
    batch = LibrarianBatches.get(batch_id)
    if not batch:
        raise BatchError("Batch not found.", 404)
    username = user.key.split("/")[-1]
    if not user.is_super_librarian_or_higher():
        raise BatchError("Only super-librarians can decline requested batches.", 403)
    if batch["status"] != "requested":
        raise BatchError(f"Batch is {batch['status']}, not requested.", 409)
    LibrarianBatches.update(batch_id, status="declined")
    if batch.get("mrid"):
        CommunityEditsQueue.update_request_status(batch["mrid"], CommunityEditsQueue.STATUS["DECLINED"], username, comment=comment)
    return {"status": "declined", "batch_id": batch_id}


def revert(user: Any, batch_id: int, key: str | None = None, force: bool = False) -> dict[str, Any]:
    """Restore every record the batch touched (or one of them) to its pre-batch revision.

    A record edited again since the batch is left alone (409 with ``moved``)
    unless ``force`` is set, so an undo never silently discards someone's later work."""
    batch = LibrarianBatches.get(batch_id)
    if not batch:
        raise BatchError("Batch not found.", 404)
    if batch["status"] not in ("applied", "partially_reverted"):
        raise BatchError(f"Batch is {batch['status']}; only applied batches can be reverted.", 409)
    username = user.key.split("/")[-1]
    if not (user.is_super_librarian_or_higher() or username == batch["username"]):
        raise BatchError("Only the batch's author or a super-librarian can revert it.", 403)
    items = batch["items"]
    if key:
        nk = normalize_key(key)
        items = [it for it in items if it["key"] == nk]
        if not items:
            raise BatchError("That record is not part of this batch.", 404)
    current = {t.key: t.dict().get("revision") for t in site.get().get_many([it["key"] for it in items])}
    moved = {
        it["key"]: current[it["key"]]
        for it in items
        if not it.get("reverted") and it.get("after_revision") and current.get(it["key"]) not in (None, it["after_revision"])
    }
    if moved and not force:
        raise BatchError("Some records were edited after the batch; revert them one at a time or force the revert.", 409, moved=moved)
    docs = []
    for it in items:
        if it.get("reverted"):
            continue
        before = it.get("before_revision") or 0
        if before == 0:
            docs.append({"key": it["key"], "type": {"key": "/type/delete"}})
        else:
            thing = site.get().get(it["key"], before)
            if thing is None:
                raise BatchError(f"Could not load {it['key']} at revision {before}.", 500)
            docs.append(thing.dict())
    if not docs:
        return {"status": batch["status"], "batch_id": batch_id, "reverted": 0}
    try:
        result = site.get().save_many(docs, comment=f"Revert batch #{batch_id}", action="librarian-batch-revert", data={"batch_id": batch_id})
    except Exception as e:
        logger.exception("revert of batch %s failed", batch_id)
        raise BatchError(f"Revert failed: {getattr(e, 'message', str(e))}", 500) from e
    reverted = {r["key"] for r in result or []}
    for it in batch["items"]:
        if it["key"] in reverted:
            it["reverted"] = True
    status = "reverted" if all(it.get("reverted") for it in batch["items"]) else "partially_reverted"
    LibrarianBatches.update(batch_id, status=status, items=batch["items"])
    stats.increment(f"ol.librarians.batch.{batch['action']}.reverted")
    return {"status": status, "batch_id": batch_id, "reverted": len(reverted)}
