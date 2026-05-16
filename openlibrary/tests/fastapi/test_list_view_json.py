import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openlibrary.fastapi.lists import router


@pytest.fixture
def client() -> TestClient:
    """Return a TestClient for the lists router."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


FAKE_LIST = {
    "links": {
        "self": "/people/testuser/lists/OL123L",
        "seeds": "/people/testuser/lists/OL123L/seeds",
        "subjects": "/people/testuser/lists/OL123L/subjects",
        "editions": "/people/testuser/lists/OL123L/editions",
    },
    "name": "My Test List",
    "type": {"key": "/people/testuser/lists/OL123L"},
    "description": "A test list",
    "seed_count": 3,
    "meta": {
        "revision": 1,
        "created": "2024-01-01T00:00:00",
        "last_modified": "2024-06-01T00:00:00",
    },
}


def test_list_view_json_user_returns_list(client, monkeypatch):
    """User-owned list should return formatted metadata."""
    monkeypatch.setattr(
        "openlibrary.fastapi.lists.get_list",
        lambda key, raw=False: FAKE_LIST,
    )
    resp = client.get("/people/testuser/lists/OL123L.json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "My Test List"
    assert data["seed_count"] == 3
    assert "self" in data["links"]


def test_list_view_json_user_not_found(client, monkeypatch):
    """Should return 404 when list does not exist."""
    monkeypatch.setattr(
        "openlibrary.fastapi.lists.get_list",
        lambda key, raw=False: None,
    )
    resp = client.get("/people/testuser/lists/OL999L.json")
    assert resp.status_code == 404


def test_list_view_json_deleted_list_returns_404(client, monkeypatch):
    """A deleted list (type = /type/delete) should return 404 regardless of ?_raw."""
    deleted = {"type": {"key": "/type/delete"}}
    monkeypatch.setattr(
        "openlibrary.fastapi.lists.get_list",
        lambda key, raw=False: deleted,
    )
    # Without ?_raw
    resp = client.get("/people/testuser/lists/OL123L.json")
    assert resp.status_code == 404

    # With ?_raw=true — must also be 404 (not the raw deleted record)
    resp_raw = client.get("/people/testuser/lists/OL123L.json?_raw=true")
    assert resp_raw.status_code == 404


def test_list_view_json_public_list(client, monkeypatch):
    """Public list (no /people/ prefix) should also work."""
    fake = {**FAKE_LIST, "links": {"self": "/lists/OL456L"}, "type": {"key": "/lists/OL456L"}}
    monkeypatch.setattr(
        "openlibrary.fastapi.lists.get_list",
        lambda key, raw=False: fake,
    )
    resp = client.get("/lists/OL456L.json")
    assert resp.status_code == 200


def test_list_view_json_series(client, monkeypatch):
    """Series list should work via /series/{id}.json."""
    fake = {**FAKE_LIST, "links": {"self": "/series/OL789L"}, "type": {"key": "/series/OL789L"}}
    monkeypatch.setattr(
        "openlibrary.fastapi.lists.get_list",
        lambda key, raw=False: fake,
    )
    resp = client.get("/series/OL789L.json")
    assert resp.status_code == 200


def test_list_view_json_raw_param(client, monkeypatch):
    """?_raw=true should be passed through to get_list, along with the correct key."""
    captured = {}

    def fake_get_list(key, raw=False):
        captured["key"] = key
        captured["raw"] = raw
        return FAKE_LIST

    monkeypatch.setattr("openlibrary.fastapi.lists.get_list", fake_get_list)
    resp = client.get("/people/testuser/lists/OL123L.json?_raw=true")
    assert resp.status_code == 200
    assert captured["raw"] is True
    assert captured["key"] == "/people/testuser/lists/OL123L"


FAKE_SUBJECTS = {
    "subjects": [{"name": "Science", "count": 10, "url": "/subjects/science"}],
    "places": [],
    "people": [],
    "times": [],
    "links": {
        "self": "/people/testuser/lists/OL123L/subjects",
        "list": "/people/testuser/lists/OL123L",
    },
}


def test_list_subjects_json_user_returns_subjects(client, monkeypatch):
    monkeypatch.setattr(
        "openlibrary.fastapi.lists.get_list_subjects",
        lambda key, limit=20: FAKE_SUBJECTS,
    )
    resp = client.get("/people/testuser/lists/OL123L/subjects.json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["subjects"][0]["name"] == "Science"
    assert data["subjects"][0]["count"] == 10
    assert data["subjects"][0]["url"] == "/subjects/science"
    assert "self" in data["links"]
    assert "list" in data["links"]


def test_list_subjects_json_user_not_found(client, monkeypatch):
    monkeypatch.setattr(
        "openlibrary.fastapi.lists.get_list_subjects",
        lambda key, limit=20: None,
    )
    resp = client.get("/people/testuser/lists/OL999L/subjects.json")
    assert resp.status_code == 404


def test_list_subjects_json_public_list(client, monkeypatch):
    subjects = {**FAKE_SUBJECTS, "links": {"self": "/lists/OL456L/subjects", "list": "/lists/OL456L"}}
    monkeypatch.setattr(
        "openlibrary.fastapi.lists.get_list_subjects",
        lambda key, limit=20: subjects,
    )
    resp = client.get("/lists/OL456L/subjects.json")
    assert resp.status_code == 200
    assert resp.json()["links"]["self"] == "/lists/OL456L/subjects"


def test_list_subjects_json_series(client, monkeypatch):
    subjects = {**FAKE_SUBJECTS, "links": {"self": "/series/OL789L/subjects", "list": "/series/OL789L"}}
    monkeypatch.setattr(
        "openlibrary.fastapi.lists.get_list_subjects",
        lambda key, limit=20: subjects,
    )
    resp = client.get("/series/OL789L/subjects.json")
    assert resp.status_code == 200


def test_list_subjects_json_user_series(client, monkeypatch):
    subjects = {**FAKE_SUBJECTS, "links": {"self": "/people/testuser/series/OL123L/subjects", "list": "/people/testuser/series/OL123L"}}
    monkeypatch.setattr(
        "openlibrary.fastapi.lists.get_list_subjects",
        lambda key, limit=20: subjects,
    )
    resp = client.get("/people/testuser/series/OL123L/subjects.json")
    assert resp.status_code == 200


FAKE_EDITIONS = {
    "size": 1,
    "start": 0,
    "end": 1,
    "entries": [{"key": "/books/OL1M", "title": "Test Book"}],
    "links": {
        "self": "/people/testuser/lists/OL123L/editions",
        "next": None,
        "prev": None,
        "list": "/people/testuser/lists/OL123L",
    },
}


def test_list_editions_json_returns_editions(client, monkeypatch):
    monkeypatch.setattr(
        "openlibrary.fastapi.lists.get_list_editions",
        lambda key, url, offset=0, limit=50: FAKE_EDITIONS,
    )
    resp = client.get("/people/testuser/lists/OL123L/editions.json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["size"] == 1
    assert data["entries"][0]["key"] == "/books/OL1M"
    assert "links" in data


def test_list_editions_json_not_found(client, monkeypatch):
    monkeypatch.setattr(
        "openlibrary.fastapi.lists.get_list_editions",
        lambda key, url, offset=0, limit=50: None,
    )
    resp = client.get("/people/testuser/lists/OL999L/editions.json")
    assert resp.status_code == 404


def test_list_editions_json_public_list(client, monkeypatch):
    editions = {**FAKE_EDITIONS, "links": {**FAKE_EDITIONS["links"], "self": "/lists/OL456L/editions", "list": "/lists/OL456L"}}
    monkeypatch.setattr(
        "openlibrary.fastapi.lists.get_list_editions",
        lambda key, url, offset=0, limit=50: editions,
    )
    resp = client.get("/lists/OL456L/editions.json")
    assert resp.status_code == 200


def test_list_editions_json_series(client, monkeypatch):
    editions = {**FAKE_EDITIONS, "links": {**FAKE_EDITIONS["links"], "self": "/series/OL789L/editions", "list": "/series/OL789L"}}
    monkeypatch.setattr(
        "openlibrary.fastapi.lists.get_list_editions",
        lambda key, url, offset=0, limit=50: editions,
    )
    resp = client.get("/series/OL789L/editions.json")
    assert resp.status_code == 200


def test_list_editions_json_user_series(client, monkeypatch):
    editions = {**FAKE_EDITIONS, "links": {**FAKE_EDITIONS["links"], "self": "/people/testuser/series/OL123L/editions", "list": "/people/testuser/series/OL123L"}}
    monkeypatch.setattr(
        "openlibrary.fastapi.lists.get_list_editions",
        lambda key, url, offset=0, limit=50: editions,
    )
    resp = client.get("/people/testuser/series/OL123L/editions.json")
    assert resp.status_code == 200
