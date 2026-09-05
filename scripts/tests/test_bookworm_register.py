"""Tests for the BookWorm feed-registration script (#12844)."""

from __future__ import annotations

import datetime
from typing import Final

import pytest
import web

from openlibrary.bookworm.registry import FeedRegistry
from openlibrary.core.db import get_db
from scripts import bookworm_register

FEED_REGISTRY_DDL: Final = """
CREATE TABLE feed_registry (
    id integer primary key, provider_name text not null, feed_type text not null default 'opds',
    url text not null, last_updated timestamp default null, data text not null default '{}',
    created timestamp default current_timestamp, updated timestamp default current_timestamp,
    UNIQUE (provider_name, url)
);
"""


@pytest.fixture
def registry_db(monkeypatch):
    web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
    db = get_db()
    db.query("DROP TABLE IF EXISTS feed_registry;")
    db.query(FEED_REGISTRY_DDL)
    monkeypatch.setattr(bookworm_register, "load_config", lambda path: None)
    yield db
    db.query("DROP TABLE IF EXISTS feed_registry;")


def registered() -> dict[str, FeedRegistry]:
    return {feed.provider_name: feed for feed in FeedRegistry.all()}


class TestDefaults:
    def test_registers_the_default_feeds(self, registry_db):
        bookworm_register.main(ol_config="x.yml")
        assert set(registered()) == set(bookworm_register.DEFAULT_PROVIDERS)

    def test_bwb_is_not_registered_by_default(self, registry_db):
        """BWB is blocked by Cloudflare; registering it would fail every pass."""
        bookworm_register.main(ol_config="x.yml")
        assert "betterworldbooks" not in registered()

    def test_bwb_can_be_registered_explicitly(self, registry_db):
        bookworm_register.main(ol_config="x.yml", provider="betterworldbooks")
        assert "betterworldbooks" in registered()

    def test_lenny_uses_the_server_side_cursor(self, registry_db):
        """Verified against the live feed: lenny honours ?modified_since.

        Registering it as ``client`` would re-crawl all 96 items every run.
        """
        bookworm_register.main(ol_config="x.yml", provider="lenny")
        assert registered()["lenny"].supports_modified_since is True


class TestIdempotence:
    def test_re_running_does_not_duplicate(self, registry_db):
        bookworm_register.main(ol_config="x.yml")
        bookworm_register.main(ol_config="x.yml")
        assert len(FeedRegistry.all()) == len(bookworm_register.DEFAULT_PROVIDERS)

    def test_re_running_never_rewinds_a_live_cursor(self, registry_db):
        """The dangerous case: re-applying registration must not replay history."""
        bookworm_register.main(ol_config="x.yml", provider="lenny")
        feed = registered()["lenny"]
        FeedRegistry.advance(feed.id, last_updated=datetime.datetime(2026, 9, 1))

        bookworm_register.main(ol_config="x.yml", provider="lenny", since="2020-01-01")

        assert str(registered()["lenny"].last_updated).startswith("2026-09-01")


class TestCursorSeeding:
    def test_since_seeds_the_cursor_on_first_registration(self, registry_db):
        bookworm_register.main(ol_config="x.yml", provider="project_gutenberg", since="2026-08-28")
        assert str(registered()["project_gutenberg"].last_updated).startswith("2026-08-28")

    def test_no_since_leaves_the_cursor_null(self, registry_db):
        """A null cursor means the first run backfills from the beginning."""
        bookworm_register.main(ol_config="x.yml", provider="lenny")
        assert registered()["lenny"].last_updated is None

    def test_bad_since_is_rejected(self, registry_db):
        with pytest.raises(SystemExit):
            bookworm_register.main(ol_config="x.yml", provider="lenny", since="28/08/2026")


class TestSafety:
    def test_unknown_provider_exits_nonzero(self, registry_db):
        with pytest.raises(SystemExit):
            bookworm_register.main(ol_config="x.yml", provider="nope")

    def test_dry_run_writes_nothing(self, registry_db):
        bookworm_register.main(ol_config="x.yml", dry_run=True)
        assert FeedRegistry.all() == []

    def test_show_writes_nothing(self, registry_db, capsys):
        bookworm_register.main(ol_config="x.yml", show=True)
        assert FeedRegistry.all() == []
        assert "empty" in capsys.readouterr().out
