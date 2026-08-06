"""Tests for the on-demand Retention Score script (issue #11956)."""

import json
from typing import ClassVar
from unittest.mock import patch

import pytest

from openlibrary.core import retention
from openlibrary.core.matomo import MatomoError
from scripts import gather_retention_scores as script

SCORES = {
    "window_hours": 1,
    "since": "2026-07-27T12:00:00+00:00",
    "visits": 2,
    "cohorts": {cohort: {"patrons": 0, "weighted_total": 0, "engagement": 0.0} for cohort in retention.COHORTS},
    "classes": {
        cls: {"weight": info["weight"], "patrons": 1, "weighted_total": 100, "engagement": 100.0, "contribution": info["weight"] * 100}
        for cls, info in script.PATRON_CLASSES.items()
    },
    "r_total": 171.0,
    "r_per_patron": 42.75,
    "events": {},
    "total_patrons": 4,
    "data_quality": {
        "missing_dimension": 0,
        "unknown_cohort": 0,
        "unidentified_patrons": 0,
        "dropped_no_timestamp": 0,
        "started_before_window": 0,
        "truncated": False,
    },
    "warnings": [],
}


@pytest.fixture
def configfile(tmp_path):
    path = tmp_path / "openlibrary.yml"
    path.write_text("matomo_api: from-config\n")
    return str(path)


class TestResolveToken:
    def test_reads_the_token_from_the_config_file(self, configfile, monkeypatch):
        monkeypatch.delenv("MATOMO_TOKEN", raising=False)
        assert script.resolve_token(configfile) == "from-config"

    def test_environment_takes_precedence_over_the_config_file(self, configfile, monkeypatch):
        monkeypatch.setenv("MATOMO_TOKEN", "from-env")
        assert script.resolve_token(configfile) == "from-env"

    def test_returns_empty_when_the_key_is_blank(self, tmp_path, monkeypatch):
        monkeypatch.delenv("MATOMO_TOKEN", raising=False)
        path = tmp_path / "openlibrary.yml"
        path.write_text("matomo_api:\n")
        assert script.resolve_token(str(path)) == ""

    def test_returns_empty_for_an_empty_config_file(self, tmp_path, monkeypatch):
        monkeypatch.delenv("MATOMO_TOKEN", raising=False)
        path = tmp_path / "openlibrary.yml"
        path.write_text("")
        assert script.resolve_token(str(path)) == ""


