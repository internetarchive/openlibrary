import datetime
from typing import Final

import pytest
import web

from openlibrary.bookworm.registry import CURSOR_MODIFIED_SINCE, FeedRegistry
from openlibrary.core.db import get_db

FEED_REGISTRY_DDL: Final = """
CREATE TABLE feed_registry (
    id integer primary key,
    provider_name text not null,
    feed_type text not null default 'opds',
    url text not null,
    last_updated timestamp default null,
    data text not null default '{}',
    created timestamp default current_timestamp,
    updated timestamp default current_timestamp,
    UNIQUE (provider_name, url)
);
"""


@pytest.fixture
def registry_db():
    web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
    db = get_db()
    db.query("DROP TABLE IF EXISTS feed_registry;")
    db.query(FEED_REGISTRY_DDL)
    yield db
    db.query("DROP TABLE IF EXISTS feed_registry;")


def test_register_is_idempotent_and_stores_connector_config(registry_db):
    first = FeedRegistry.register("project_gutenberg", "https://g/opds", id_strategy="gutenberg", cursor_style=CURSOR_MODIFIED_SINCE)
    assert first.data["id_strategy"] == "gutenberg"
    assert first.data["cursor_style"] == CURSOR_MODIFIED_SINCE
    assert first.data["status"] == "pending"
    # second call does not duplicate
    second = FeedRegistry.register("project_gutenberg", "https://g/opds")
    assert second.id == first.id
    assert len(FeedRegistry.all()) == 1


def test_to_feed_carries_id_strategy(registry_db):
    FeedRegistry.register("betterworldbooks", "https://bwb/opds", id_strategy="isbn")
    feed = FeedRegistry.find("betterworldbooks", "https://bwb/opds").to_feed()
    assert feed.provider_name == "betterworldbooks"
    assert feed.id_strategy == "isbn"


def test_advance_moves_cursor(registry_db):
    row = FeedRegistry.register("lenny", "https://lenny/opds", id_strategy="self_link")
    cursor = datetime.datetime(2026, 7, 20, 12, 0, 0)
    assert FeedRegistry.advance(row.id, last_updated=cursor) == 1
    assert str(FeedRegistry.get_by_id(row.id).last_updated).startswith("2026-07-20 12:00:00")


def test_all_lists_in_order(registry_db):
    FeedRegistry.register("a", "https://a/opds")
    FeedRegistry.register("b", "https://b/opds")
    assert [r.provider_name for r in FeedRegistry.all()] == ["a", "b"]
