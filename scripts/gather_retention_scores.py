#!/usr/bin/env python3
"""Compute the Core Vitals Retention Score on demand (issue #11956).

Runs the same scoring a scheduled job would, against any window, so you can ask
"what is the score right now?" at any moment. Scoring lives in
`openlibrary/core/retention.py`; this is just a way to drive it.

Prints by default and pushes nothing: an ad hoc run should not contaminate the
gauge series a scheduled job feeds. Pass --statsd when you do want it recorded.

    # Score the last hour and print a breakdown
    ./scripts/gather_retention_scores.py conf/openlibrary.yml

    # Last 24 hours, per-cohort and per-event detail, as JSON
    ./scripts/gather_retention_scores.py conf/openlibrary.yml --hours 24 --verbose --json

    # Score the last complete clock hour and record it to statsd
    ./scripts/gather_retention_scores.py /olsystem/etc/openlibrary.yml --by-hour --hours 2 --statsd

Flags come from the signature of main() via FnToCLI, so booleans also accept
their --no- form (e.g. --no-statsd).

The Matomo token is read from `matomo_api` in the config file, or from a
MATOMO_TOKEN environment variable, which takes precedence and saves developers
editing a checked-in config. Matomo is reachable from IA infrastructure; from a
developer machine, set HTTPS_PROXY to an allowlisted forward proxy.
"""

import json as jsonlib
import sys

try:
    import _init_path  # type: ignore[import-not-found]  # noqa: F401 side effect: add OL package root to sys.path
except ImportError:
    import scripts._init_path  # noqa: F401 same side effect when imported as a package

from openlibrary.core.matomo import MatomoError
from openlibrary.core.retention import (
    PATRON_CLASSES,
    UNTRACKED_EVENTS,
    gather_retention_scores,
    gather_retention_scores_by_hour,
    resolve_token,
    retention_gauges,
    write_retention_to_statsd,
)
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI


def print_report(scores: dict, verbose: bool) -> None:
    print(f"\nOpen Library Retention Score — last {scores['window_hours']}h (since {scores['since']})")
    print(f"{scores['visits']:,} visits scored")
    print("=" * 72)
    print(f"  {'CLASS':<12} {'PATRONS':>9} {'POINTS':>10} {'E(t)':>9} {'w':>6} {'w*P*E':>12}")
    print("  " + "-" * 62)

    for cls in PATRON_CLASSES:
        data = scores["classes"][cls]
        print(f"  {cls:<12} {data['patrons']:>9,} {data['weighted_total']:>10,} {data['engagement']:>9.2f} {data['weight']:>6.2f} {data['contribution']:>12,.2f}")
        if verbose:
            for cohort in PATRON_CLASSES[cls]["cohorts"]:
                cohort_data = scores["cohorts"][cohort]
                print(f"    {cohort:<10} {cohort_data['patrons']:>9,} {cohort_data['weighted_total']:>10,} {cohort_data['engagement']:>9.2f}")

    print("  " + "-" * 62)
    print(f"  R_total          = {scores['r_total']:,.2f}")
    print(f"  R per patron     = {scores['r_per_patron']:.4f}")

    if verbose and scores["events"]:
        # Which events actually earned the points. This is what makes R_total
        # explainable, and what makes a mis-mapped event visible as a zero.
        print(f"\n  {'EVENT':<28} {'COUNT':>8} {'PTS':>6} {'TOTAL':>10}")
        print("  " + "-" * 54)
        for name, event in scores["events"].items():
            print(f"  {name:<28} {event['count']:>8,} {event['points']:>6} {event['total']:>10,}")

    if untracked := ", ".join(f"{name} ({points}pts)" for name, points in UNTRACKED_EVENTS.items()):
        print(f"\n  No working Matomo source, scoring 0 (#12366): {untracked}")

    for warning in scores["warnings"]:
        print(f"  WARNING: {warning}", file=sys.stderr)


def print_hourly_report(hourly: list[dict], verbose: bool) -> None:
    """One row per clock hour, most recent first, then the newest hour in full."""
    print(f"\nOpen Library Retention Score — last {len(hourly)} clock hours")
    print("=" * 72)
    print(f"  {'HOUR (UTC)':<18} {'R_TOTAL':>12} {'R/PATRON':>10} {'PATRONS':>9} {'VISITS':>9}")
    print("  " + "-" * 62)
    for hour in hourly:
        label = hour["hour_start"][11:16] + (" (partial)" if hour["partial"] else "")
        print(f"  {label:<18} {hour['r_total']:>12,.2f} {hour['r_per_patron']:>10.4f} {hour['total_patrons']:>9,} {hour['visits']:>9,}")
    if hourly and hourly[0]["partial"]:
        print("\n  The first row covers only the minutes elapsed so far this hour; it is not")
        print("  comparable to a complete hour and a lower number there is not a drop.")
    if hourly:
        print_report(hourly[0], verbose)


def main(
    openlibrary_config: str,
    hours: int = 1,
    by_hour: bool = False,
    statsd: bool = False,
    json: bool = False,
    verbose: bool = False,
) -> None:
    """Compute the Core Vitals Retention Score for a window ending now.

    :param openlibrary_config: Path to openlibrary.yml, supplying the Matomo token and statsd server
    :param hours: Size of the window to score, in hours
    :param by_hour: Score each of the last --hours clock hours separately instead of as one window
    :param statsd: Also record the scores to statsd; off by default so an ad hoc run cannot contaminate a scheduled series
    :param json: Emit the full result as JSON
    :param verbose: Show the per-cohort and per-event breakdown behind the score
    """
    if hours < 1:
        raise SystemExit("--hours must be at least 1")

    if not (token := resolve_token(openlibrary_config)):
        raise SystemExit(f"No Matomo token found. Set `matomo_api` in {openlibrary_config}, or export MATOMO_TOKEN.")

    hourly: list[dict] | None = None
    # The window to record: under --by-hour that is the most recent *complete*
    # hour, since hourly[0] is still filling up and its value would depend on
    # the minute the job fired.
    recordable: dict | None = None
    try:
        if by_hour:
            hourly = gather_retention_scores_by_hour(token, hours=hours)
            recordable = next((hour for hour in hourly if not hour["partial"]), None)
        else:
            recordable = gather_retention_scores(token, hours=hours)
    except MatomoError as exc:
        raise SystemExit(
            f"Could not reach Matomo: {exc}\nMatomo is restricted to IA's network; set HTTPS_PROXY to an allowlisted proxy if running locally."
        ) from exc

    if json:
        print(jsonlib.dumps(hourly if hourly is not None else recordable, indent=2))
    elif hourly is not None:
        print_hourly_report(hourly, verbose)
    elif recordable is not None:
        print_report(recordable, verbose)

    if statsd:
        if recordable is None:
            raise SystemExit("Nothing recorded: --by-hour --hours 1 covers only the hour in progress. Use --hours 2 or more.")
        write_retention_to_statsd(openlibrary_config, recordable)
        print(f"\nRecorded {len(retention_gauges(recordable))} gauges to statsd for the hour starting {recordable.get('hour_start', recordable['since'])}.")


if __name__ == "__main__":
    FnToCLI(main).run()
