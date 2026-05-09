#!/usr/bin/env python3
"""
Compare two Solr benchmark runs and decide whether to keep a config change.

Usage:
    python3 scripts/solr_compare_runs.py baseline.json experiment.json
    python3 scripts/solr_compare_runs.py scripts/solr_perf_results/baseline.json \\
                                         scripts/solr_perf_results/exp1.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean, median


def load(path: str) -> dict:
    return json.loads(Path(path).read_text())


def p50(times: list[int]) -> int:
    valid = sorted(t for t in times if t >= 0)
    if not valid:
        return 0
    return valid[len(valid) // 2]


def p90(times: list[int]) -> int:
    valid = sorted(t for t in times if t >= 0)
    if not valid:
        return 0
    return valid[int(len(valid) * 0.9)]


def avg(times: list[int]) -> float:
    valid = [t for t in times if t >= 0]
    return mean(valid) if valid else 0.0


def compare(baseline: dict, candidate: dict) -> tuple[bool, bool]:
    """
    Returns (is_improvement, has_regression).
    Improvement: any query gets meaningfully faster (>5% p90) with no regressions.
    Regression: any query gets meaningfully slower (>10% p90).
    """
    b_seq = baseline.get("sequential", {})
    c_seq = candidate.get("sequential", {})

    improvements = 0
    regressions = 0

    print(f"\n{'Query':<25} {'Baseline p50':>12} {'Exp p50':>10} {'Δ':>7}  {'Baseline p90':>12} {'Exp p90':>10} {'Δ':>7}  {'Verdict'}")
    print("-" * 110)

    for name in sorted(b_seq.keys()):
        if name not in c_seq:
            continue
        b50 = p50(b_seq[name])
        c50 = p50(c_seq[name])
        b90 = p90(b_seq[name])
        c90 = p90(c_seq[name])
        if b90 == 0:
            continue
        d90 = (b90 - c90) / b90 * 100  # positive = improvement
        d50 = (b50 - c50) / b50 * 100 if b50 > 0 else 0

        # Require both relative AND absolute delta to count; avoids false
        # positives at sub-5ms resolution (1ms→2ms = "100%" but is just noise).
        abs_delta_ms = b90 - c90  # positive = improvement
        if d90 > 10 and abs_delta_ms >= 5:
            verdict = "IMPROVE ✓"
            improvements += 1
        elif d90 < -10 and abs_delta_ms <= -5:
            verdict = "REGRESS ✗"
            regressions += 1
        else:
            verdict = "~same"

        d90_str = f"{d90:+.0f}%"
        d50_str = f"{d50:+.0f}%"
        print(f"  {name:<23} {b50:>10}ms {c50:>10}ms {d50_str:>7}  {b90:>10}ms {c90:>10}ms {d90_str:>7}  {verdict}")

    # Cache stats
    b_cache = baseline.get("caches", {})
    c_cache = candidate.get("caches", {})
    if b_cache and c_cache:
        print()
        print(f"  {'Cache':<20} {'Baseline hitRatio':>17} {'Exp hitRatio':>12} {'Δ':>6}  {'Baseline evictions':>18} {'Exp evictions':>13}")
        print("  " + "-" * 90)
        for cname in sorted(b_cache.keys()):
            if cname not in c_cache:
                continue
            bhr = b_cache[cname]["hitRatio"]
            chr_ = c_cache[cname]["hitRatio"]
            bev = b_cache[cname]["evictions"]
            cev = c_cache[cname]["evictions"]
            dhr = (chr_ - bhr) * 100
            dev = ((bev - cev) / bev * 100) if bev > 0 else 0
            print(f"  {cname:<20} {bhr:>15.3f} {chr_:>14.3f} {dhr:>+6.2f}%  {bev:>16,} {cev:>14,}")

    # JVM stats
    b_jvm = baseline.get("jvm", {})
    c_jvm = candidate.get("jvm", {})
    if b_jvm and c_jvm:
        print()
        print("  JVM:")
        print(f"    Heap: {b_jvm.get('heap_pct',0):.1f}% → {c_jvm.get('heap_pct',0):.1f}%")
        print(f"    GC Major count: {b_jvm.get('gc_old_count',0)} → {c_jvm.get('gc_old_count',0)}")
        print(f"    GC Major time:  {b_jvm.get('gc_old_ms',0)}ms → {c_jvm.get('gc_old_ms',0)}ms")

    # Concurrent throughput
    b_conc = baseline.get("concurrent", {})
    c_conc = candidate.get("concurrent", {})
    if b_conc.get("rps") and c_conc.get("rps"):
        brps = b_conc["rps"]
        crps = c_conc["rps"]
        drps = (crps - brps) / brps * 100
        print()
        print(f"  Concurrent req/s: {brps:.1f} → {crps:.1f} ({drps:+.1f}%)")
        if c_conc.get("p99") and b_conc.get("p99"):
            bp99 = b_conc["p99"]
            cp99 = c_conc["p99"]
            dp99 = (bp99 - cp99) / bp99 * 100
            print(f"  Concurrent p99: {bp99}ms → {cp99}ms ({dp99:+.0f}%)")

    print()
    print(f"Summary: {improvements} improvements, {regressions} regressions across {len(b_seq)} queries")

    is_improvement = improvements > 0 and regressions == 0
    has_regression = regressions > 0
    return is_improvement, has_regression


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python3 solr_compare_runs.py baseline.json candidate.json")
        sys.exit(1)

    baseline = load(sys.argv[1])
    candidate = load(sys.argv[2])

    print(f"Comparing:")
    print(f"  Baseline:  {baseline.get('label', '?')} @ {baseline.get('timestamp', '?')}")
    print(f"  Candidate: {candidate.get('label', '?')} @ {candidate.get('timestamp', '?')}")

    is_improvement, has_regression = compare(baseline, candidate)

    if has_regression:
        print("\n>>> VERDICT: REVERT — regression detected")
        sys.exit(2)
    elif is_improvement:
        print("\n>>> VERDICT: KEEP — improvement with no regressions")
        sys.exit(0)
    else:
        print("\n>>> VERDICT: NEUTRAL — no significant change (keep if it adds stability)")
        sys.exit(1)


if __name__ == "__main__":
    main()
