"""Tests for the BookWorm feed-registration script (#12844)."""

from __future__ import annotations

import datetime
import logging
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


class TestReseed:
    def test_reseed_moves_an_existing_cursor(self, registry_db):
        """The recovery path for 'registered it, then realised the backfill is
        too large' -- without hand-written SQL."""
        bookworm_register.main(ol_config="x.yml", provider="project_gutenberg")
        FeedRegistry.advance(registered()["project_gutenberg"].id, last_updated=datetime.datetime(2020, 1, 1))

        bookworm_register.main(ol_config="x.yml", provider="project_gutenberg", since="2026-08-28", reseed=True)

        assert str(registered()["project_gutenberg"].last_updated).startswith("2026-08-28")

    def test_reseed_is_required_to_move_it(self, registry_db):
        bookworm_register.main(ol_config="x.yml", provider="project_gutenberg")
        FeedRegistry.advance(registered()["project_gutenberg"].id, last_updated=datetime.datetime(2020, 1, 1))

        bookworm_register.main(ol_config="x.yml", provider="project_gutenberg", since="2026-08-28")

        assert str(registered()["project_gutenberg"].last_updated).startswith("2020-01-01")


class TestUrlChange:
    def test_a_changed_url_warns_about_the_stale_row(self, registry_db, caplog, monkeypatch):
        """register() is keyed on provider_name + url, so editing a feed's URL
        leaves TWO live rows for one provider, both harvested every pass."""
        bookworm_register.main(ol_config="x.yml", provider="project_gutenberg")
        monkeypatch.setitem(bookworm_register.FEEDS["project_gutenberg"], "url", "https://opds.pglaf.org/opds/search?sort=fil")

        with caplog.at_level(logging.WARNING):
            bookworm_register.main(ol_config="x.yml", provider="project_gutenberg")

        assert "DIFFERENT url" in caplog.text
        assert len([f for f in FeedRegistry.all() if f.provider_name == "project_gutenberg"]) == 2


class TestShow:
    def test_show_prints_a_registered_feed(self, registry_db, capsys):
        """The empty-registry case never exercises the print loop at all."""
        bookworm_register.main(ol_config="x.yml", provider="lenny")
        capsys.readouterr()

        bookworm_register.main(ol_config="x.yml", show=True)

        out = capsys.readouterr().out
        assert "lenny" in out
        assert "lennyforlibraries.org" in out

    def test_show_honours_provider(self, registry_db, capsys):
        bookworm_register.main(ol_config="x.yml")
        capsys.readouterr()

        bookworm_register.main(ol_config="x.yml", provider="lenny", show=True)

        out = capsys.readouterr().out
        assert "lenny" in out
        assert "project_gutenberg" not in out


class TestActivation:
    def test_registering_does_not_activate(self, registry_db):
        """Registering must be safe: a new feed is not picked up by cron."""
        bookworm_register.main(ol_config="x.yml", provider="lenny")
        assert registered()["lenny"].is_active is False

    def test_activate_flag_activates(self, registry_db):
        bookworm_register.main(ol_config="x.yml", provider="lenny", activate=True)
        assert registered()["lenny"].is_active is True

    def test_activating_an_existing_feed_preserves_its_cursor(self, registry_db):
        """The two-step rollout: register, validate, then activate -- without
        rewinding whatever progress a validation run made."""
        bookworm_register.main(ol_config="x.yml", provider="lenny")
        FeedRegistry.advance(registered()["lenny"].id, last_updated=datetime.datetime(2026, 9, 1))

        bookworm_register.main(ol_config="x.yml", provider="lenny", activate=True)

        feed = registered()["lenny"]
        assert feed.is_active is True
        assert str(feed.last_updated).startswith("2026-09-01")
        assert feed.supports_modified_since is True  # connector config survived

    def test_show_reports_status(self, registry_db, capsys):
        bookworm_register.main(ol_config="x.yml", provider="lenny")
        capsys.readouterr()
        bookworm_register.main(ol_config="x.yml", show=True)
        assert "[pending]" in capsys.readouterr().out
