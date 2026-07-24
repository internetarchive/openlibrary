import datetime
from typing import Final

import pytest
import web

from openlibrary.core.db import get_db
from openlibrary.core.tbp import FeedRegistry

# sqlite-friendly DDL (Postgres uses serial/jsonb; sqlite is typeless).
TBP_FEED_REGISTRY_DDL: Final = """
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

SEED: Final = [
    {
        "id": 1,
        "provider_name": "betterworldbooks",
        "feed_type": "opds",
        "url": "https://www.betterworldbooks.com/opds",
    },
    {
        "id": 2,
        "provider_name": "lenny",
        "feed_type": "opds",
        "url": "https://lennyforlibraries.org/v1/api/opds",
    },
]


@pytest.fixture(scope="module")
def setup_db():
    web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
    db = get_db()
    db.query(TBP_FEED_REGISTRY_DDL)
    yield db
    db.query("delete from tbp_feed_registry;")


@pytest.fixture
def registry_db(setup_db):
    setup_db.multiple_insert("tbp_feed_registry", SEED)
    yield setup_db
    setup_db.query("delete from tbp_feed_registry;")


class TestFeedRegistry:
    def test_find_hit(self, registry_db):
        row = FeedRegistry.find("betterworldbooks", "https://www.betterworldbooks.com/opds")
        assert row is not None
        assert row.id == 1
        assert row.feed_type == "opds"

    def test_find_miss(self, registry_db):
        assert FeedRegistry.find("nope", "https://example.invalid/opds") is None

    def test_get(self, registry_db):
        assert FeedRegistry.get_by_id(2).provider_name == "lenny"
        assert FeedRegistry.get_by_id(999) is None

    def test_all(self, registry_db):
        assert [r.provider_name for r in FeedRegistry.all()] == ["betterworldbooks", "lenny"]

    def test_new(self, registry_db):
        row = FeedRegistry.new("standard_ebooks", "https://standardebooks.org/opds", data={"k": "v"})
        assert row is not None
        assert row.feed_type == "opds"
        assert row.data == {"k": "v"}
        assert len(FeedRegistry.all()) == 3

    def test_register_is_idempotent(self, registry_db):
        first = FeedRegistry.register("betterworldbooks", "https://www.betterworldbooks.com/opds")
        assert first.id == 1
        # Second call must not create a duplicate row.
        second = FeedRegistry.register("betterworldbooks", "https://www.betterworldbooks.com/opds")
        assert second.id == 1
        assert len(FeedRegistry.all()) == 2

    def test_advance(self, registry_db):
        cursor = datetime.datetime(2026, 6, 3, 12, 0, 0)
        rows_changed = FeedRegistry.advance(1, last_updated=cursor, data={"cursor": "abc"})
        assert rows_changed == 1
        row = FeedRegistry.get_by_id(1)
        assert str(row.last_updated).startswith("2026-06-03 12:00:00")
        assert row.data == {"cursor": "abc"}
