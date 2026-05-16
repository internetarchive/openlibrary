#!/usr/bin/env python3
"""
Replay Solr query logs against a target instance and compare latency.

Two modes:

  Log replay (default):
    Parse production Solr logs, replay replayable queries against a Solr
    instance, and report p50/p99 latency compared to the log-recorded QTime.

    python scripts/replay_solr_log.py ../solr/solr.log [options]
    python scripts/replay_solr_log.py ../solr/solr.log.{1..9} --slow-only 1000
    python scripts/replay_solr_log.py ../solr/solr.log --label BOOK_SEARCH_FACETS --json

  Cursor test:
    Compare cursor-based vs offset-based pagination latency against the OL
    /search.json API.  Most meaningful against production (read-only).

    python scripts/replay_solr_log.py --cursor-test \\
        --ol-url https://openlibrary.org \\
        --cursor-query "language:rus" --cursor-pages 20

Note: ~64% of production queries use an internal Solr template format
(EDITION_MATCH batch queries) that cannot be replayed without the OL Solr
plugin context.  These are silently skipped; the remaining 36% covers all
user-facing labels (BOOK_SEARCH_API, BOOK_SEARCH_FACETS, BOOK_CAROUSEL, etc.).
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode
from urllib.request import urlopen

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class QueryEvent:
    path: str                     # "/select" or "/get"
    params: dict[str, list[str]]  # parse_qs output — multi-value keys preserved
    label: str                    # ol.label value from params
    baseline_ms: int              # QTime from the log line


@dataclass
class ReplayResult:
    label: str
    baseline_ms: int
    replay_ms: int | None         # None = HTTP error or timeout


# ---------------------------------------------------------------------------
# Log parsing
# ---------------------------------------------------------------------------

_PATH_RE = re.compile(r"path=(/\S+) params=")
_STATUS_RE = re.compile(r"status=(\d+) QTime=(\d+)")


def _extract_params_block(line: str) -> str | None:
    """
    Extract the inner content of the params={...} block using brace counting.

    Needed because param values may contain nested {!local-params} Solr syntax,
    so a simple closing-brace regex would terminate too early.
    """
    idx = line.find("params=")
    if idx == -1:
        return None
    start = idx + 7  # len("params=")
    if start >= len(line) or line[start] != "{":
        return None
    depth = 0
    for i in range(start, len(line)):
        if line[i] == "{":
            depth += 1
        elif line[i] == "}":
            depth -= 1
            if depth == 0:
                return line[start + 1 : i]
    return None


def _parse_line(line: str) -> QueryEvent | None:
    """Parse one Solr log line, or return None if the query is not replayable."""
    path_m = _PATH_RE.search(line)
    status_m = _STATUS_RE.search(line)
    if not path_m or not status_m:
        return None
    if status_m.group(1) != "0":
        return None  # skip error responses

    raw = _extract_params_block(line)
    if raw is None:
        return None

    # Double-brace template format: {{params(version=2&wt=javabin),defaults({...})}}
    # After outer-brace stripping, raw starts with "{params(" — these are
    # EDITION_MATCH batch queries that use the OL Solr plugin and cannot be
    # replayed stand-alone.
    if raw.startswith(("{params(", "params(")):
        return None

    params = parse_qs(raw, keep_blank_values=True)
    label = params.get("ol.label", ["UNLABELLED"])[0]
    return QueryEvent(
        path=path_m.group(1),
        params=params,
        label=label,
        baseline_ms=int(status_m.group(2)),
    )


def parse_log_files(
    paths: list[str],
    labels: set[str] | None = None,
    min_qtime: int = 0,
    sample: float = 1.0,
) -> tuple[list[QueryEvent], dict[str, int], int]:
    """
    Parse Solr log files and return (events, skipped_counts, total_request_lines).

    skipped_counts keys: "non-replayable", "label:<LABEL>", "below-min-qtime",
    "sampled-out".
    """
    events: list[QueryEvent] = []
    skipped: dict[str, int] = {}
    total_request_lines = 0

    for path in paths:
        text = Path(path).read_text(errors="replace")
        for line in text.splitlines():
            if "o.a.s.c.S.Request" not in line:
                continue
            total_request_lines += 1

            event = _parse_line(line)
            if event is None:
                skipped["non-replayable"] = skipped.get("non-replayable", 0) + 1
                continue
            if labels and event.label not in labels:
                key = f"label:{event.label}"
                skipped[key] = skipped.get(key, 0) + 1
                continue
            if event.baseline_ms < min_qtime:
                skipped["below-min-qtime"] = skipped.get("below-min-qtime", 0) + 1
                continue
            if sample < 1.0 and random.random() >= sample:
                skipped["sampled-out"] = skipped.get("sampled-out", 0) + 1
                continue

            events.append(event)

    return events, skipped, total_request_lines


# ---------------------------------------------------------------------------
# Replay engine
# ---------------------------------------------------------------------------


def _replay_one(event: QueryEvent, solr_url: str, timeout: int) -> int | None:
    """Send one query to Solr and return QTime from the response, or None on error."""
    p = dict(event.params)
    p["wt"] = ["json"]  # override javabin — we need JSON to read QTime
    url = f"{solr_url}{event.path}?{urlencode(p, doseq=True)}"
    try:
        with urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return int(data["responseHeader"]["QTime"])
    except (OSError, ValueError, KeyError):
        return None


def replay_events(
    events: list[QueryEvent],
    solr_url: str,
    concurrency: int,
    warmup: int,
    timeout: int,
) -> list[ReplayResult]:
    """
    Replay events against Solr.

    The first `warmup` events are sent sequentially to warm Solr's internal
    caches; their latencies are excluded from results.  The remaining events
    are sent with up to `concurrency` parallel workers.
    """
    if warmup > 0:
        warmup_events = events[:warmup]
        measure_events = events[warmup:]
        print(f"  Warming up: sending {min(warmup, len(events))} queries sequentially...", end=" ", flush=True)
        for evt in warmup_events:
            _replay_one(evt, solr_url, timeout)
        print("done")
    else:
        measure_events = events

    if not measure_events:
        return []

    print(f"  Measuring: {len(measure_events)} queries with {concurrency} workers...", end=" ", flush=True)
    results: list[ReplayResult] = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [(evt, pool.submit(_replay_one, evt, solr_url, timeout)) for evt in measure_events]
        for evt, fut in futures:
            results.append(ReplayResult(evt.label, evt.baseline_ms, fut.result()))
    print("done")
    return results


# ---------------------------------------------------------------------------
# Statistics and reporting
# ---------------------------------------------------------------------------


def _pct(values: list[int], p: float) -> int:
    if not values:
        return 0
    s = sorted(values)
    return s[min(int(len(s) * p / 100), len(s) - 1)]


def _delta(baseline: int, replay: int) -> str:
    if baseline == 0:
        return "  n/a"
    pct = (replay - baseline) / baseline * 100
    return f"{pct:+.0f}%"


def report(
    results: list[ReplayResult],
    skipped: dict[str, int],
    total_request_lines: int,
    solr_url: str,
    warmup: int,
    concurrency: int,
) -> None:
    by_label: dict[str, list[ReplayResult]] = {}
    for r in results:
        by_label.setdefault(r.label, []).append(r)

    non_replayable = skipped.get("non-replayable", 0)
    print(f"\nReplayed {len(results):,} queries ({non_replayable:,} non-replayable skipped) "
          f"from {total_request_lines:,} log lines")
    print(f"Warmup: {warmup}  |  Concurrency: {concurrency}  |  Target: {solr_url}\n")

    col_w = 22
    header = (
        f"{'Label':<{col_w}} {'Count':>7}  {'Log p50':>8}  {'Replay p50':>10}  {'Δ':>5}  "
        f"{'Log p99':>8}  {'Replay p99':>10}  {'Δ':>5}"
    )
    print(header)
    print("─" * len(header))

    all_baseline: list[int] = []
    all_replay: list[int] = []

    for label in sorted(by_label, key=lambda lbl: -len(by_label[lbl])):
        rs = by_label[label]
        baseline_vals = [r.baseline_ms for r in rs]
        replay_vals = [r.replay_ms for r in rs if r.replay_ms is not None]
        errors = sum(1 for r in rs if r.replay_ms is None)
        all_baseline.extend(baseline_vals)
        all_replay.extend(replay_vals)

        b50, r50 = _pct(baseline_vals, 50), _pct(replay_vals, 50)
        b99, r99 = _pct(baseline_vals, 99), _pct(replay_vals, 99)
        flag = " ✓" if b99 > 0 and r99 < b99 * 0.5 else ""
        err_note = f"  ({errors} err)" if errors else ""

        print(
            f"{label:<{col_w}} {len(rs):>7}  {b50:>7}ms  {r50:>9}ms  {_delta(b50, r50):>5}  "
            f"{b99:>7}ms  {r99:>9}ms  {_delta(b99, r99):>5}{flag}{err_note}"
        )

    print("─" * len(header))
    total_errors = sum(1 for r in results if r.replay_ms is None)
    tb50, tr50 = _pct(all_baseline, 50), _pct(all_replay, 50)
    tb99, tr99 = _pct(all_baseline, 99), _pct(all_replay, 99)
    print(
        f"{'Total':<{col_w}} {len(results):>7}  {tb50:>7}ms  {tr50:>9}ms  {_delta(tb50, tr50):>5}  "
        f"{tb99:>7}ms  {tr99:>9}ms  {_delta(tb99, tr99):>5}"
    )
    err_pct = total_errors / len(results) * 100 if results else 0
    print(f"Errors: {total_errors} ({err_pct:.1f}%)")
    print()
    print("✓ = >50% improvement at p99")
    print("⚠ Dev index is much smaller than production; absolute ms values will be lower.")
    print("  Use Δ (relative change) for cross-run comparison of the same Solr instance.")


def report_dry_run(events: list[QueryEvent], skipped: dict[str, int], total_lines: int) -> None:
    """Report parse statistics without replaying."""
    by_label: dict[str, list[int]] = {}
    for e in events:
        by_label.setdefault(e.label, []).append(e.baseline_ms)

    non_replayable = skipped.get("non-replayable", 0)
    print(f"\nParsed {total_lines:,} request log lines:")
    print(f"  Non-replayable (template format): {non_replayable:,}")
    print(f"  Would replay:                     {len(events):,}")
    if skipped:
        for k, v in sorted(skipped.items()):
            if k != "non-replayable":
                print(f"  Skipped ({k}): {v:,}")
    print()
    print(f"{'Label':<25} {'Count':>7}  {'Log p50':>8}  {'Log p99':>8}  {'Log max':>8}")
    print("─" * 65)
    for label in sorted(by_label, key=lambda lbl: -len(by_label[lbl])):
        vals = by_label[label]
        print(f"{label:<25} {len(vals):>7}  {_pct(vals, 50):>7}ms  {_pct(vals, 99):>7}ms  {max(vals):>7}ms")


def report_json(results: list[ReplayResult]) -> None:
    by_label: dict[str, dict[str, list[int]]] = {}
    for r in results:
        entry = by_label.setdefault(r.label, {"baseline": [], "replay": []})
        entry["baseline"].append(r.baseline_ms)
        if r.replay_ms is not None:
            entry["replay"].append(r.replay_ms)
    print(json.dumps(by_label, indent=2))


# ---------------------------------------------------------------------------
# Cursor vs offset test
# ---------------------------------------------------------------------------


def cursor_test(ol_url: str, query: str, sort: str, limit: int, pages: int) -> None:
    """Compare cursor-based vs offset-based pagination latency against OL /search.json."""
    base = f"{ol_url}/search.json"
    q_enc = quote(query)
    s_enc = quote(sort)

    print("\nCursor vs Offset Benchmark")
    print(f"Query: {query!r}  |  sort: {sort!r}  |  limit: {limit}/page  |  pages: {pages}")
    print(f"Target: {ol_url}\n")
    print(f"{'Page':>5}  {'Offset start':>12}  {'Offset ms':>10}  {'Cursor ms':>10}  {'Ratio':>7}")
    print("─" * 55)

    cursor = "*"
    succeeded = 0
    for page in range(1, pages + 1):
        start = (page - 1) * limit

        # Offset leg
        offset_url = f"{base}?q={q_enc}&sort={s_enc}&offset={start}&limit={limit}"
        t0 = time.monotonic()
        try:
            with urlopen(offset_url, timeout=60) as resp:
                json.loads(resp.read())
            offset_ms = int((time.monotonic() - t0) * 1000)
        except (OSError, ValueError) as e:
            print(f"  page {page}: offset request failed: {e}")
            continue

        # Cursor leg
        cursor_url = f"{base}?q={q_enc}&sort={s_enc}&cursor={quote(cursor)}&limit={limit}"
        t0 = time.monotonic()
        try:
            with urlopen(cursor_url, timeout=60) as resp:
                data = json.loads(resp.read())
            cursor_ms = int((time.monotonic() - t0) * 1000)
            next_cursor = data.get("next_cursor")
            if next_cursor:
                cursor = next_cursor
            else:
                print(f"  page {page}: no next_cursor - result set exhausted")
                break
        except (OSError, ValueError) as e:
            print(f"  page {page}: cursor request failed: {e}")
            continue

        ratio = offset_ms / cursor_ms if cursor_ms > 0 else float("inf")
        print(f"{page:>5}  {start:>12,}  {offset_ms:>10}  {cursor_ms:>10}  {ratio:>7.2f}x")
        succeeded += 1

    print()
    if succeeded:
        print("Ratio grows with offset depth; production shows 50-100x at offset ~374,000.")
    else:
        print("No pages succeeded. Check --ol-url and that the server is reachable.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="replay_solr_log.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("logfiles", nargs="*", metavar="LOGFILE", help="Solr log files to replay")

    rg = p.add_argument_group("Log replay options")
    rg.add_argument(
        "--solr",
        default="http://localhost:8983/solr/openlibrary",
        metavar="URL",
        help="Solr base URL (default: %(default)s)",
    )
    rg.add_argument(
        "--label",
        action="append",
        default=[],
        metavar="LABEL",
        help="Filter by ol.label, e.g. BOOK_SEARCH_API (repeatable)",
    )
    rg.add_argument(
        "--slow-only",
        type=int,
        default=0,
        metavar="MS",
        help="Only replay queries slower than MS ms in the log",
    )
    rg.add_argument(
        "--sample",
        type=float,
        default=1.0,
        metavar="RATE",
        help="Fraction of matched queries to replay, 0.0-1.0 (default: 1.0; use 0 for dry-run parse only)",
    )
    rg.add_argument("--concurrency", type=int, default=8, metavar="N", help="Worker threads (default: 8)")
    rg.add_argument(
        "--warmup",
        type=int,
        default=50,
        metavar="N",
        help="Sequential warmup queries before measurement (default: 50)",
    )
    rg.add_argument("--timeout", type=int, default=30, metavar="S", help="Per-request timeout seconds (default: 30)")
    rg.add_argument(
        "--json",
        action="store_true",
        help="JSON output — dict of {label: {baseline: [...], replay: [...]}}",
    )

    cg = p.add_argument_group("Cursor test mode (replaces log replay — no LOGFILE needed)")
    cg.add_argument("--cursor-test", action="store_true", help="Enable cursor vs offset pagination benchmark")
    cg.add_argument(
        "--ol-url",
        default="http://localhost:8080",
        metavar="URL",
        help="OL base URL for cursor test (default: %(default)s)",
    )
    cg.add_argument(
        "--cursor-query",
        default="language:rus",
        metavar="Q",
        help='Search query for cursor test (default: "%(default)s")',
    )
    cg.add_argument(
        "--cursor-sort",
        default="key asc",
        metavar="S",
        help='Sort clause for cursor test (default: "%(default)s")',
    )
    cg.add_argument("--cursor-limit", type=int, default=100, metavar="N", help="Page size for cursor test (default: 100)")
    cg.add_argument("--cursor-pages", type=int, default=20, metavar="N", help="Pages to compare (default: 20)")

    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.cursor_test:
        cursor_test(args.ol_url, args.cursor_query, args.cursor_sort, args.cursor_limit, args.cursor_pages)
        return

    if not args.logfiles:
        parser.error("Provide at least one LOGFILE, or use --cursor-test")

    labels = set(args.label) if args.label else None
    dry_run = args.sample == 0.0

    print(f"Parsing {len(args.logfiles)} log file(s)...")
    events, skipped, total_lines = parse_log_files(
        args.logfiles,
        labels=labels,
        min_qtime=args.slow_only,
        sample=1.0 if dry_run else args.sample,
    )

    if dry_run:
        report_dry_run(events, skipped, total_lines)
        return

    if not events:
        print("No replayable queries matched the filters. Try relaxing --label / --slow-only.")
        sys.exit(1)

    print(f"Found {len(events):,} replayable queries.")
    results = replay_events(events, args.solr, args.concurrency, args.warmup, args.timeout)

    if args.json:
        report_json(results)
    else:
        report(results, skipped, total_lines, args.solr, args.warmup, args.concurrency)


if __name__ == "__main__":
    main()
