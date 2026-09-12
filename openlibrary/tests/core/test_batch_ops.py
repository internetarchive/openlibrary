"""Tests for openlibrary.core.batch_ops: plans, previews, the role split,
revision checks, apply and revert — with the site, the batches table and the
queue faked."""

from unittest.mock import MagicMock

import pytest

from openlibrary.core import batch_ops
from openlibrary.core import record_context as rc
from openlibrary.utils.request_context import site


class FakeThing:
    def __init__(self, doc):
        self._doc = doc
        self.key = doc["key"]

    def dict(self):
        return dict(self._doc)


class FakeSite:
    def __init__(self, docs):
        self.docs = {d["key"]: dict(d) for d in docs}
        self.history = {}
        self.saved = []
        self.next_key = 100

    def get(self, key, revision=None):
        if revision is not None:
            doc = self.history.get((key, revision))
            return FakeThing(doc) if doc else None
        return FakeThing(self.docs[key]) if key in self.docs else None

    def get_many(self, keys, raw=False):
        return [FakeThing(self.docs[k]) for k in keys if k in self.docs]

    def new_key(self, type_):
        self.next_key += 1
        return f"/works/OL{self.next_key}W"

    def things(self, query, details=False):
        if query.get("type") == "/type/edition" and query.get("works"):
            assert isinstance(query["works"], str), "one work per query"
            return [k for k, d in self.docs.items() if any(w["key"] == query["works"] for w in d.get("works", []))]
        return []

    def recentchanges(self, query):
        return []

    def save_many(self, docs, comment=None, data=None, action=None):
        self.saved.append({"docs": docs, "comment": comment, "action": action, "data": data})
        out = []
        for d in docs:
            key = d["key"]
            old = self.docs.get(key)
            rev = (old.get("revision", 0) if old else 0) + 1
            if old:
                self.history[(key, old.get("revision", 0))] = dict(old)
            self.docs[key] = {**d, "revision": rev}
            out.append({"key": key, "revision": rev})
        return out


WORK = {
    "key": "/works/OL1W",
    "type": {"key": "/type/work"},
    "title": "Shiloh",
    "subjects": ["Dogs"],
    "authors": [{"author": {"key": "/authors/OL1A"}}],
    "revision": 2,
}
WORK2 = {"key": "/works/OL2W", "type": {"key": "/type/work"}, "title": "Shiloh season", "authors": [{"author": {"key": "/authors/OL1A"}}], "revision": 1}
ED1 = {
    "key": "/books/OL1M",
    "type": {"key": "/type/edition"},
    "title": "Shiloh",
    "works": [{"key": "/works/OL1W"}],
    "authors": [{"key": "/authors/OL1A"}],
    "isbn_13": ["9780000000001"],
    "publishers": ["Atheneum"],
    "revision": 1,
}
ED2 = {
    "key": "/books/OL2M",
    "type": {"key": "/type/edition"},
    "title": "Shiloh",
    "works": [{"key": "/works/OL1W"}],
    "isbn_10": ["0000000002"],
    "ocaid": "shiloh00",
    "revision": 4,
}
AUTHOR = {"key": "/authors/OL1A", "type": {"key": "/type/author"}, "name": "Phyllis Reynolds Naylor", "revision": 1}
AUTHOR2 = {"key": "/authors/OL2A", "type": {"key": "/type/author"}, "name": "P. R. Naylor", "revision": 1}


def user(is_super=True):
    u = MagicMock()
    u.key = "/people/tester"
    u.is_super_librarian_or_higher.return_value = is_super
    return u


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    s = FakeSite([WORK, WORK2, ED1, ED2, AUTHOR, AUTHOR2])
    site.set(s)
    monkeypatch.setattr(rc, "wikidata_for", lambda doc: None)
    monkeypatch.setattr(rc, "_solr_doc", lambda key, fields: {})
    monkeypatch.setattr(rc, "_lists_count", lambda key: 0)
    monkeypatch.setattr(rc, "_readinglog_count", lambda key: 0)
    monkeypatch.setattr(batch_ops.stats, "increment", lambda *a, **k: None)
    rows = {}
    batches = MagicMock()

    def create(username, action, params, items, changes, warnings, overrides, status="requested", comment=None, mrid=None, summary=None):
        bid = len(rows) + 1
        rows[bid] = {
            "id": bid,
            "username": username,
            "action": action,
            "params": params,
            "items": items,
            "changes": changes,
            "warnings": warnings,
            "overrides": overrides,
            "status": status,
            "comment": comment,
            "mrid": mrid,
            "summary": summary,
        }
        return bid

    def update(bid, **fields):
        rows[bid].update(fields)

    batches.create.side_effect = create
    batches.update.side_effect = update
    batches.get.side_effect = rows.get
    monkeypatch.setattr(batch_ops, "LibrarianBatches", batches)
    queue = MagicMock()
    queue.TYPE = {"BATCH": 3, "WORK_MERGE": 1, "AUTHOR_MERGE": 2}
    queue.STATUS = {"PENDING": 1, "MERGED": 2, "DECLINED": 0}
    queue.submit_request.return_value = 77
    monkeypatch.setattr(batch_ops, "CommunityEditsQueue", queue)
    return {"site": s, "rows": rows, "queue": queue}


