from typing import Final

import pytest
import web

from openlibrary.catalog import opds2
from openlibrary.core import bookworm
from openlibrary.core.db import get_db
from openlibrary.core.staged import STAGED, StagedRecord
from openlibrary.core.tbp import FeedRegistry

TBP_DDL: Final = """
CREATE TABLE tbp_feed_registry (
    id integer primary key, provider_name text not null, feed_type text not null,
    url text not null, last_updated timestamp default null, data text not null default '{}',
    created timestamp default current_timestamp, updated timestamp default current_timestamp,
    UNIQUE (provider_name, url)
);
"""
STAGED_DDL: Final = """
CREATE TABLE tbp_staged_record (
    id integer primary key, provider_name text not null, local_id text not null,
    record text not null, acquisition text default null, status text not null default 'staged',
    created timestamp default current_timestamp, updated timestamp default current_timestamp,
    UNIQUE (provider_name, local_id)
);
"""
IMPORT_BATCH_DDL: Final = """
CREATE TABLE import_batch (id integer primary key, name text, submitter text, submit_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
"""
IMPORT_ITEM_DDL: Final = """
CREATE TABLE import_item (
    id serial primary key, batch_id integer, status text default 'pending', error text,
    ia_id text, data text, ol_key text, comments text, submitter text, UNIQUE (batch_id, ia_id)
);
"""

FEED_URL: Final = "https://prov.example/opds"
ONE_BOOK_FEED: Final = {
    "publications": [
        {
            "metadata": {
                "title": "A Book",
                "identifier": "urn:isbn:9781737408802",
                "author": [{"name": "An Author"}],
                "modified": "2026-06-16T10:00:00+00:00",
            },
            "links": [
                {
                    "rel": "http://opds-spec.org/acquisition/buy",
                    "href": "https://prov.example/buy/9781737408802",
                    "properties": {"price": {"currency": "USD", "value": 2.0}},
                }
            ],
        }
    ],
    "links": [],
}


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

    def get(self, url, **kwargs):
        return FakeResponse(self.pages[url])


@pytest.fixture
def bookworm_db():
    web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
    db = get_db()
    for table in ("import_item", "import_batch", "tbp_staged_record", "tbp_feed_registry"):
        db.query(f"DROP TABLE IF EXISTS {table};")
    for ddl in (TBP_DDL, STAGED_DDL, IMPORT_BATCH_DDL, IMPORT_ITEM_DDL):
        db.query(ddl)
    yield db
    for table in ("import_item", "import_batch", "tbp_staged_record", "tbp_feed_registry"):
        db.query(f"DROP TABLE IF EXISTS {table};")


def _serve(monkeypatch, pages):
    monkeypatch.setattr(opds2, "PAGE_SLEEP_SECONDS", 0)
    monkeypatch.setattr(opds2.requests, "Session", lambda: FakeSession(pages))


def test_stage_feed_buffers_records_with_acquisition(monkeypatch, bookworm_db):
    FeedRegistry.register("prov", FEED_URL, data={"source_id_prefix": "prov"})
    feed = FeedRegistry.find("prov", FEED_URL)
    _serve(monkeypatch, {FEED_URL: ONE_BOOK_FEED})

    result = bookworm.stage_feed(feed)
    assert result == {"feed": "prov", "staged": 1, "advanced": True}

    staged = StagedRecord.pending()
    assert len(staged) == 1
    assert staged[0].record["source_records"] == ["prov:9781737408802"]
    assert staged[0].acquisition["price"] == {"currency": "USD", "value": 2.0}
    # no import_item yet — staging only
    assert list(bookworm_db.select("import_item")) == []
    # cursor advanced + unlocked
    reloaded = FeedRegistry.get_by_id(feed.id)
    assert reloaded.last_updated is not None
    assert reloaded.data["status"] == "idle"


def test_promote_pending_creates_import_items_and_is_idempotent(monkeypatch, bookworm_db):
    FeedRegistry.register("prov", FEED_URL)
    feed = FeedRegistry.find("prov", FEED_URL)
    _serve(monkeypatch, {FEED_URL: ONE_BOOK_FEED})
    bookworm.stage_feed(feed)

    assert bookworm.promote_pending() == 1
    rows = list(bookworm_db.select("import_item"))
    assert [r.ia_id for r in rows] == ["prov:9781737408802"]
    # staged row is now marked promoted -> drops out of the queue
    assert StagedRecord.pending() == []
    # promoting again does nothing (queue empty)
    assert bookworm.promote_pending() == 0
    assert len(list(bookworm_db.select("import_item"))) == 1


def test_run_once_stages_then_promotes(monkeypatch, bookworm_db):
    FeedRegistry.register("prov", FEED_URL)
    _serve(monkeypatch, {FEED_URL: ONE_BOOK_FEED})

    summary = bookworm.run_once()
    assert summary["promoted"] == 1
    assert summary["staged"] == [{"feed": "prov", "staged": 1, "advanced": True}]
    assert [r.ia_id for r in bookworm_db.select("import_item")] == ["prov:9781737408802"]


def test_stage_feed_is_idempotent_via_cursor(monkeypatch, bookworm_db):
    FeedRegistry.register("prov", FEED_URL)
    feed = FeedRegistry.find("prov", FEED_URL)
    _serve(monkeypatch, {FEED_URL: ONE_BOOK_FEED})
    bookworm.stage_feed(feed)
    # Second stage: cursor past the record -> nothing new staged.
    second = bookworm.stage_feed(FeedRegistry.get_by_id(feed.id))
    assert second["staged"] == 0
    assert len([r for r in StagedRecord.pending() if r.status == STAGED]) == 1
