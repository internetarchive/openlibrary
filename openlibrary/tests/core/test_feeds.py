from typing import Final

import pytest
import web

from openlibrary.catalog import opds2
from openlibrary.core import feeds
from openlibrary.core.db import get_db
from openlibrary.core.tbp import FeedRegistry

TBP_DDL: Final = """
CREATE TABLE tbp_feed_registry (
    id integer primary key,
    provider_name text not null,
    feed_type text not null,
    url text not null,
    last_updated timestamp default null,
    data text not null default '{}',
    created timestamp default current_timestamp,
    updated timestamp default current_timestamp,
    UNIQUE (provider_name, url)
);
"""

IMPORT_BATCH_DDL: Final = """
CREATE TABLE import_batch (
    id integer primary key,
    name text,
    submitter text,
    submit_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

IMPORT_ITEM_DDL: Final = """
CREATE TABLE import_item (
    id serial primary key,
    batch_id integer,
    status text default 'pending',
    error text,
    ia_id text,
    data text,
    ol_key text,
    comments text,
    submitter text,
    UNIQUE (batch_id, ia_id)
);
"""


def _publication(isbn_13: str, modified: str) -> dict:
    return {
        "metadata": {
            "title": f"Book {isbn_13}",
            "identifier": f"urn:isbn:{isbn_13}",
            "author": [{"name": "An Author"}],
            "modified": modified,
        },
        "links": [
            {
                "rel": "http://opds-spec.org/acquisition/buy",
                "href": f"https://provider.example/buy/{isbn_13}",
                "properties": {"price": {"currency": "USD", "value": 2.0}},
            }
        ],
    }


ONE_BOOK_FEED: Final = {"publications": [_publication("9781737408802", "2026-06-16T10:00:00+00:00")], "links": []}
EMPTY_FEED: Final[dict] = {"publications": [], "links": []}


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self, pages_by_url):
        self.pages_by_url = pages_by_url

    def get(self, url, **kwargs):
        return FakeResponse(self.pages_by_url[url])


@pytest.fixture
def feeds_db():
    web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
    db = get_db()
    for table in ("import_item", "import_batch", "tbp_feed_registry"):
        db.query(f"DROP TABLE IF EXISTS {table};")
    db.query(TBP_DDL)
    db.query(IMPORT_BATCH_DDL)
    db.query(IMPORT_ITEM_DDL)
    yield db
    for table in ("import_item", "import_batch", "tbp_feed_registry"):
        db.query(f"DROP TABLE IF EXISTS {table};")


def _serve(monkeypatch, pages):
    monkeypatch.setattr(opds2, "PAGE_SLEEP_SECONDS", 0)
    session = FakeSession(pages)
    monkeypatch.setattr(opds2.requests, "Session", lambda: session)


def test_harvest_feed_stages_records_and_advances_cursor(monkeypatch, feeds_db):
    FeedRegistry.register("prov", "https://prov.example/opds", data={"source_id_prefix": "prov"})
    feed = FeedRegistry.find("prov", "https://prov.example/opds")
    _serve(monkeypatch, {"https://prov.example/opds": ONE_BOOK_FEED})

    result = feeds.harvest_feed(feed)
    assert result == {"feed": "prov", "olbooks": 1, "advanced": True}

    rows = list(feeds_db.select("import_item"))
    assert [r.ia_id for r in rows] == ["prov:9781737408802"]

    reloaded = FeedRegistry.get_by_id(feed.id)
    assert reloaded.last_updated is not None  # cursor advanced
    assert reloaded.data["status"] == "idle"  # unlocked
    assert "locked_at" not in reloaded.data


def test_harvest_feed_skips_when_locked(monkeypatch, feeds_db):
    FeedRegistry.register("prov", "https://prov.example/opds")
    feed = FeedRegistry.find("prov", "https://prov.example/opds")
    assert FeedRegistry.try_lock(feed.id) is True  # someone else is harvesting
    _serve(monkeypatch, {"https://prov.example/opds": ONE_BOOK_FEED})

    assert feeds.harvest_feed(feed) == {"feed": "prov", "skipped": "locked"}
    assert list(feeds_db.select("import_item")) == []


def test_harvest_is_idempotent_via_cursor(monkeypatch, feeds_db):
    FeedRegistry.register("prov", "https://prov.example/opds")
    feed = FeedRegistry.find("prov", "https://prov.example/opds")
    _serve(monkeypatch, {"https://prov.example/opds": ONE_BOOK_FEED})

    feeds.harvest_feed(feed)
    # Second run: cursor now past the record -> nothing new, no duplicate rows.
    second = feeds.harvest_feed(FeedRegistry.get_by_id(feed.id))
    assert second["olbooks"] == 0
    assert second["advanced"] is False
    assert len(list(feeds_db.select("import_item"))) == 1


def test_harvest_all_runs_every_feed(monkeypatch, feeds_db):
    FeedRegistry.register("a", "https://a.example/opds")
    FeedRegistry.register("b", "https://b.example/opds")
    _serve(monkeypatch, {"https://a.example/opds": ONE_BOOK_FEED, "https://b.example/opds": EMPTY_FEED})

    results = feeds.harvest_all()
    assert {r["feed"] for r in results} == {"a", "b"}
    by_feed = {r["feed"]: r for r in results}
    assert by_feed["a"]["olbooks"] == 1
    assert by_feed["b"]["olbooks"] == 0
