"""Tests for the BookWorm command line (#12844).

Three commands, three concerns.

``harvest`` is what ops actually invokes on the ol-home0 cron container, so what
is tested is operational: which feeds a run touches, whether a failure is
visible to cron, and whether a dry run is genuinely inert.

``register`` writes the feed list, so what is tested is that re-running it is
safe -- never duplicating a feed, never rewinding a cursor that has already
progressed, and never silently ignoring config it cannot apply.

``preview`` only classifies, so its bucketing is tested directly.
"""

from __future__ import annotations

import datetime
import logging
from typing import Final

import pytest
import web

from openlibrary.bookworm import cli
from openlibrary.bookworm.registry import FeedRegistry
from openlibrary.core.db import get_db

# ---------------------------------------------------------------------------
# harvest
# ---------------------------------------------------------------------------


class FakeFeed:
    _next_id = iter(range(1, 1000))

    def __init__(self, provider_name: str):
        self.provider_name = provider_name
        # Deterministic: hash() is PYTHONHASHSEED-dependent.
        self.id = next(FakeFeed._next_id)


@pytest.fixture
def runner(monkeypatch):
    """Stub out config loading and harvesting; record what the runner asked for."""
    calls: dict = {"harvest_feed": [], "harvest_all": 0, "sleeps": [], "setup_requests": 0, "load_config": None, "harvest_all_kwargs": [], "order": []}
    feeds = [FakeFeed("lenny"), FakeFeed("project_gutenberg")]

    def fake_load_config(path):
        calls["load_config"] = path
        calls["order"].append("load_config")

    def fake_setup_requests():
        calls["setup_requests"] += 1
        calls["order"].append("setup_requests")

    monkeypatch.setattr(cli, "load_config", fake_load_config)
    monkeypatch.setattr(cli, "setup_requests", fake_setup_requests)
    monkeypatch.setattr(cli.FeedRegistry, "all", staticmethod(lambda: feeds))

    def fake_harvest_feed(feed, **kwargs):
        calls["harvest_feed"].append((feed.provider_name, kwargs))
        return {"feed": feed.provider_name, "records": 3}

    def fake_harvest_all(**kwargs):
        calls["harvest_all"] += 1
        calls["harvest_all_kwargs"].append(kwargs)
        calls["order"].append("harvest_all")
        return [{"feed": f.provider_name, "records": 3} for f in feeds]

    monkeypatch.setattr(cli.harvest, "harvest_feed", fake_harvest_feed)
    monkeypatch.setattr(cli.harvest, "harvest_all", fake_harvest_all)

    def fake_sleep(seconds):
        calls["sleeps"].append(seconds)

    monkeypatch.setattr(cli.time, "sleep", fake_sleep)
    return calls


class TestProxySetup:
    def test_proxy_config_is_applied_before_any_fetch(self, runner):
        """ol-home0 reaches provider feeds only through an authenticated proxy.

        setup_requests() exports http_proxy / no_proxy_addresses from
        openlibrary.yml into the environment; skipping it means every fetch
        goes direct and times out.
        """
        cli.harvest_command(ol_config="prod.yml")
        assert runner["load_config"] == "prod.yml"
        # Order matters: setup_requests reads infogami.config, so it is
        # meaningless before load_config has populated it.
        assert runner["order"][:2] == ["load_config", "setup_requests"]
        assert runner["order"].index("setup_requests") < runner["order"].index("harvest_all")


class TestFeedSelection:
    def test_default_harvests_every_feed(self, runner):
        cli.harvest_command(ol_config="x.yml")
        assert runner["harvest_all"] == 1
        assert runner["harvest_feed"] == []

    def test_provider_harvests_only_that_feed(self, runner):
        cli.harvest_command(ol_config="x.yml", provider="lenny", dry_run=True)
        assert [name for name, _ in runner["harvest_feed"]] == ["lenny"]
        assert runner["harvest_all"] == 0
        # The fixture captures kwargs; assert on them rather than discarding them.
        assert runner["harvest_feed"][0][1]["dry_run"] is True

    def test_unknown_provider_exits_nonzero(self, runner):
        with pytest.raises(SystemExit) as exc:
            cli.harvest_command(ol_config="x.yml", provider="nope")
        assert exc.value.code != 0


