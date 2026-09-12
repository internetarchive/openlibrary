"""JSON behind the librarian workbench (/librarians/workbench): the grid query,
worklists, record detail for the panel, and the batch operations every edit
goes through. Logic lives in openlibrary/core/{workbench,batch_ops,record_context}.py;
this file is routing, validation and the role split.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from openlibrary.accounts import get_current_user
from openlibrary.core import batch_ops, record_context, workbench
from openlibrary.core.librarian_batches import LibrarianBatches
from openlibrary.fastapi.auth import LibrarianDep  # noqa: TC001
from openlibrary.utils.request_context import req_context, web_ctx_ip

router = APIRouter(tags=["librarians"])


def _user():
    user = get_current_user()
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def _batch_error(e: batch_ops.BatchError) -> HTTPException:
    return HTTPException(status_code=e.status, detail={"error": e.message, **e.extra})


def _wb_error(e: workbench.WorkbenchError) -> HTTPException:
    return HTTPException(status_code=e.status, detail={"error": e.message})


def _client_ip() -> str:
    return req_context.get().x_forwarded_for or "127.0.0.1"


# ── Workbench ────────────────────────────────────────────────────────


class FilterItem(BaseModel):
    id: str
    value: Any = None


class QueryBody(BaseModel):
    type: str = "edition"
    q: str = Field(default="", max_length=500)
    filters: list[FilterItem] = Field(default_factory=list)
    sort: str = "relevance"
    page: int = Field(default=1, ge=1, le=200)
    rows: int = Field(default=50, ge=1, le=workbench.MAX_ROWS)


@router.post("/librarians/workbench/query.json")
def workbench_query(_: LibrarianDep, body: QueryBody) -> dict[str, Any]:
    try:
        return workbench.run_query(body.type, body.q, [f.model_dump() for f in body.filters], body.sort, body.page, body.rows)
    except workbench.WorkbenchError as e:
        raise _wb_error(e) from e


@router.get("/librarians/workbench/keys.json")
def workbench_keys(_: LibrarianDep, keys: Annotated[str, Query(max_length=20000)]) -> dict[str, Any]:
    """Pasted OLIDs or URLs, one grid per record type."""
    wanted = [k for k in (s.strip() for s in keys.replace("\n", ",").split(",")) if k]
    return {"groups": workbench.hydrate_keys(wanted[: workbench.MAX_ROWS * 3])}


@router.get("/librarians/workbench/config.json")
def workbench_config(auth: LibrarianDep) -> dict[str, Any]:
    user = _user()
    return {
        "username": auth.username,
        "is_super": bool(user.is_super_librarian_or_higher()),
        "filters": workbench.public_filters(),
        "sorts": {t: list(s) for t, s in workbench.SORTS.items()},
        "actions": [
            {"name": a.name, "label": a.label, "applies_to": sorted(a.applies_to), "super_only": a.super_only}
            for a in batch_ops.ACTIONS.values()
            if a.name in batch_ops.ENABLED_ACTIONS
        ],
        "settable_fields": batch_ops.SETTABLE_FIELDS,
        "max_batch": batch_ops.MAX_ITEMS,
        "max_rows": workbench.MAX_ROWS,
    }


@router.get("/librarians/workbench/worklists.json")
def worklists(_: LibrarianDep, counts: bool = True) -> dict[str, Any]:
    return {"worklists": workbench.list_worklists(with_counts=counts)}


class WorklistBody(BaseModel):
    name: str = Field(max_length=80)
    type: str = "edition"
    q: str = Field(default="", max_length=500)
    filters: list[FilterItem] = Field(default_factory=list)
    sort: str = "relevance"


@router.post("/librarians/workbench/worklists.json")
def create_worklist(auth: LibrarianDep, body: WorklistBody) -> dict[str, Any]:
    user = _user()
    try:
        return workbench.save_worklist(
            auth.username, {**body.model_dump(), "filters": [f.model_dump() for f in body.filters]}, is_super=bool(user.is_super_librarian_or_higher())
        )
    except workbench.WorkbenchError as e:
        raise _wb_error(e) from e


@router.put("/librarians/workbench/worklists/{wid}.json")
def update_worklist(auth: LibrarianDep, wid: str, body: WorklistBody) -> dict[str, Any]:
    user = _user()
    try:
        return workbench.save_worklist(
            auth.username, {**body.model_dump(), "filters": [f.model_dump() for f in body.filters]}, wid=wid, is_super=bool(user.is_super_librarian_or_higher())
        )
    except workbench.WorkbenchError as e:
        raise _wb_error(e) from e


@router.delete("/librarians/workbench/worklists/{wid}.json")
def delete_worklist(auth: LibrarianDep, wid: str) -> dict[str, Any]:
    user = _user()
    try:
        workbench.delete_worklist(auth.username, wid, is_super=bool(user.is_super_librarian_or_higher()))
    except workbench.WorkbenchError as e:
        raise _wb_error(e) from e
    return {"deleted": wid}


@router.get("/librarians/workbench/record.json")
def workbench_record(_: LibrarianDep, key: str) -> dict[str, Any]:
    """Everything the record panel shows: the hydrated row, the editable fields, and the full health strip."""
    nk = record_context.normalize_key(key)
    if not nk:
        raise HTTPException(status_code=400, detail={"error": "Not a record key"})
    rt = record_context.key_type(nk)
    rows = workbench.hydrate(rt or "edition", [nk])
    if not rows:
        raise HTTPException(status_code=404, detail={"error": "Record not found"})
    row = rows[0]
    docs, _r, _m = record_context.load_docs([row["key"]])
    doc = docs.get(row["key"]) or {}
    fields = {}
    for name, kind in batch_ops.SETTABLE_FIELDS.get(row["type"], {}).items():
        v = doc.get(name)
        if kind == "keys":
            v = [record_context.olid(k) for k in record_context.ref_keys(v)]
        fields[name] = {"kind": kind, "value": v}
    return {"record": row, "fields": fields, "health": record_context.health(row["key"])}


# ── Batches ──────────────────────────────────────────────────────────


class BatchItem(BaseModel):
    key: str
    expected_revision: int | None = None


class BatchBody(BaseModel):
    action: str
    items: list[BatchItem] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = True
    overrides: list[str] = Field(default_factory=list)
    comment: str | None = Field(default=None, max_length=500)


@router.post("/librarians/batch.json")
def batch(_: LibrarianDep, body: BatchBody) -> dict[str, Any]:
    if body.action not in batch_ops.ENABLED_ACTIONS:
        raise HTTPException(status_code=400, detail={"error": f"Action {body.action!r} is not enabled."})
    user = _user()
    with web_ctx_ip(_client_ip()):
        try:
            return batch_ops.run(
                user,
                body.action,
                [it.model_dump() for it in body.items],
                body.params,
                dry_run=body.dry_run,
                overrides=body.overrides,
                comment=body.comment,
            )
        except batch_ops.BatchError as e:
            raise _batch_error(e) from e


@router.get("/librarians/batches.json")
def batches(auth: LibrarianDep, mine: bool = True, status: str | None = None, limit: int = 30, offset: int = 0) -> dict[str, Any]:
    user = _user()
    username = auth.username if (mine or not user.is_super_librarian_or_higher()) else None
    rows = LibrarianBatches.list_batches(username=username, status=status, limit=min(limit, 100), offset=offset)
    return {"batches": rows}


@router.get("/librarians/batch/{batch_id}.json")
def batch_detail(_: LibrarianDep, batch_id: int) -> dict[str, Any]:
    row = LibrarianBatches.get(batch_id)
    if not row:
        raise HTTPException(status_code=404, detail={"error": "Batch not found"})
    return row


class BatchDecisionBody(BaseModel):
    comment: str | None = Field(default=None, max_length=500)
    overrides: list[str] = Field(default_factory=list)


@router.post("/librarians/batch/{batch_id}/apply.json")
def batch_apply(_: LibrarianDep, batch_id: int, body: BatchDecisionBody | None = None) -> dict[str, Any]:
    user = _user()
    with web_ctx_ip(_client_ip()):
        try:
            return batch_ops.apply_requested(user, batch_id, comment=body.comment if body else None, overrides=body.overrides if body else None)
        except batch_ops.BatchError as e:
            raise _batch_error(e) from e


@router.post("/librarians/batch/{batch_id}/decline.json")
def batch_decline(_: LibrarianDep, batch_id: int, body: BatchDecisionBody | None = None) -> dict[str, Any]:
    user = _user()
    try:
        return batch_ops.decline_requested(user, batch_id, comment=body.comment if body else None)
    except batch_ops.BatchError as e:
        raise _batch_error(e) from e


class RevertBody(BaseModel):
    key: str | None = None
    force: bool = False


@router.post("/librarians/batch/{batch_id}/revert.json")
def batch_revert(_: LibrarianDep, batch_id: int, body: RevertBody | None = None) -> dict[str, Any]:
    user = _user()
    with web_ctx_ip(_client_ip()):
        try:
            return batch_ops.revert(user, batch_id, key=body.key if body else None, force=bool(body and body.force))
        except batch_ops.BatchError as e:
            raise _batch_error(e) from e


# ── Context ──────────────────────────────────────────────────────────


@router.get("/librarians/context.json")
def context(_: LibrarianDep, key: str) -> dict[str, Any]:
    nk = record_context.normalize_key(key)
    if not nk:
        raise HTTPException(status_code=400, detail={"error": "Not a record key"})
    return record_context.health(nk)


@router.get("/librarians/checks.json")
def checks(_: LibrarianDep, action: str, keys: str) -> dict[str, Any]:
    """Pre-flight checks for the merge pages, which do their own writing."""
    if action not in ("merge_works", "merge_authors"):
        raise HTTPException(status_code=400, detail={"error": "Unknown check"})
    wanted = [nk for k in keys.split(",") if (nk := record_context.normalize_key(k))][:100]
    docs, resolved, missing = record_context.load_docs(wanted)
    warnings = record_context.checks_for(action, docs, {})
    warnings.extend({"level": "warn", "code": "missing", "text": f"{record_context.olid(k)} does not exist.", "key": k} for k in missing)
    return {"action": action, "warnings": warnings, "resolved": resolved, "keys": list(docs)}
