"""Covers the monitoring jobs themselves, not just the helpers they call.

The jobs are where the metric paths are actually chosen and submitted, so
without these a refactor can stop emitting a series entirely while every
helper-level test stays green.
"""

import asyncio
import importlib
import types

import pytest

from scripts.monitoring.utils import GraphiteEvent


@pytest.fixture
def monitor(monkeypatch):
    """Import monitor.py fresh, so promoter state does not leak between tests."""
    # Imported here, not at module scope: monitor.py reads HOSTNAME at import time.
    monkeypatch.setenv("HOSTNAME", "ol-www0.us.archive.org")
    return importlib.reload(importlib.import_module("scripts.monitoring.monitor"))


@pytest.fixture
def submitted(monkeypatch):
    events: list[GraphiteEvent] = []
    monkeypatch.setattr(GraphiteEvent, "submit_many", staticmethod(lambda evts, _addr: events.extend(evts)))
    return events


def _stub_bash(monkeypatch, monitor, **by_command):
    """Stub bash_run, dispatching on the command so each job sees its own output."""

    def fake_bash_run(cmd, **_kwargs):
        return types.SimpleNamespace(stdout=by_command.get(cmd.strip(), ""))

    monkeypatch.setattr(monitor, "bash_run", fake_bash_run)


def test_monitor_nginx_logs_submits_promoted_bots_and_other(monitor, submitted, monkeypatch):
    _stub_bash(
        monkeypatch,
        monitor,
        list_unknown_bot_counts="     90 aggressivecrawler\n      2 rarespider\n",
    )

    monitor.monitor_nginx_logs()

    # aggressivecrawler clears the 75 floor on its first tick; rarespider does not
    # and aggregates into other. Both land under the ol-www0 bucket, `ol`.
    assert sorted((e.path, e.value) for e in submitted) == [
        ("stats.ol.bot_traffic.aggressivecrawler", 90.0),
        ("stats.ol.bot_traffic.other", 2.0),
    ]


def test_monitor_nginx_logs_still_submits_other_when_nothing_is_promoted(monitor, submitted, monkeypatch):
    _stub_bash(monkeypatch, monitor, list_unknown_bot_counts="      3 rarespider\n")

    monitor.monitor_nginx_logs()

    assert [(e.path, e.value) for e in submitted] == [("stats.ol.bot_traffic.other", 3.0)]


def test_monitor_partner_useragents_promotes_a_new_partner_past_the_pinned_list(monitor, submitted, monkeypatch):
    _stub_bash(
        monkeypatch,
        monitor,
        **{
            monitor.PARTNER_UA_COMMAND.strip(): """
    120 NewHotPartner/1.0 (https://new.example; x@new.example)
      2 Gleeph/1.0 (x@gleeph.net)
      1 SomeoneRandom/1.0 (x@random.example)
"""
        },
    )

    asyncio.run(monitor.monitor_partner_useragents())
    by_path = {e.path: e.value for e in submitted}

    # The whole point of the feature: a partner nobody has added to the pinned
    # list gets its own series. The 89 pinned names must not crowd it out.
    assert by_path["stats.ol.partners.NewHotPartner"] == 120.0
    # Pinned partners keep their series however quiet they are...
    assert by_path["stats.ol.partners.Gleeph"] == 2.0
    # ...but a pinned partner that sent nothing this minute is left out entirely,
    # exactly as before this change, so its existing series is sampled the same way.
    assert "stats.ol.partners.Bontent" not in by_path
    # Genuinely unknown low-volume traffic is what `other` is for.
    assert by_path["stats.ol.partners.other"] == 1.0


def test_partner_label_uses_the_first_user_agent_token(monitor):
    assert monitor.partner_label("Bontent/1.0 (https://bontent.app; x@bontent.app)") == "Bontent"
    assert monitor.partner_label("ISBN.nu Book Price Comparison (x@isbn.nu)") == "ISBN_nu"


def test_pinned_partner_names_match_the_committed_snapshot(monitor):
    assert len(monitor.PINNED_PARTNER_NAMES) == 89
    for name in ("Bontent", "Gleeph", "Bookscovery", "UMDB"):
        assert name in monitor.PINNED_PARTNER_NAMES