class TestExitStatus:
    """One feed failing must not be invisible to cron.

    The runner used to exit non-zero only when *every* feed errored, so a single
    provider failing forever produced a silent green cron job.
    """

    def test_a_single_failing_feed_is_surfaced(self, runner, monkeypatch):
        monkeypatch.setattr(
            cli.harvest,
            "harvest_all",
            lambda **kw: [
                {"feed": "lenny", "records": 3},
                {"feed": "project_gutenberg", "records": 0, "error": True},
            ],
        )
        with pytest.raises(SystemExit) as exc:
            cli.harvest_command(ol_config="x.yml")
        assert exc.value.code != 0

    def test_all_succeeding_exits_zero(self, runner):
        cli.harvest_command(ol_config="x.yml")  # must not raise

    def test_no_feeds_registered_is_not_a_failure(self, runner, monkeypatch):
        """An empty registry is a fresh install, not an error to page someone about."""
        monkeypatch.setattr(cli.harvest, "harvest_all", lambda **kw: [])
        cli.harvest_command(ol_config="x.yml")  # must not raise


class TestProviderPathIsolatesFailures:
    """--provider had no per-feed guard, so a failure escaped as a traceback
    and --dry-run behaved differently depending on whether --provider was given."""

    def test_a_failing_single_feed_is_reported_not_raised(self, runner, monkeypatch):
        def boom(feed, **kwargs):
            raise RuntimeError("feed exploded")

        monkeypatch.setattr(cli.harvest, "harvest_feed", boom)
        with pytest.raises(SystemExit) as exc:
            cli.harvest_command(ol_config="x.yml", provider="lenny")
        assert exc.value.code != 0  # reported as a failed run, not a traceback

    def test_dry_run_with_provider_does_not_fail_the_job(self, runner, monkeypatch):
        def boom(feed, **kwargs):
            raise RuntimeError("feed exploded")

        monkeypatch.setattr(cli.harvest, "harvest_feed", boom)
        cli.harvest_command(ol_config="x.yml", provider="lenny", dry_run=True)  # must not raise


class TestContinuousFatalErrors:
    def test_a_fatal_error_does_not_look_like_a_clean_stop(self, runner):
        """--continuous caught SystemExit and returned 0, so a supervisor read a
        config error as a successful shutdown and never restarted or alerted."""
        with pytest.raises(SystemExit) as exc:
            cli.harvest_command(ol_config="x.yml", provider="typo", continuous=True, interval=60)
        assert exc.value.code != 0

    def test_interval_floor_is_enforced(self, runner, monkeypatch):
        passes = {"n": 0}

        def fake_harvest_all(**kwargs):
            passes["n"] += 1
            if passes["n"] >= 2:
                raise KeyboardInterrupt
            return [{"feed": "lenny", "records": 1}]

        monkeypatch.setattr(cli.harvest, "harvest_all", fake_harvest_all)
        cli.harvest_command(ol_config="x.yml", continuous=True, interval=0)
        assert runner["sleeps"] == [cli.MIN_INTERVAL_SECONDS]


class TestDryRun:
    def test_dry_run_reaches_the_harvester(self, runner):
        """Assert the flag, not the call count.

        Asserting only that harvest_all ran would still pass if dry_run were
        dropped on the way through -- and the failure that hides is a dry run
        advancing the cursor.
        """
        cli.harvest_command(ol_config="x.yml", dry_run=True)
        assert runner["harvest_all_kwargs"][0]["dry_run"] is True

    def test_a_normal_run_does_not_claim_to_be_a_dry_run(self, runner):
        cli.harvest_command(ol_config="x.yml")
        assert runner["harvest_all_kwargs"][0]["dry_run"] is False

    def test_dry_run_never_exits_nonzero_on_feed_errors(self, runner, monkeypatch):
        """A dry run is a diagnostic; it reports problems rather than failing the job."""
        monkeypatch.setattr(
            cli.harvest,
            "harvest_all",
            lambda **kw: [{"feed": "lenny", "records": 0, "error": True}],
        )
        cli.harvest_command(ol_config="x.yml", dry_run=True)  # must not raise


