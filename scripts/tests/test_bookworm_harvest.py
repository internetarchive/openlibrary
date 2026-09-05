"""Tests for the BookWorm cron entrypoint (#12844).

The runner is what ops actually invokes on the ol-home0 cron container, so the
behaviour under test here is operational: which feeds a run touches, whether a
failure is visible to cron, and whether a dry run is genuinely inert.
"""

from __future__ import annotations

import pytest

from scripts import bookworm_harvest


class FakeFeed:
    def __init__(self, provider_name: str):
        self.provider_name = provider_name
        self.id = hash(provider_name) % 1000


@pytest.fixture
def runner(monkeypatch):
    """Stub out config loading and harvesting; record what the runner asked for."""
    calls: dict = {"harvest_feed": [], "harvest_all": 0, "sleeps": [], "setup_requests": 0, "load_config": None}
    feeds = [FakeFeed("lenny"), FakeFeed("project_gutenberg")]

    def fake_load_config(path):
        calls["load_config"] = path

    def fake_setup_requests():
        calls["setup_requests"] += 1

    monkeypatch.setattr(bookworm_harvest, "load_config", fake_load_config)
    monkeypatch.setattr(bookworm_harvest, "setup_requests", fake_setup_requests)
    monkeypatch.setattr(bookworm_harvest.FeedRegistry, "all", staticmethod(lambda: feeds))

    def fake_harvest_feed(feed, **kwargs):
        calls["harvest_feed"].append((feed.provider_name, kwargs))
        return {"feed": feed.provider_name, "records": 3}

    def fake_harvest_all(**kwargs):
        calls["harvest_all"] += 1
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
        assert runner["setup_requests"] == 1


class TestFeedSelection:
    def test_default_harvests_every_feed(self, runner):
        bookworm_harvest.main(ol_config="x.yml")
        assert runner["harvest_all"] == 1
        assert runner["harvest_feed"] == []

    def test_provider_harvests_only_that_feed(self, runner):
        bookworm_harvest.main(ol_config="x.yml", provider="lenny")
        assert [name for name, _ in runner["harvest_feed"]] == ["lenny"]
        assert runner["harvest_all"] == 0

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


class TestDryRun:
    def test_dry_run_is_passed_through(self, runner):
        bookworm_harvest.main(ol_config="x.yml", dry_run=True)
        assert runner["harvest_all"] == 1

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
