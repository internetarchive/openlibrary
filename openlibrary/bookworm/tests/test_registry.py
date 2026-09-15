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


def test_to_feed_carries_the_ol_edition_flag(registry_db):
    """A feed whose local id IS an OL edition number has to say so.

    The parser needs it to decide whether a record can name its edition outright
    instead of being matched on title alone.
    """
    FeedRegistry.register("lenny", "https://lenny/opds", id_strategy="self_link", data={"local_id_is_ol_edition": True})
    feed = FeedRegistry.find("lenny", "https://lenny/opds")
    assert feed.local_id_is_ol_edition is True
    assert feed.to_feed().local_id_is_ol_edition is True


def test_the_ol_edition_flag_defaults_off(registry_db):
    FeedRegistry.register("project_gutenberg", "https://g/opds", id_strategy="gutenberg")
    feed = FeedRegistry.find("project_gutenberg", "https://g/opds")
    assert feed.local_id_is_ol_edition is False
    assert feed.to_feed().local_id_is_ol_edition is False


def test_advance_moves_cursor(registry_db):
    row = FeedRegistry.register("lenny", "https://lenny/opds", id_strategy="self_link")
    cursor = datetime.datetime(2026, 7, 20, 12, 0, 0)
    assert FeedRegistry.advance(row.id, last_updated=cursor) == 1
    assert str(FeedRegistry.get_by_id(row.id).last_updated).startswith("2026-07-20 12:00:00")


def test_all_lists_in_order(registry_db):
    FeedRegistry.register("a", "https://a/opds")
    FeedRegistry.register("b", "https://b/opds")
    assert [r.provider_name for r in FeedRegistry.all()] == ["a", "b"]


class TestStatusGating:
    """``status`` was written on registration but never read, so a registered
    feed was live on the next harvest and a registration could not be staged."""

    def test_a_new_feed_is_pending_not_active(self, registry_db):
        feed = FeedRegistry.register("lenny", "https://lenny/opds", id_strategy="self_link")
        assert feed.status == "pending"
        assert feed.is_active is False

    def test_activate_makes_it_harvestable(self, registry_db):
        feed = FeedRegistry.register("lenny", "https://lenny/opds", id_strategy="self_link")
        FeedRegistry.set_status(feed.id, "active")
        assert FeedRegistry.get_by_id(feed.id).is_active is True

    def test_activating_preserves_the_rest_of_the_config(self, registry_db):
        """The status lives in the same jsonb blob as the connector config, so a
        careless write would drop id_strategy/cursor_style."""
        feed = FeedRegistry.register("project_gutenberg", "https://g/opds", id_strategy="gutenberg", cursor_style=CURSOR_MODIFIED_SINCE)
        FeedRegistry.set_status(feed.id, "active")

        reloaded = FeedRegistry.get_by_id(feed.id)
        assert reloaded.id_strategy == "gutenberg"
        assert reloaded.supports_modified_since is True
        assert reloaded.is_active is True

    def test_activating_does_not_disturb_the_cursor(self, registry_db):
        feed = FeedRegistry.register("lenny", "https://lenny/opds", id_strategy="self_link")
        FeedRegistry.advance(feed.id, last_updated=datetime.datetime(2026, 9, 1))
        FeedRegistry.set_status(feed.id, "active")
        assert str(FeedRegistry.get_by_id(feed.id).last_updated).startswith("2026-09-01")

    def test_a_row_with_no_status_is_treated_as_active(self, registry_db):
        """Rows created before status existed must keep harvesting."""
        feed = FeedRegistry.register("lenny", "https://lenny/opds", id_strategy="self_link")
        FeedRegistry.advance(feed.id, last_updated=datetime.datetime(2026, 9, 1), data={"id_strategy": "self_link"})
        assert FeedRegistry.get_by_id(feed.id).is_active is True