class TestContinuousMode:
    def test_continuous_loops_and_sleeps_between_passes(self, runner, monkeypatch):
        passes = {"n": 0}

        def fake_harvest_all(**kwargs):
            passes["n"] += 1
            if passes["n"] >= 3:
                raise KeyboardInterrupt
            return [{"feed": "lenny", "records": 1}]

        monkeypatch.setattr(cli.harvest, "harvest_all", fake_harvest_all)
        cli.harvest_command(ol_config="x.yml", continuous=True, interval=1800)

        assert passes["n"] == 3
        assert runner["sleeps"] == [1800, 1800]

    def test_continuous_survives_a_failing_pass(self, runner, monkeypatch):
        """A transient error must not kill a long-running loop."""
        passes = {"n": 0}

        def fake_harvest_all(**kwargs):
            passes["n"] += 1
            if passes["n"] == 1:
                raise RuntimeError("transient")
            raise KeyboardInterrupt

        monkeypatch.setattr(cli.harvest, "harvest_all", fake_harvest_all)
        cli.harvest_command(ol_config="x.yml", continuous=True, interval=60)
        assert passes["n"] == 2

    def test_single_pass_does_not_sleep(self, runner):
        cli.harvest_command(ol_config="x.yml")
        assert runner["sleeps"] == []


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------

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
    monkeypatch.setattr(cli, "load_config", lambda path: None)
    yield db
    db.query("DROP TABLE IF EXISTS feed_registry;")


def registered() -> dict[str, FeedRegistry]:
    return {feed.provider_name: feed for feed in FeedRegistry.all()}


class TestDefaults:
    def test_registers_the_default_feeds(self, registry_db):
        cli.register_command(ol_config="x.yml")
        assert set(registered()) == set(cli.DEFAULT_PROVIDERS)

    def test_bwb_is_not_registered_by_default(self, registry_db):
        """BWB is blocked by Cloudflare; registering it would fail every pass."""
        cli.register_command(ol_config="x.yml")
        assert "betterworldbooks" not in registered()

    def test_bwb_can_be_registered_explicitly(self, registry_db):
        cli.register_command(ol_config="x.yml", provider="betterworldbooks")
        assert "betterworldbooks" in registered()

    def test_lenny_uses_the_server_side_cursor(self, registry_db):
        """Verified against the live feed: lenny honours ?modified_since.

        Registering it as ``client`` would re-crawl all 96 items every run.
        """
        cli.register_command(ol_config="x.yml", provider="lenny")
        assert registered()["lenny"].supports_modified_since is True


class TestConnectorConfig:
    def test_lenny_records_that_its_ids_are_ol_editions(self, registry_db):
        """Without this, Lenny records are matched on title alone."""
        cli.register_command(ol_config="x.yml", provider="lenny")
        assert registered()["lenny"].local_id_is_ol_edition is True

    def test_other_feeds_do_not_claim_it(self, registry_db):
        cli.register_command(ol_config="x.yml", provider="project_gutenberg")
        assert registered()["project_gutenberg"].local_id_is_ol_edition is False

    def test_config_added_after_registration_warns_that_it_is_not_applied(self, registry_db, caplog):
        """register() returns an existing row without touching its data blob.

        So connector config added to FEEDS later never reaches the database, and
        the symptom -- records matched on title alone because
        ``local_id_is_ol_edition`` never arrived -- looks nothing like the cause.
        """
        FeedRegistry.register(
            "lenny",
            cli.FEEDS["lenny"]["url"],
            id_strategy="self_link",
            cursor_style=cli.FEEDS["lenny"]["cursor_style"],
        )
        with caplog.at_level(logging.WARNING):
            cli.register_command(ol_config="x.yml", provider="lenny")
        assert "stale connector config" in caplog.text
        assert "local_id_is_ol_edition" in caplog.text

    def test_no_warning_when_the_config_already_matches(self, registry_db, caplog):
        cli.register_command(ol_config="x.yml", provider="lenny")
        with caplog.at_level(logging.WARNING):
            cli.register_command(ol_config="x.yml", provider="lenny")
        assert "stale connector config" not in caplog.text


class TestIdempotence:
    def test_re_running_does_not_duplicate(self, registry_db):
        cli.register_command(ol_config="x.yml")
        cli.register_command(ol_config="x.yml")
        assert len(FeedRegistry.all()) == len(cli.DEFAULT_PROVIDERS)

    def test_re_running_never_rewinds_a_live_cursor(self, registry_db):
        """The dangerous case: re-applying registration must not replay history."""
        cli.register_command(ol_config="x.yml", provider="lenny")
        feed = registered()["lenny"]
        FeedRegistry.advance(feed.id, last_updated=datetime.datetime(2026, 9, 1))

        cli.register_command(ol_config="x.yml", provider="lenny", since="2020-01-01")

        assert str(registered()["lenny"].last_updated).startswith("2026-09-01")


