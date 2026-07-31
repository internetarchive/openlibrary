import pytest
from fastapi.testclient import TestClient

from openlibrary.bookworm.server import app


@pytest.fixture(autouse=True)
def _no_config_or_harvest(monkeypatch):
    # Don't load real config or hit the db in unit tests.
    monkeypatch.setattr("openlibrary.bookworm.server._load_config", lambda: None)
    monkeypatch.setattr("openlibrary.bookworm.harvest.harvest_all", lambda *a, **k: [])


def test_health():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok", "service": "bookworm"}


def test_manual_harvest_trigger_runs_harvest_all(monkeypatch):
    monkeypatch.setattr("openlibrary.bookworm.harvest.harvest_all", lambda *a, **k: [{"feed": "bwb", "records": 2}])
    with TestClient(app) as client:
        assert client.post("/harvest").json() == {"results": [{"feed": "bwb", "records": 2}]}
