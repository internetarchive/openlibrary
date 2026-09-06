"""Tests for the BookWorm cron entrypoint (#12844).

The runner is what ops actually invokes on the ol-home0 cron container, so the
behaviour under test here is operational: which feeds a run touches, whether a
failure is visible to cron, and whether a dry run is genuinely inert.
"""

from __future__ import annotations

import pytest

from scripts import bookworm_harvest


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

    monkeypatch.setattr(bookworm_harvest, "load_config", fake_load_config)
    monkeypatch.setattr(bookworm_harvest, "setup_requests", fake_setup_requests)
    monkeypatch.setattr(bookworm_harvest.FeedRegistry, "all", staticmethod(lambda: feeds))

    def fake_harvest_feed(feed, **kwargs):
        calls["harvest_feed"].append((feed.provider_name, kwargs))
        return {"feed": feed.provider_name, "records": 3}

    def fake_harvest_all(**kwargs):
        calls["harvest_all"] += 1
        calls["harvest_all_kwargs"].append(kwargs)
        calls["order"].append("harvest_all")
        return [{"feed": f.provider_name, "records": 3} for f in feeds]

    monkeypatch.setattr(bookworm_harvest.harvest, "harvest_feed", fake_harvest_feed)
    monkeypatch.setattr(bookworm_harvest.harvest, "harvest_all", fake_harvest_all)

    def fake_sleep(seconds):
        calls["sleeps"].append(seconds)

    monkeypatch.setattr(bookworm_harvest.time, "sleep", fake_sleep)
    return calls


class TestProxySetup:
    def test_proxy_config_is_applied_before_any_fetch(self, runner):
        """ol-home0 reaches provider feeds only through an authenticated proxy.

        setup_requests() exports http_proxy / no_proxy_addresses from
        openlibrary.yml into the environment; skipping it means every fetch
        goes direct and times out.
        """
        bookworm_harvest.main(ol_config="prod.yml")
        assert runner["load_config"] == "prod.yml"
        # Order matters: setup_requests reads infogami.config, so it is
        # meaningless before load_config has populated it.
        assert runner["order"][:2] == ["load_config", "setup_requests"]
        assert runner["order"].index("setup_requests") < runner["order"].index("harvest_all")


class TestFeedSelection:
    def test_default_harvests_every_feed(self, runner):
        bookworm_harvest.main(ol_config="x.yml")
        assert runner["harvest_all"] == 1
        assert runner["harvest_feed"] == []

    def test_provider_harvests_only_that_feed(self, runner):
        bookworm_harvest.main(ol_config="x.yml", provider="lenny", dry_run=True)
        assert [name for name, _ in runner["harvest_feed"]] == ["lenny"]
        assert runner["harvest_all"] == 0
        # The fixture captures kwargs; assert on them rather than discarding them.
        assert runner["harvest_feed"][0][1]["dry_run"] is True

    def test_unknown_provider_exits_nonzero(self, runner):
        with pytest.raises(SystemExit) as exc:
            bookworm_harvest.main(ol_config="x.yml", provider="nope")
        assert exc.value.code != 0


class TestExitStatus:
    """One feed failing must not be invisible to cron.

    The runner used to exit non-zero only when *every* feed errored, so a single
    provider failing forever produced a silent green cron job.
    """

    def test_a_single_failing_feed_is_surfaced(self, runner, monkeypatch):
        monkeypatch.setattr(
            bookworm_harvest.harvest,
            "harvest_all",
            lambda **kw: [
                {"feed": "lenny", "records": 3},
                {"feed": "project_gutenberg", "records": 0, "error": True},
            ],
        )
        with pytest.raises(SystemExit) as exc:
            bookworm_harvest.main(ol_config="x.yml")
        assert exc.value.code != 0

    def test_all_succeeding_exits_zero(self, runner):
        bookworm_harvest.main(ol_config="x.yml")  # must not raise

    def test_no_feeds_registered_is_not_a_failure(self, runner, monkeypatch):
        """An empty registry is a fresh install, not an error to page someone about."""
        monkeypatch.setattr(bookworm_harvest.harvest, "harvest_all", lambda **kw: [])
        bookworm_harvest.main(ol_config="x.yml")  # must not raise