class TestCursorSeeding:
    def test_since_seeds_the_cursor_on_first_registration(self, registry_db):
        cli.register_command(ol_config="x.yml", provider="project_gutenberg", since="2026-08-28")
        assert str(registered()["project_gutenberg"].last_updated).startswith("2026-08-28")

    def test_no_since_leaves_the_cursor_null(self, registry_db):
        """A null cursor means the first run backfills from the beginning."""
        cli.register_command(ol_config="x.yml", provider="lenny")
        assert registered()["lenny"].last_updated is None

    def test_bad_since_is_rejected(self, registry_db):
        with pytest.raises(SystemExit):
            cli.register_command(ol_config="x.yml", provider="lenny", since="28/08/2026")


class TestSafety:
    def test_unknown_provider_exits_nonzero(self, registry_db):
        with pytest.raises(SystemExit):
            cli.register_command(ol_config="x.yml", provider="nope")

    def test_dry_run_writes_nothing(self, registry_db):
        cli.register_command(ol_config="x.yml", dry_run=True)
        assert FeedRegistry.all() == []

    def test_show_writes_nothing(self, registry_db, capsys):
        cli.register_command(ol_config="x.yml", show=True)
        assert FeedRegistry.all() == []
        assert "empty" in capsys.readouterr().out


class TestReseed:
    def test_reseed_moves_an_existing_cursor(self, registry_db):
        """The recovery path for 'registered it, then realised the backfill is
        too large' -- without hand-written SQL."""
        cli.register_command(ol_config="x.yml", provider="project_gutenberg")
        FeedRegistry.advance(registered()["project_gutenberg"].id, last_updated=datetime.datetime(2020, 1, 1))

        cli.register_command(ol_config="x.yml", provider="project_gutenberg", since="2026-08-28", reseed=True)

        assert str(registered()["project_gutenberg"].last_updated).startswith("2026-08-28")

    def test_reseed_is_required_to_move_it(self, registry_db):
        cli.register_command(ol_config="x.yml", provider="project_gutenberg")
        FeedRegistry.advance(registered()["project_gutenberg"].id, last_updated=datetime.datetime(2020, 1, 1))

        cli.register_command(ol_config="x.yml", provider="project_gutenberg", since="2026-08-28")

        assert str(registered()["project_gutenberg"].last_updated).startswith("2020-01-01")


class TestUrlChange:
    def test_a_changed_url_warns_about_the_stale_row(self, registry_db, caplog, monkeypatch):
        """register() is keyed on provider_name + url, so editing a feed's URL
        leaves TWO live rows for one provider, both harvested every pass."""
        cli.register_command(ol_config="x.yml", provider="project_gutenberg")
        monkeypatch.setitem(cli.FEEDS["project_gutenberg"], "url", "https://opds.pglaf.org/opds/search?sort=fil")

        with caplog.at_level(logging.WARNING):
            cli.register_command(ol_config="x.yml", provider="project_gutenberg")

        assert "DIFFERENT url" in caplog.text
        assert len([f for f in FeedRegistry.all() if f.provider_name == "project_gutenberg"]) == 2


class TestShow:
    def test_show_prints_a_registered_feed(self, registry_db, capsys):
        """The empty-registry case never exercises the print loop at all."""
        cli.register_command(ol_config="x.yml", provider="lenny")
        capsys.readouterr()

        cli.register_command(ol_config="x.yml", show=True)

        out = capsys.readouterr().out
        assert "lenny" in out
        # Compare against the registered spec rather than repeating the literal,
        # so the test cannot drift from FEEDS.
        assert cli.FEEDS["lenny"]["url"] in out

    def test_show_honours_provider(self, registry_db, capsys):
        cli.register_command(ol_config="x.yml")
        capsys.readouterr()

        cli.register_command(ol_config="x.yml", provider="lenny", show=True)

        out = capsys.readouterr().out
        assert "lenny" in out
        assert "project_gutenberg" not in out


