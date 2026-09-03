#!/usr/bin/env python3
"""Compute the Core Vitals Retention Score on demand (issue #11956).

Runs the same scoring a scheduled job would, against any window, so you can ask
"what is the score right now?" at any moment. Scoring lives in
`openlibrary/core/retention.py`; this is just a way to drive it.

Prints by default and pushes nothing: an ad hoc run should not contaminate the
gauge series a scheduled job feeds. Pass --statsd when you do want it recorded.

    # Score the last hour and print a breakdown
    ./scripts/gather_retention_scores.py conf/openlibrary.yml

    # Last 24 hours, per-cohort detail, as JSON
    ./scripts/gather_retention_scores.py conf/openlibrary.yml --hours 24 --verbose --json

    # Score the last complete clock hour and record it to statsd
    ./scripts/gather_retention_scores.py /olsystem/etc/openlibrary.yml --by-hour --hours 2 --statsd

The Matomo token is read from `matomo_api` in the config file, or from a
MATOMO_TOKEN environment variable, which takes precedence and saves developers
editing a checked-in config. Matomo is reachable from IA infrastructure; from a
developer machine, set HTTPS_PROXY to an allowlisted forward proxy.
"""

import argparse
import json
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("openlibrary_config", help="Path to openlibrary.yml (supplies the Matomo token and statsd server)")
    parser.add_argument("--hours", type=int, default=1, help="Size of the window to score, in hours (default: 1)")
    parser.add_argument("--statsd", action="store_true", help="Also push the scores to statsd (off by default)")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Emit the full result as JSON")
    parser.add_argument("--verbose", action="store_true", help="Show the per-cohort and per-event breakdown behind the score")
    parser.add_argument("--by-hour", action="store_true", dest="by_hour", help="Score each of the last --hours clock hours separately instead of as one window")
    return parser.parse_args(argv)


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


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.hours < 1:
        print("--hours must be at least 1", file=sys.stderr)
        return 1

    if not (token := resolve_token(args.openlibrary_config)):
        print(
            f"No Matomo token found. Set `matomo_api` in {args.openlibrary_config}, or export MATOMO_TOKEN.",
            file=sys.stderr,
        )
        return 1

    hourly: list[dict] | None = None
    # The window to record: the most recent *complete* hour under --by-hour.
    # hourly[0] is the hour in progress, so recording it would write a value that
    # depends on the minute the job fired -- a sawtooth, not a measurement.
    recordable: dict | None = None
    try:
        if args.by_hour:
            hourly = gather_retention_scores_by_hour(token, hours=args.hours)
            recordable = next((hour for hour in hourly if not hour["partial"]), None)
        else:
            recordable = gather_retention_scores(token, hours=args.hours)
    except MatomoError as exc:
        print(f"Could not reach Matomo: {exc}", file=sys.stderr)
        print("Matomo is restricted to IA's network; set HTTPS_PROXY to an allowlisted proxy if running locally.", file=sys.stderr)
        return 1

    if args.as_json:
        print(json.dumps(hourly if hourly is not None else recordable, indent=2))
    elif hourly is not None:
        print_hourly_report(hourly, args.verbose)
    elif recordable is not None:
        print_report(recordable, args.verbose)

    if args.statsd:
        if recordable is None:
            print("\nNothing recorded: --by-hour --hours 1 covers only the hour in progress. Use --hours 2 or more.", file=sys.stderr)
            return 1
        write_retention_to_statsd(args.openlibrary_config, recordable)
        print(f"\nPushed {len(retention_gauges(recordable))} gauges to statsd for the hour starting {recordable.get('hour_start', recordable['since'])}.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