class TestMain:
    def test_fails_cleanly_without_a_token(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("MATOMO_TOKEN", raising=False)
        path = tmp_path / "openlibrary.yml"
        path.write_text("matomo_api:\n")
        assert script.main([str(path)]) == 1
        assert "No Matomo token found" in capsys.readouterr().err

    def test_rejects_a_zero_hour_window(self, configfile, capsys):
        assert script.main([configfile, "--hours", "0"]) == 1
        assert "--hours must be at least 1" in capsys.readouterr().err

    def test_reports_an_unreachable_matomo_without_a_traceback(self, configfile, capsys):
        with patch.object(script, "gather_retention_scores", side_effect=MatomoError("no route to host")):
            assert script.main([configfile]) == 1
        err = capsys.readouterr().err
        assert "Could not reach Matomo" in err
        assert "HTTPS_PROXY" in err

    def test_prints_a_report_and_succeeds(self, configfile, capsys):
        with patch.object(script, "gather_retention_scores", return_value=SCORES):
            assert script.main([configfile]) == 0
        out = capsys.readouterr().out
        assert "R_total" in out
        assert "171.00" in out

    def test_does_not_push_to_statsd_by_default(self, configfile):
        """An ad hoc run must not contaminate the hourly gauge series."""
        with (
            patch.object(script, "gather_retention_scores", return_value=SCORES),
            patch.object(script, "write_retention_to_statsd") as mock_write,
        ):
            assert script.main([configfile]) == 0
        mock_write.assert_not_called()

    def test_pushes_to_statsd_when_asked(self, configfile):
        with (
            patch.object(script, "gather_retention_scores", return_value=SCORES),
            patch.object(script, "write_retention_to_statsd") as mock_write,
        ):
            assert script.main([configfile, "--statsd"]) == 0
        mock_write.assert_called_once_with(configfile, SCORES)

    def test_json_output_is_parseable(self, configfile, capsys):
        with patch.object(script, "gather_retention_scores", return_value=SCORES):
            assert script.main([configfile, "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["r_total"] == 171.0

    def test_passes_the_requested_window_through(self, configfile):
        with patch.object(script, "gather_retention_scores", return_value=SCORES) as mock_gather:
            script.main([configfile, "--hours", "24"])
        assert mock_gather.call_args.kwargs["hours"] == 24

    def test_warnings_go_to_stderr(self, configfile, capsys):
        scores = SCORES | {"warnings": ["registrant: 5 active patrons but zero scored engagement"]}
        with patch.object(script, "gather_retention_scores", return_value=scores):
            script.main([configfile])
        assert "zero scored engagement" in capsys.readouterr().err


class TestByHour:
    HOURLY: ClassVar[list[dict]] = [
        SCORES | {"hour_start": "2026-07-31T04:00:00+00:00", "partial": True, "r_total": 300.0, "total_patrons": 2},
        SCORES | {"hour_start": "2026-07-31T03:00:00+00:00", "partial": False, "r_total": 900.0, "total_patrons": 6},
    ]

    def test_by_hour_uses_the_hourly_gatherer(self, configfile):
        with patch.object(script, "gather_retention_scores_by_hour", return_value=self.HOURLY) as mock_hourly:
            assert script.main([configfile, "--by-hour", "--hours", "2"]) == 0
        assert mock_hourly.call_args.kwargs["hours"] == 2

    def test_prints_one_row_per_hour_most_recent_first(self, configfile, capsys):
        with patch.object(script, "gather_retention_scores_by_hour", return_value=self.HOURLY):
            script.main([configfile, "--by-hour"])
        out = capsys.readouterr().out
        assert "04:00 (partial)" in out
        assert "03:00" in out
        assert out.index("04:00") < out.index("03:00")

    def test_flags_the_partial_hour(self, configfile, capsys):
        with patch.object(script, "gather_retention_scores_by_hour", return_value=self.HOURLY):
            script.main([configfile, "--by-hour"])
        assert "not a drop" in capsys.readouterr().out

    def test_json_emits_the_whole_series(self, configfile, capsys):
        with patch.object(script, "gather_retention_scores_by_hour", return_value=self.HOURLY):
            script.main([configfile, "--by-hour", "--json"])
        assert len(json.loads(capsys.readouterr().out)) == 2

    def test_statsd_records_the_most_recent_COMPLETE_hour(self, configfile):
        """Recording the in-progress hour would write a value that depends on the
        minute the job fired -- a sawtooth in Graphite rather than a measurement."""
        with (
            patch.object(script, "gather_retention_scores_by_hour", return_value=self.HOURLY),
            patch.object(script, "write_retention_to_statsd") as mock_write,
        ):
            script.main([configfile, "--by-hour", "--statsd"])
        recorded = mock_write.call_args.args[1]
        assert recorded["partial"] is False
        assert recorded["r_total"] == 900.0

    def test_statsd_refuses_when_no_complete_hour_is_available(self, configfile, capsys):
        """--hours 1 spans only the hour in progress, so there is nothing to record."""
        only_partial = [self.HOURLY[0]]
        with (
            patch.object(script, "gather_retention_scores_by_hour", return_value=only_partial),
            patch.object(script, "write_retention_to_statsd") as mock_write,
        ):
            assert script.main([configfile, "--by-hour", "--hours", "1", "--statsd"]) == 1
        mock_write.assert_not_called()
        assert "hour in progress" in capsys.readouterr().err


class TestEventBreakdown:
    def test_verbose_lists_the_events_that_earned_points(self, configfile, capsys):
        scores = SCORES | {"events": {"read": {"count": 12, "points": 100, "total": 1200}}}
        with patch.object(script, "gather_retention_scores", return_value=scores):
            script.main([configfile, "--verbose"])
        out = capsys.readouterr().out
        assert "read" in out
        assert "1,200" in out

    def test_events_are_hidden_without_verbose(self, configfile, capsys):
        scores = SCORES | {"events": {"read": {"count": 12, "points": 100, "total": 1200}}}
        with patch.object(script, "gather_retention_scores", return_value=scores):
            script.main([configfile])
        assert "1,200" not in capsys.readouterr().out
