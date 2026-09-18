"""Where librarian batches live, without a table of their own.

An applied batch *is* its changeset. batch_ops saves every record in one
``save_many`` with action ``librarian-batch`` and a data blob (a batch uid, the
action, params, summary, warnings, acknowledgements and a capped change list),
so the batch id is the changeset id and the edit history is the audit trail.
A revert, whole or per record, is another changeset with action
``librarian-batch-revert`` whose ``data.parent_changeset`` points back, the
same link merge undo uses.

A requested batch writes nothing to records, so it waits in the site store as
a ``librarian-batch-request`` document until a super-librarian applies or
declines it. Only what is queried is indexed (status, username, and the record
keys while the request is open); the rest rides in one JSON string.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from openlibrary.utils.request_context import site

logger = logging.getLogger("openlibrary.librarian_batches")

APPLY_KIND = "librarian-batch"
REVERT_KIND = "librarian-batch-revert"
REQUEST_TYPE = "librarian-batch-request"
REQUEST_SEQ = "librarian-batch-request"
MAX_STORED_CHANGES = 500
MAX_REVERT_SCAN = 1000


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0, tzinfo=None).isoformat()


def _username(author: Any) -> str | None:
    key = author.get("key") if isinstance(author, dict) else getattr(author, "key", None)
    return key.rsplit("/", 1)[-1] if key else None


# ── Applied batches (changesets) ─────────────────────────────────────


def new_uid() -> str:
    return uuid.uuid4().hex


def batch_data(
    uid: str,
    action: str,
    params: dict[str, Any],
    summary: str,
    warnings: list[dict[str, Any]],
    overrides: list[str],
    changes: list[dict[str, Any]],
    creates: list[str],
    titles: dict[str, str],
    request_id: int | None = None,
    mrid: int | None = None,
) -> dict[str, Any]:
    """The changeset data for an applied batch. Top-level strings and ints are
    indexed by infobase, which is how ``find_applied`` locates it."""
    data: dict[str, Any] = {
        "batch": uid,
        "workbench_action": action,
        "params": {k: v for k, v in params.items() if k != "comment"},
        "summary": summary[:250],
        "warnings": warnings,
        "overrides": overrides,
        "changes": changes[:MAX_STORED_CHANGES],
        "changes_total": len(changes),
        "creates": creates,
        "titles": dict(list(titles.items())[:MAX_STORED_CHANGES]),
    }
    if request_id is not None:
        data["request"] = request_id
    if mrid is not None:
        data["mrid"] = mrid
    return data


def find_applied(uid: str) -> int | None:
    """The changeset id of the batch saved with ``uid``."""
    rows = site.get().recentchanges({"kind": APPLY_KIND, "data": {"batch": uid}, "limit": 1})
    return int(rows[0].id) if rows else None


def _reverted_keys(parent_ids: list[int], begin: str | None = None) -> dict[int, set[str]]:
    """{batch id: keys reverted by any of its revert changesets}.

    Infobase hands changeset ids back as strings and indexes changeset data as
    text (an int in a ``data`` filter is a 500), so ids are compared as ints and
    queried as strings."""
    out: dict[int, set[str]] = {int(pid): set() for pid in parent_ids}
    if not out:
        return out
    if len(out) == 1:
        query: dict[str, Any] = {"kind": REVERT_KIND, "data": {"parent_changeset": str(next(iter(out)))}, "limit": MAX_REVERT_SCAN}
    else:
        query = {"kind": REVERT_KIND, "limit": MAX_REVERT_SCAN}
        if begin:
            query["begin_date"] = begin
    for cs in site.get().recentchanges(query):
        d = cs.dict()
        parent = (d.get("data") or {}).get("parent_changeset")
        if parent is not None and int(parent) in out:
            out[int(parent)].update(c["key"] for c in d.get("changes") or [])
    return out


def _batch_view(d: dict[str, Any], reverted: set[str], full: bool = True) -> dict[str, Any]:
    data = d.get("data") or {}
    batch_id = int(d["id"])
    titles = data.get("titles") or {}
    items = [
        {
            "key": c["key"],
            "title": titles.get(c["key"]),
            "before_revision": c["revision"] - 1,
            "after_revision": c["revision"],
            "reverted": c["key"] in reverted,
        }
        for c in d.get("changes") or []
    ]
    if items and all(it["reverted"] for it in items):
        status = "reverted"
    elif any(it["reverted"] for it in items):
        status = "partially_reverted"
    else:
        status = "applied"
    view = {
        "kind": "batch",
        "id": batch_id,
        "url": f"/librarians/batch/{batch_id}",
        "status": status,
        "action": data.get("workbench_action"),
        "username": _username(d.get("author")),
        "created": str(d.get("timestamp") or ""),
        "comment": d.get("comment") or "",
        "summary": data.get("summary") or "",
        "item_count": len(items),
        "request": data.get("request"),
        "mrid": data.get("mrid"),
    }
    if full:
        view.update(
            items=items,
            params=data.get("params") or {},
            warnings=data.get("warnings") or [],
            overrides=data.get("overrides") or [],
            changes=data.get("changes") or [],
            changes_total=data.get("changes_total") or 0,
        )
    return view


def get_batch(batch_id: int) -> dict[str, Any] | None:
    try:
        cs = site.get().get_change(batch_id)
    except Exception:  # noqa: BLE001
        return None
    if not cs:
        return None
    d = cs.dict()
    if d.get("kind") != APPLY_KIND:
        return None
    return _batch_view(d, _reverted_keys([int(d["id"])])[int(d["id"])])


def list_batches(username: str | None = None, limit: int = 30, offset: int = 0) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"kind": APPLY_KIND, "limit": limit, "offset": offset}
    if username:
        query["author"] = f"/people/{username}"
    rows = [cs.dict() for cs in site.get().recentchanges(query)]
    if not rows:
        return []
    oldest = min(str(r.get("timestamp") or "") for r in rows) or None
    reverted = _reverted_keys([int(r["id"]) for r in rows], begin=oldest)
    return [_batch_view(r, reverted.get(int(r["id"]), set()), full=False) for r in rows]


def revert_data(batch_id: int) -> dict[str, Any]:
    return {"parent_changeset": batch_id}


# ── Requested batches (store documents) ──────────────────────────────


def _request_key(request_id: int) -> str:
    return f"/librarians/requests/{request_id}"


def _request_view(doc: dict[str, Any], full: bool = True) -> dict[str, Any]:
    payload = json.loads(doc.get("payload") or "{}")
    rid = int(doc["rid"])
    view = {
        "kind": "request",
        "id": rid,
        "url": f"/librarians/request/{rid}",
        "status": doc.get("status"),
        "action": doc.get("action"),
        "username": doc.get("username"),
        "created": doc.get("created") or "",
        "updated": doc.get("updated") or "",
        "comment": payload.get("comment") or "",
        "summary": payload.get("summary") or "",
        "item_count": len(payload.get("items") or []),
        "mrid": payload.get("mrid"),
        "batch": payload.get("batch"),
    }
    if full:
        # Same item shape as an applied batch, so one review page renders both.
        items = [
            {"key": it["key"], "title": it.get("title"), "before_revision": it.get("before_revision"), "after_revision": None, "reverted": False}
            for it in payload.get("items") or []
        ]
        view.update(
            items=items,
            params=payload.get("params") or {},
            warnings=payload.get("warnings") or [],
            overrides=payload.get("overrides") or [],
            changes=payload.get("changes") or [],
            changes_total=payload.get("changes_total") or 0,
        )
    return view


def create_request(
    username: str,
    action: str,
    params: dict[str, Any],
    items: list[dict[str, Any]],
    changes: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    overrides: list[str],
    summary: str,
    comment: str | None = None,
) -> int:
    rid = int(site.get().seq.next_value(REQUEST_SEQ))
    now = _now()
    doc = {
        "type": REQUEST_TYPE,
        "rid": str(rid),
        "status": "requested",
        "username": username,
        "action": action,
        "open_keys": [it["key"] for it in items],
        "created": now,
        "updated": now,
        "payload": json.dumps(
            {
                "params": params,
                "items": items,
                "changes": changes[:MAX_STORED_CHANGES],
                "changes_total": len(changes),
                "warnings": warnings,
                "overrides": overrides,
                "summary": summary,
                "comment": comment,
            }
        ),
    }
    site.get().store[_request_key(rid)] = doc
    return rid


def _load_request(request_id: int) -> dict[str, Any] | None:
    return site.get().store.get(_request_key(request_id))


def get_request(request_id: int) -> dict[str, Any] | None:
    doc = _load_request(request_id)
    return _request_view(doc) if doc else None


def update_request(request_id: int, status: str | None = None, **payload_fields: Any) -> None:
    """Set the status and/or payload fields. A decided request stops being open on its records."""
    doc = _load_request(request_id)
    if not doc:
        return
    doc = dict(doc)
    if status:
        doc["status"] = status
        if status != "requested":
            doc["open_keys"] = []
    if payload_fields:
        payload = json.loads(doc.get("payload") or "{}")
        payload.update(payload_fields)
        doc["payload"] = json.dumps(payload)
    doc["updated"] = _now()
    site.get().store[_request_key(request_id)] = doc


def list_requests(username: str | None = None, status: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
    store = site.get().store
    if username:
        docs = store.values(type=REQUEST_TYPE, name="username", value=username, limit=limit)
    elif status:
        docs = store.values(type=REQUEST_TYPE, name="status", value=status, limit=limit)
    else:
        docs = store.values(type=REQUEST_TYPE, limit=limit)
    views = [_request_view(d, full=False) for d in docs]
    return [v for v in views if not status or v["status"] == status]


def open_requests_for_key(key: str) -> list[dict[str, Any]]:
    docs = site.get().store.values(type=REQUEST_TYPE, name="open_keys", value=key, limit=20)
    return [_request_view(d, full=False) for d in docs if d.get("status") == "requested"]
