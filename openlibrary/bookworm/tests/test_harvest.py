import datetime
import json
from pathlib import Path
from typing import Final

import pytest
import web

from openlibrary.bookworm import harvest, opds
from openlibrary.bookworm.harvest import _as_utc
from openlibrary.bookworm.registry import CURSOR_MODIFIED_SINCE, FeedRegistry
from openlibrary.core.db import get_db

SAMPLES = Path(__file__).parent / "samples"
NOW: Final = datetime.datetime(2026, 7, 30, tzinfo=datetime.UTC)

FEED_REGISTRY_DDL: Final = """
CREATE TABLE feed_registry (
    id integer primary key, provider_name text not null, feed_type text not null default 'opds',
    url text not null, last_updated timestamp default null, data text not null default '{}',
    created timestamp default current_timestamp, updated timestamp default current_timestamp,
    UNIQUE (provider_name, url)
);
"""
IMPORT_BATCH_DDL: Final = "CREATE TABLE import_batch (id integer primary key, name text, submitter text, submit_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"
IMPORT_ITEM_DDL: Final = """
CREATE TABLE import_item (
    id serial primary key, batch_id integer, status text default 'pending', error text,
    ia_id text, data text, ol_key text, comments text, submitter text, UNIQUE (batch_id, ia_id)
);
"""


def feed_page(name: str) -> dict:
    return {"publications": json.loads((SAMPLES / f"{name}.json").read_text()), "links": []}


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self, pages):
        self.pages = pages
        self.calls: list[str] = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        return FakeResponse(self.pages[url])


@pytest.fixture
def bookworm_db():
    web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
    db = get_db()
    for table in ("import_item", "import_batch", "feed_registry"):
        db.query(f"DROP TABLE IF EXISTS {table};")
    for ddl in (FEED_REGISTRY_DDL, IMPORT_BATCH_DDL, IMPORT_ITEM_DDL):
        db.query(ddl)
    yield db
    for table in ("import_item", "import_batch", "feed_registry"):
        db.query(f"DROP TABLE IF EXISTS {table};")


def test_harvest_bwb_submits_import_items_carrying_acquisitions(bookworm_db):
    FeedRegistry.register("betterworldbooks", "https://bwb/opds", id_strategy="isbn")
    feed = FeedRegistry.find("betterworldbooks", "https://bwb/opds")
    session = FakeSession({"https://bwb/opds": feed_page("bwb")})

    result = harvest.harvest_feed(feed, session=session, now=NOW)
    assert result["records"] == 2

    rows = list(bookworm_db.select("import_item"))
    assert {r.ia_id for r in rows} == {"betterworldbooks:9781737408802", "betterworldbooks:9798995425007"}
    data = json.loads(rows[0].data)
    assert data["acquisitions"][0]["provider_name"] == "betterworldbooks"
    assert data["acquisitions"][0]["data"]["access"] == "buy"
    # cursor advanced to the newest publication modified time in the feed (UTC)
    expected = max(_as_utc(opds.Publication(**p).modified) for p in json.loads((SAMPLES / "bwb.json").read_text()))
    assert _as_utc(FeedRegistry.get_by_id(feed.id).last_updated) == expected


def test_harvest_gutenberg_injects_modified_since_and_open_access(bookworm_db):
    FeedRegistry.register("project_gutenberg", "https://g/opds/search?sort=fil", id_strategy="gutenberg", cursor_style=CURSOR_MODIFIED_SINCE)
    feed = FeedRegistry.find("project_gutenberg", "https://g/opds/search?sort=fil")
    FeedRegistry.advance(feed.id, last_updated=datetime.datetime(2026, 7, 20))
    feed = FeedRegistry.get_by_id(feed.id)

    fetch_url = feed.request_url(datetime.datetime(2026, 7, 20, tzinfo=datetime.UTC))
    assert "modified_since=2026-07-20" in fetch_url
    session = FakeSession({fetch_url: feed_page("gutenberg")})

    result = harvest.harvest_feed(feed, session=session, now=NOW)
    assert result["records"] == 3
    assert any("modified_since=2026-07-20" in call for call in session.calls)
    data = json.loads(next(iter(bookworm_db.select("import_item"))).data)
    assert data["acquisitions"][0]["data"]["access"] == "open-access"
    # modified_since feeds advance the cursor to run time
    assert str(FeedRegistry.get_by_id(feed.id).last_updated).startswith("2026-07-30")


def test_harvest_all_covers_every_feed(bookworm_db):
    FeedRegistry.register("betterworldbooks", "https://bwb/opds", id_strategy="isbn")
    FeedRegistry.register("lenny", "https://lenny/opds", id_strategy="self_link")
    session = FakeSession({"https://bwb/opds": feed_page("bwb"), "https://lenny/opds": feed_page("lenny")})

    results = harvest.harvest_all(session=session)
    assert {r["feed"] for r in results} == {"betterworldbooks", "lenny"}
    assert {r["feed"]: r["records"] for r in results} == {"betterworldbooks": 2, "lenny": 3}


def test_one_malformed_publication_is_skipped_not_fatal(bookworm_db):
    """A single poison publication must not abort the feed (which would wedge the cursor)."""
    FeedRegistry.register("lenny", "https://lenny/opds", id_strategy="self_link")
    feed = FeedRegistry.find("lenny", "https://lenny/opds")
    good = json.loads((SAMPLES / "lenny.json").read_text())
    poison = {"metadata": {"title": "Poison"}, "links": [{"rel": "self"}]}  # link missing href -> ValidationError
    page = {"publications": [poison, *good], "links": []}
    session = FakeSession({"https://lenny/opds": page})

    result = harvest.harvest_feed(feed, session=session, now=NOW)
    assert result["records"] == len(good)  # the good ones still made it; poison skipped
    assert FeedRegistry.get_by_id(feed.id).last_updated is not None  # cursor advanced


def test_harvest_all_continues_when_one_feed_errors(bookworm_db):
    FeedRegistry.register("betterworldbooks", "https://bwb/opds", id_strategy="isbn")
    FeedRegistry.register("lenny", "https://lenny/opds", id_strategy="self_link")
    # lenny's URL is absent from the session -> FakeSession.get raises KeyError mid-harvest.
    session = FakeSession({"https://bwb/opds": feed_page("bwb")})

    results = harvest.harvest_all(session=session)
    by_feed = {r["feed"]: r for r in results}
    assert by_feed["betterworldbooks"]["records"] == 2  # healthy feed unaffected
    assert by_feed["lenny"]["records"] == 0
    assert by_feed["lenny"].get("error") is True