def test_tag_preview_folds_editions_to_their_work():
    out = batch_ops.run(user(), "tag", [{"key": "OL1W"}, {"key": "OL1M"}], {"add": {"subjects": ["Dogs", "Virginia"]}}, dry_run=True)
    assert out["mode"] == "apply"
    assert out["docs_touched"] == 1
    assert out["changes"][0]["to"] == ["Dogs", "Virginia"]
    assert any(w["code"] == "edition_folded" for w in out["warnings"])


def test_unknown_action_and_super_only():
    with pytest.raises(batch_ops.BatchError) as e:
        batch_ops.run(user(), "nope", [{"key": "OL1W"}])
    assert e.value.status == 400
    with pytest.raises(batch_ops.BatchError) as e:
        batch_ops.run(user(is_super=False), "delete", [{"key": "OL1W"}])
    assert e.value.status == 403


def test_move_editions_to_existing_and_new_work(fakes):
    out = batch_ops.run(user(), "move_editions", [{"key": "OL1M"}], {"target": "OL2W"}, dry_run=True)
    assert out["changes"] == [{"key": "/books/OL1M", "field": "works", "from": ["/works/OL1W"], "to": ["/works/OL2W"]}]
    new = batch_ops.run(user(), "move_editions", [{"key": "OL1M"}, {"key": "OL2M"}], {"target": "new"}, dry_run=True)
    assert new["creates"] == [batch_ops.NEW_WORK_KEY]
    assert any(c["field"] == "(new work)" and c["to"] == "Shiloh" for c in new["changes"])
    assert fakes["site"].next_key == 100, "a preview must not consume a key"
    applied = batch_ops.run(user(), "move_editions", [{"key": "OL1M"}, {"key": "OL2M"}], {"target": "new"}, dry_run=False)
    assert applied["creates"] == ["/works/OL101W"]
    assert fakes["site"].docs["/books/OL1M"]["works"] == [{"key": "/works/OL101W"}]


def test_set_author_fans_out_per_work(fakes):
    out = batch_ops.run(user(), "set_author", [{"key": "OL1W"}, {"key": "OL2W"}], {"author": "OL2A", "mode": "add", "include_editions": True}, dry_run=True)
    keys = {c["key"] for c in out["changes"]}
    assert keys == {"/works/OL1W", "/works/OL2W", "/books/OL1M"}


def test_set_author_replace_reaches_editions(fakes):
    out = batch_ops.run(user(), "set_author", [{"key": "OL1W"}], {"author": "OL2A", "replace": "OL1A", "include_editions": True}, dry_run=True)
    keys = {c["key"] for c in out["changes"]}
    assert keys == {"/works/OL1W", "/books/OL1M"}  # OL2M has no authors of its own


def test_merge_editions_unions_identifiers_and_redirects_dupes():
    out = batch_ops.run(user(), "merge_editions", [{"key": "OL1M"}, {"key": "OL2M"}], {}, dry_run=True)
    fields = {(c["key"], c["field"]) for c in out["changes"]}
    assert ("/books/OL1M", "isbn_10") in fields
    assert ("/books/OL1M", "ocaid") in fields
    assert ("/books/OL2M", "type") in fields


def test_set_field_rejects_unknown_field():
    with pytest.raises(batch_ops.BatchError):
        batch_ops.run(user(), "set_field", [{"key": "OL1M"}], {"field": "title", "value": "x"}, dry_run=True)
    out = batch_ops.run(user(), "set_field", [{"key": "OL1M"}], {"field": "publishers", "value": ["Scholastic"], "mode": "append"}, dry_run=True)
    assert out["changes"][0]["to"] == ["Atheneum", "Scholastic"]


def test_librarian_request_files_a_queue_row(fakes):
    out = batch_ops.run(user(is_super=False), "tag", [{"key": "OL1W"}], {"add": {"subjects": ["Virginia"]}}, dry_run=False)
    assert out["status"] == "requested"
    assert out["mrid"] == 77
    fakes["queue"].submit_request.assert_called_once()
    assert fakes["rows"][1]["status"] == "requested"
    assert fakes["site"].saved == []


def test_apply_writes_one_save_many_and_records_revisions(fakes):
    out = batch_ops.run(user(), "tag", [{"key": "OL1W", "expected_revision": 2}], {"add": {"subjects": ["Virginia"]}}, dry_run=False, comment="test")
    assert out["status"] == "applied"
    assert out["applied"] == 1
    saved = fakes["site"].saved
    assert len(saved) == 1
    assert saved[0]["action"] == "librarian-batch"
    assert saved[0]["comment"].startswith("test")
    assert fakes["rows"][1]["items"][0]["after_revision"] == 3