class TestProviderPathIsolatesFailures:
    """--provider had no per-feed guard, so a failure escaped as a traceback
    and --dry-run behaved differently depending on whether --provider was given."""

    def test_a_failing_single_feed_is_reported_not_raised(self, runner, monkeypatch):
        def boom(feed, **kwargs):
            raise RuntimeError("feed exploded")

        monkeypatch.setattr(bookworm_harvest.harvest, "harvest_feed", boom)
        with pytest.raises(SystemExit) as exc:
            bookworm_harvest.main(ol_config="x.yml", provider="lenny")
        assert exc.value.code != 0  # reported as a failed run, not a traceback

    def test_dry_run_with_provider_does_not_fail_the_job(self, runner, monkeypatch):
        def boom(feed, **kwargs):
            raise RuntimeError("feed exploded")

        monkeypatch.setattr(bookworm_harvest.harvest, "harvest_feed", boom)
        bookworm_harvest.main(ol_config="x.yml", provider="lenny", dry_run=True)  # must not raise


class TestContinuousFatalErrors:
    def test_a_fatal_error_does_not_look_like_a_clean_stop(self, runner):
        """--continuous caught SystemExit and returned 0, so a supervisor read a
        config error as a successful shutdown and never restarted or alerted."""
        with pytest.raises(SystemExit) as exc:
            bookworm_harvest.main(ol_config="x.yml", provider="typo", continuous=True, interval=60)
        assert exc.value.code != 0

    def test_interval_floor_is_enforced(self, runner, monkeypatch):
        passes = {"n": 0}

        def fake_harvest_all(**kwargs):
            passes["n"] += 1
            if passes["n"] >= 2:
                raise KeyboardInterrupt
            return [{"feed": "lenny", "records": 1}]

        monkeypatch.setattr(bookworm_harvest.harvest, "harvest_all", fake_harvest_all)
        bookworm_harvest.main(ol_config="x.yml", continuous=True, interval=0)
        assert runner["sleeps"] == [bookworm_harvest.MIN_INTERVAL_SECONDS]


class TestDryRun:
    def test_dry_run_reaches_the_harvester(self, runner):
        """Assert the flag, not the call count.

        Asserting only that harvest_all ran would still pass if dry_run were
        dropped on the way through -- and the failure that hides is a dry run
        advancing the cursor.
        """
        bookworm_harvest.main(ol_config="x.yml", dry_run=True)
        assert runner["harvest_all_kwargs"][0]["dry_run"] is True

    def test_a_normal_run_does_not_claim_to_be_a_dry_run(self, runner):
        bookworm_harvest.main(ol_config="x.yml")
        assert runner["harvest_all_kwargs"][0]["dry_run"] is False

    def test_dry_run_never_exits_nonzero_on_feed_errors(self, runner, monkeypatch):
        """A dry run is a diagnostic; it reports problems rather than failing the job."""
        monkeypatch.setattr(
            bookworm_harvest.harvest,
            "harvest_all",
            lambda **kw: [{"feed": "lenny", "records": 0, "error": True}],
        )
        bookworm_harvest.main(ol_config="x.yml", dry_run=True)  # must not raise


class TestContinuousMode:
    def test_continuous_loops_and_sleeps_between_passes(self, runner, monkeypatch):
        passes = {"n": 0}

        def fake_harvest_all(**kwargs):
            passes["n"] += 1
            if passes["n"] >= 3:
                raise KeyboardInterrupt
            return [{"feed": "lenny", "records": 1}]

        monkeypatch.setattr(bookworm_harvest.harvest, "harvest_all", fake_harvest_all)
        bookworm_harvest.main(ol_config="x.yml", continuous=True, interval=1800)

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

        monkeypatch.setattr(bookworm_harvest.harvest, "harvest_all", fake_harvest_all)
        bookworm_harvest.main(ol_config="x.yml", continuous=True, interval=60)
        assert passes["n"] == 2

    def test_single_pass_does_not_sleep(self, runner):
        bookworm_harvest.main(ol_config="x.yml")
        assert runner["sleeps"] == []
