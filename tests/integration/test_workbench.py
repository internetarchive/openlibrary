# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "pytest",
#     "requests",
# ]
# ///

"""Integration test for the librarian workbench's write path against a running
dev stack: preview → apply → read the batch back → revert → the record is as it
was. This is the one path the unit tests cannot cover, because it depends on
infobase indexing the changeset data the batch is found by.

Needs the dev server on localhost:8080 and the seeded admin account.

Run explicitly with:
    uv run --with pytest --with pytest-asyncio --with requests pytest -m integration -o addopts="" tests/integration/test_workbench.py -v
"""

import pytest
import requests

BASE_URL = "http://localhost:8080"
USERNAME = "openlibrary"
PASSWORD = "openlibrary"


@pytest.fixture
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/account/login.json", json={"username": USERNAME, "password": PASSWORD})
    assert r.status_code == 200, r.text
    config = s.get(f"{BASE_URL}/librarians/workbench/config.json")
    assert config.status_code == 200, config.text
    assert config.json()["is_super"], "the test applies directly, so it needs a super-librarian"
    yield s
    s.close()


def _work(session):
    r = session.post(f"{BASE_URL}/librarians/workbench/query.json", json={"type": "work", "q": "", "rows": 1, "sort": "editions_desc"})
    assert r.status_code == 200, r.text
    records = r.json()["records"]
    assert records, "the dev index has no works"
    return records[0]["key"]


@pytest.mark.integration
def test_apply_then_revert_round_trip(session):
    key = _work(session)
    before = session.get(f"{BASE_URL}{key}.json").json()
    value = ["eng"] if not before.get("original_languages") else []
    if not value:
        pytest.skip(f"{key} already has original_languages; pick a cleaner record")
    body = {"action": "set_field", "items": [{"key": key}], "params": {"field": "original_languages", "value": value, "mode": "set"}}

    preview = session.post(f"{BASE_URL}/librarians/batch.json", json={**body, "dry_run": True}).json()
    assert preview["mode"] == "apply"
    assert preview["can_apply"] is True
    assert preview["changes"] == [{"key": key, "field": "original_languages", "from": None, "to": [{"key": "/languages/eng"}]}]
    assert preview["revisions"] == {key: before["revision"]}

    applied = session.post(
        f"{BASE_URL}/librarians/batch.json",
        json={**body, "items": [{"key": key, "expected_revision": before["revision"]}], "dry_run": False, "comment": "workbench integration test"},
    ).json()
    assert applied["status"] == "applied", applied
    assert applied["batch_id"], "the changeset must be found by its uid"
    assert applied["revisions"] == {key: before["revision"] + 1}
    assert session.get(f"{BASE_URL}{key}.json").json()["original_languages"] == [{"key": "/languages/eng"}]

    batch = session.get(f"{BASE_URL}/librarians/batch/{applied['batch_id']}.json").json()
    assert batch["status"] == "applied"
    assert batch["items"] == [
        {"key": key, "title": batch["items"][0]["title"], "before_revision": before["revision"], "after_revision": before["revision"] + 1, "reverted": False}
    ]
    assert applied["batch_id"] in {b["id"] for b in session.get(f"{BASE_URL}/librarians/batches.json?limit=10").json()["batches"] if b["kind"] == "batch"}
    assert session.get(f"{BASE_URL}/librarians/batch/{applied['batch_id']}").status_code == 200

    reverted = session.post(f"{BASE_URL}/librarians/batch/{applied['batch_id']}/revert.json", json={}).json()
    assert reverted == {"status": "reverted", "batch_id": applied["batch_id"], "reverted": 1}
    after = session.get(f"{BASE_URL}{key}.json").json()
    assert after.get("original_languages") == before.get("original_languages")
    assert after["revision"] == before["revision"] + 2
    assert session.get(f"{BASE_URL}/librarians/batch/{applied['batch_id']}.json").json()["status"] == "reverted"


@pytest.mark.integration
def test_flag_round_trip(session):
    key = _work(session)
    filed = session.post(
        f"{BASE_URL}/librarians/batch.json", json={"action": "flag", "items": [{"key": key}], "params": {"reason": "review"}, "dry_run": False}
    ).json()
    assert filed["status"] == "requested", filed
    rid = filed["request_id"]
    pending = [c for c in session.get(f"{BASE_URL}/librarians/context.json?key={key}").json()["chips"] if c["code"] == "pending"]
    assert pending, "an open request shows on its record"
    assert any(p["id"] == rid for p in pending[0]["detail"])
    assert session.get(f"{BASE_URL}/librarians/request/{rid}/preview.json").status_code == 400, "a flag has no plan"
    assert session.post(f"{BASE_URL}/librarians/request/{rid}/apply.json", json={}).status_code == 400
    assert session.post(f"{BASE_URL}/librarians/request/{rid}/resolve.json", json={"comment": "integration test"}).json()["status"] == "resolved"
    assert session.get(f"{BASE_URL}/librarians/request/{rid}.json").json()["status"] == "resolved"
    assert not [c for c in session.get(f"{BASE_URL}/librarians/context.json?key={key}").json()["chips"] if c["code"] == "pending"]


@pytest.mark.integration
def test_bad_input_is_a_readable_400(session):
    key = _work(session)
    r = session.post(
        f"{BASE_URL}/librarians/batch.json", json={"action": "set_field", "items": [{"key": key}], "params": {"field": "original_languages", "value": ["zzq"]}}
    )
    assert r.status_code == 400
    assert "zzq" in r.json()["detail"]["error"]