class TestActivation:
    def test_registering_does_not_activate(self, registry_db):
        """Registering must be safe: a new feed is not picked up by cron."""
        cli.register_command(ol_config="x.yml", provider="lenny")
        assert registered()["lenny"].is_active is False

    def test_activate_flag_activates(self, registry_db):
        cli.register_command(ol_config="x.yml", provider="lenny", activate=True)
        assert registered()["lenny"].is_active is True

    def test_activating_an_existing_feed_preserves_its_cursor(self, registry_db):
        """The two-step rollout: register, validate, then activate -- without
        rewinding whatever progress a validation run made."""
        cli.register_command(ol_config="x.yml", provider="lenny")
        FeedRegistry.advance(registered()["lenny"].id, last_updated=datetime.datetime(2026, 9, 1))

        cli.register_command(ol_config="x.yml", provider="lenny", activate=True)

        feed = registered()["lenny"]
        assert feed.is_active is True
        assert str(feed.last_updated).startswith("2026-09-01")
        assert feed.supports_modified_since is True  # connector config survived

    def test_show_reports_status(self, registry_db, capsys):
        cli.register_command(ol_config="x.yml", provider="lenny")
        capsys.readouterr()
        cli.register_command(ol_config="x.yml", show=True)
        assert "[pending]" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# preview
# ---------------------------------------------------------------------------


def record(local_id: str | None) -> dict:
    acquisitions = [{"provider_name": "lenny", "local_id": local_id}] if local_id else []
    return {"title": "A Book", "source_records": [f"lenny:{local_id}"], "acquisitions": acquisitions}


def reply(key: str | None, status: str = "matched") -> dict:
    return {"success": True, "edition": {"key": key, "status": status} if key else {}}


class TestExpectedEditionKey:
    def test_a_numeric_local_id_names_an_edition(self):
        """Lenny encodes the OL edition number in its self link."""
        assert cli.expected_edition_key(record("51008637")) == "/books/OL51008637M"

    def test_a_non_numeric_id_names_nothing(self):
        assert cli.expected_edition_key(record("urn:isbn:9781737408802")) is None

    def test_no_acquisitions_names_nothing(self):
        assert cli.expected_edition_key(record(None)) is None


class TestClassify:
    def test_the_expected_edition(self):
        bucket, matched, expected = cli.classify(record("51008637"), reply("/books/OL51008637M"))
        assert bucket == cli.MATCHED_EXPECTED
        assert matched == expected == "/books/OL51008637M"

    def test_a_different_edition_is_flagged(self):
        """The silent failure. Feeds of public-domain classics hit the most
        duplicated records in the catalog, so title matching finds a large pool
        and picks one -- confidently, and with no error."""
        bucket, matched, expected = cli.classify(record("51008637"), reply("/books/OL999M"))
        assert bucket == cli.MATCHED_OTHER
        assert matched == "/books/OL999M"
        assert expected == "/books/OL51008637M"

    def test_a_create_is_its_own_bucket(self):
        bucket, _, _ = cli.classify(record("51008637"), reply("/books/OL__new__1M", status="created"))
        assert bucket == cli.WOULD_CREATE

    def test_no_edition_resolved(self):
        assert cli.classify(record("51008637"), reply(None))[0] == cli.NO_ANSWER

    def test_an_empty_reply_does_not_crash(self):
        assert cli.classify(record("51008637"), {})[0] == cli.NO_ANSWER

    @pytest.mark.parametrize("status", ["matched", "modified"])
    def test_both_non_create_statuses_are_compared(self, status):
        assert cli.classify(record("51008637"), reply("/books/OL999M", status=status))[0] == cli.MATCHED_OTHER

    def test_a_feed_without_edition_ids_is_not_judged(self):
        """For a feed whose local_id is an ISBN there is nothing to compare, so
        a match must not be reported as wrong."""
        bucket, _, expected = cli.classify(record("urn:isbn:1"), reply("/books/OL5M"))
        assert bucket == cli.MATCHED_EXPECTED
        assert expected is None

    def test_expectations_can_be_turned_off(self):
        bucket, _, _ = cli.classify(record("51008637"), reply("/books/OL999M"), expect_edition_ids=False)
        assert bucket == cli.MATCHED_EXPECTED


def test_expected_edition_key_prefers_the_named_edition():
    """The ``openlibrary`` field is what the catalog is actually handed.

    Matching against it means the id was honoured, not that the answer happened
    to agree.
    """
    named = {"openlibrary": "OL51008637M", "acquisitions": [{"local_id": "999"}]}
    assert cli.expected_edition_key(named) == "/books/OL51008637M"


def test_expected_edition_key_falls_back_to_the_acquisition_id():
    """So a feed registered before ``local_id_is_ol_edition`` existed still
    reports a split -- which is one of the failures worth catching."""
    assert cli.expected_edition_key({"acquisitions": [{"local_id": "51008637"}]}) == "/books/OL51008637M"