def test_apply_refuses_stale_revisions():
    with pytest.raises(batch_ops.BatchError) as e:
        batch_ops.run(user(), "tag", [{"key": "OL1W", "expected_revision": 1}], {"add": {"subjects": ["Virginia"]}}, dry_run=False)
    assert e.value.status == 409
    assert e.value.extra["stale"] == {"/works/OL1W": 2}


def test_revert_restores_previous_revision(fakes):
    batch_ops.run(user(), "tag", [{"key": "OL1W"}], {"add": {"subjects": ["Virginia"]}}, dry_run=False)
    assert fakes["site"].docs["/works/OL1W"]["subjects"] == ["Dogs", "Virginia"]
    out = batch_ops.revert(user(), 1)
    assert out["status"] == "reverted"
    assert fakes["site"].docs["/works/OL1W"]["subjects"] == ["Dogs"]
    assert fakes["site"].saved[-1]["action"] == "librarian-batch-revert"


def test_flag_always_requests():
    out = batch_ops.run(user(), "flag", [{"key": "OL1W"}], {"reason": "spam"}, dry_run=False)
    assert out["status"] == "requested"


def test_librarian_may_request_past_a_block(fakes):
    """A block stops an apply, not a request: the super-librarian acknowledges it when applying."""
    preview = batch_ops.run(user(is_super=False), "flag", [{"key": "OL2M"}], {"reason": "spam"}, dry_run=True)
    assert any(w["code"] == "has_scan" and w["level"] == "block" for w in preview["warnings"])
    assert preview["mode"] == "request"
    assert preview["can_apply"] is True
    filed = batch_ops.run(user(is_super=False), "flag", [{"key": "OL2M"}], {"reason": "spam"}, dry_run=False)
    assert filed["status"] == "requested"


def test_flag_is_never_applied(fakes):
    req = batch_ops.run(user(is_super=True), "flag", [{"key": "OL1W"}], {"reason": "review"}, dry_run=False)
    assert req["status"] == "requested"
    with pytest.raises(batch_ops.BatchError) as e:
        batch_ops.apply_requested(user(), req["batch_id"])
    assert e.value.status == 400


def test_apply_requested_needs_acknowledged_blocks(fakes, monkeypatch):
    """A librarian's request carries the block; the super-librarian acknowledges it at apply."""
    req = batch_ops.run(user(is_super=False), "merge_editions", [{"key": "OL1M"}, {"key": "OL2M"}], {}, dry_run=False)
    assert req["status"] == "requested"
    fakes["rows"][req["batch_id"]]["warnings"].append({"level": "block", "code": "test_block", "text": "x"})
    # The plan is rebuilt on apply, so inject the block through a check.
    monkeypatch.setattr(rc, "check_merge_editions", lambda docs: [{"level": "block", "code": "test_block", "text": "x"}])
    with pytest.raises(batch_ops.BatchError) as e:
        batch_ops.apply_requested(user(), req["batch_id"])
    assert e.value.status == 409
    out = batch_ops.apply_requested(user(), req["batch_id"], overrides=["test_block"])
    assert out["status"] == "applied"


def test_super_apply_needs_override_for_blocks(fakes):
    preview = batch_ops.run(user(), "delete", [{"key": "OL2M"}], {}, dry_run=True)
    assert preview["can_apply"] is False
    with pytest.raises(batch_ops.BatchError) as e:
        batch_ops.run(user(), "delete", [{"key": "OL2M"}], {}, dry_run=False)
    assert e.value.status == 409
    out = batch_ops.run(user(), "delete", [{"key": "OL2M"}], {}, dry_run=False, overrides=["has_scan"])
    assert out["status"] == "applied"
    assert fakes["site"].docs["/books/OL2M"]["type"] == {"key": "/type/delete"}


def test_decline_is_super_only(fakes):
    req = batch_ops.run(user(is_super=False), "tag", [{"key": "OL1W"}], {"add": {"subjects": ["Virginia"]}}, dry_run=False)
    with pytest.raises(batch_ops.BatchError) as e:
        batch_ops.decline_requested(user(is_super=False), req["batch_id"])
    assert e.value.status == 403
    out = batch_ops.decline_requested(user(), req["batch_id"])
    assert out["status"] == "declined"


def test_revert_refuses_records_edited_since(fakes):
    batch_ops.run(user(), "tag", [{"key": "OL1W"}], {"add": {"subjects": ["Virginia"]}}, dry_run=False)
    # Someone edits the work after the batch.
    fakes["site"].save_many([{**fakes["site"].docs["/works/OL1W"], "title": "Shiloh!"}])
    with pytest.raises(batch_ops.BatchError) as e:
        batch_ops.revert(user(), 1)
    assert e.value.status == 409
    assert e.value.extra["moved"] == {"/works/OL1W": 4}
    out = batch_ops.revert(user(), 1, force=True)
    assert out["status"] == "reverted"
    assert fakes["site"].docs["/works/OL1W"]["subjects"] == ["Dogs"]
