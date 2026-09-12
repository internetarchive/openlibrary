"""Tests for the /librarians workbench and batch routes: the librarian gate,
the action gate, request validation, and that route bodies reach the core
modules in the expected shape."""

from unittest.mock import MagicMock

import pytest

from openlibrary.core import batch_ops, workbench
from openlibrary.fastapi import librarians
from openlibrary.fastapi.auth import AuthenticatedUser, require_librarian
from openlibrary.utils.request_context import RequestContextVars, req_context, site


@pytest.fixture(autouse=True)
def _request_context():
    site.set(MagicMock())
    req_context.set(RequestContextVars(x_forwarded_for=None, user_agent=None, lang="en", solr_editions=True, print_disabled=False))


@pytest.fixture
def librarian(fastapi_client, monkeypatch):
    """Sign in a (super-)librarian through the dependency override, and a matching site user."""
    auth = AuthenticatedUser(username="libby", user_key="/people/libby", timestamp="2026-01-01T00:00:00")
    fastapi_client.app.dependency_overrides[require_librarian] = lambda: auth
    user = MagicMock()
    user.key = "/people/libby"
    user.is_super_librarian_or_higher.return_value = True
    monkeypatch.setattr(librarians, "get_current_user", lambda: user)
    yield user
    fastapi_client.app.dependency_overrides.clear()


def test_routes_refuse_anonymous(fastapi_client):
    for method, path in [
        ("get", "/librarians/workbench/config.json"),
        ("post", "/librarians/workbench/query.json"),
        ("get", "/librarians/workbench/worklists.json"),
        ("post", "/librarians/batch.json"),
        ("get", "/librarians/batches.json"),
    ]:
        r = fastapi_client.post(path, json={}) if method == "post" else fastapi_client.get(path)
        assert r.status_code in (401, 403), path


def test_config_lists_filters_actions_and_role(fastapi_client, librarian):
    r = fastapi_client.get("/librarians/workbench/config.json")
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "libby"
    assert body["is_super"] is True
    assert {f["id"] for f in body["filters"]} >= {"no_cover", "author_mismatch", "language"}
    assert {a["name"] for a in body["actions"]} == set(batch_ops.ENABLED_ACTIONS)
    assert "publishers" in body["settable_fields"]["edition"]


def test_query_passes_typed_body_to_core(fastapi_client, librarian, monkeypatch):
    seen = {}

    def fake(rtype, q, filters, sort, page, rows):
        seen.update(rtype=rtype, q=q, filters=filters, sort=sort, page=page, rows=rows)
        return {"records": [], "num_found": 0}

    monkeypatch.setattr(workbench, "run_query", fake)
    r = fastapi_client.post(
        "/librarians/workbench/query.json",
        json={
            "type": "work",
            "q": "author_key:OL1A",
            "filters": [{"id": "no_cover"}, {"id": "year", "value": {"from": 1990}}],
            "sort": "modified",
            "page": 2,
            "rows": 20,
        },
    )
    assert r.status_code == 200
    assert seen == {
        "rtype": "work",
        "q": "author_key:OL1A",
        "filters": [{"id": "no_cover", "value": None}, {"id": "year", "value": {"from": 1990}}],
        "sort": "modified",
        "page": 2,
        "rows": 20,
    }


def test_query_rejects_out_of_range_rows(fastapi_client, librarian):
    r = fastapi_client.post("/librarians/workbench/query.json", json={"rows": 10_000})
    assert r.status_code == 422


def test_query_errors_surface_as_json(fastapi_client, librarian, monkeypatch):
    monkeypatch.setattr(workbench, "run_query", MagicMock(side_effect=workbench.WorkbenchError("Solr rejected the query", 400)))
    r = fastapi_client.post("/librarians/workbench/query.json", json={"q": "bad:["})
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "Solr rejected the query"


def test_batch_refuses_unknown_action(fastapi_client, librarian):
    r = fastapi_client.post("/librarians/batch.json", json={"action": "format_hard_drive", "items": [{"key": "OL1W"}]})
    assert r.status_code == 400
    assert "not enabled" in r.json()["detail"]["error"]


def test_batch_forwards_items_params_and_flags(fastapi_client, librarian, monkeypatch):
    seen = {}

    def fake(user, action, items, params, dry_run, overrides, comment):
        seen.update(action=action, items=items, params=params, dry_run=dry_run, overrides=overrides, comment=comment)
        return {"mode": "apply"}

    monkeypatch.setattr(batch_ops, "run", fake)
    r = fastapi_client.post(
        "/librarians/batch.json",
        json={
            "action": "tag",
            "items": [{"key": "OL1W", "expected_revision": 3}],
            "params": {"add": {"subjects": ["Dogs"]}},
            "dry_run": False,
            "overrides": ["x"],
            "comment": "why",
        },
    )
    assert r.status_code == 200
    assert seen["action"] == "tag"
    assert seen["items"] == [{"key": "OL1W", "expected_revision": 3}]
    assert seen["params"] == {"add": {"subjects": ["Dogs"]}}
    assert (seen["dry_run"], seen["overrides"], seen["comment"]) == (False, ["x"], "why")


def test_batch_errors_keep_status_and_extra(fastapi_client, librarian, monkeypatch):
    monkeypatch.setattr(batch_ops, "run", MagicMock(side_effect=batch_ops.BatchError("stale", 409, stale={"/works/OL1W": 4})))
    r = fastapi_client.post("/librarians/batch.json", json={"action": "tag", "items": [{"key": "OL1W"}], "dry_run": False})
    assert r.status_code == 409
    assert r.json()["detail"] == {"error": "stale", "stale": {"/works/OL1W": 4}}


def test_batches_listing_is_scoped_to_self_for_librarians(fastapi_client, librarian, monkeypatch):
    librarian.is_super_librarian_or_higher.return_value = False
    seen = {}
    monkeypatch.setattr(librarians.LibrarianBatches, "list_batches", lambda **kw: seen.update(kw) or [])
    r = fastapi_client.get("/librarians/batches.json?mine=false")
    assert r.status_code == 200
    assert seen["username"] == "libby"


def test_revert_forwards_key_and_force(fastapi_client, librarian, monkeypatch):
    seen = {}
    monkeypatch.setattr(batch_ops, "revert", lambda user, bid, key=None, force=False: seen.update(bid=bid, key=key, force=force) or {"status": "reverted"})
    r = fastapi_client.post("/librarians/batch/7/revert.json", json={"key": "/works/OL1W", "force": True})
    assert r.status_code == 200
    assert seen == {"bid": 7, "key": "/works/OL1W", "force": True}


def test_worklist_create_and_delete(fastapi_client, librarian, monkeypatch):
    monkeypatch.setattr(
        workbench, "save_worklist", lambda owner, body, wid=None, is_super=False: {"id": "abc", "owner": owner, "name": body["name"], "is_super": is_super}
    )
    r = fastapi_client.post("/librarians/workbench/worklists.json", json={"name": "Mine", "type": "edition", "filters": [{"id": "no_cover"}]})
    assert r.status_code == 200
    assert r.json()["owner"] == "libby"
    monkeypatch.setattr(workbench, "delete_worklist", MagicMock(side_effect=workbench.WorkbenchError("Only the owner", 403)))
    r = fastapi_client.delete("/librarians/workbench/worklists/abc.json")
    assert r.status_code == 403


def test_record_rejects_non_keys(fastapi_client, librarian):
    r = fastapi_client.get("/librarians/workbench/record.json?key=nonsense")
    assert r.status_code == 400
