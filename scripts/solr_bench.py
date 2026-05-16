#!/usr/bin/env python3
"""
Fast Solr benchmark for Open Library — no subprocess spawning, HTTP keep-alive,
proper statistics, cache stats, and JVM metrics.

Usage:
    python3 scripts/solr_bench.py [--label LABEL] [--solr URL] [--concurrency N]
    python3 scripts/solr_bench.py --label baseline --concurrency 4
    python3 scripts/solr_bench.py --label exp1 --results-dir scripts/solr_perf_results

Designed to be run from inside Docker for accurate timing:
    docker compose -f compose.yaml -f compose.solr-perf.yaml run --rm \\
        -v ./scripts:/openlibrary/scripts \\
        home python3 scripts/solr_bench.py --label baseline --concurrency 4
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import threading
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from statistics import mean, median
from typing import Any


SOLR = os.environ.get("SOLR", "http://localhost:8983/solr/openlibrary")

# Representative Open Library query patterns — mirrors real search/browse paths
QUERIES: dict[str, str] = {
    # Full-text + facets: the most common pattern (homepage search box)
    "fulltext_faceted": (
        "q=harry+potter&fq=type:work&rows=20"
        "&facet=true&facet.field=author_facet&facet.field=language"
        "&facet.field=subject_facet&facet.field=first_publish_year&wt=json"
    ),
    # Author page: sorts by edition_count (non-score) — key test for useFilterForSortedQuery
    "author_sorted": (
        "q=*:*&fq=type:work&fq=author_key:OL2162284A"
        "&sort=edition_count+desc&rows=20"
        "&facet=true&facet.field=subject_facet&wt=json"
    ),
    # Ebook-only browse: heavy fq filter, common for borrowable-books feature
    "ebook_access": (
        "q=*:*&fq=type:work&fq=ebook_access:%5Bprintdisabled+TO+*%5D"
        "&rows=20&facet=true&facet.field=language&wt=json"
    ),
    # Language filter: enum-like fq, should be filterCache-friendly
    "lang_filter": (
        "q=*:*&fq=type:work&fq=language:fre"
        "&sort=edition_count+desc&rows=20&wt=json"
    ),
    # Two combined fq filters: exercises filterCache intersection
    "multi_filter": (
        "q=*:*&fq=type:work&fq=language:spa"
        "&fq=ebook_access:%5Bprintdisabled+TO+*%5D&rows=20&wt=json"
    ),
    # Page 2 of results: cache hit only if queryResultWindowSize >= 40
    "paginate_p2": (
        "q=harry+potter&fq=type:work&rows=20&start=20&wt=json"
    ),
    # Page 5 of results: cache hit only if queryResultWindowSize >= 100
    "paginate_p5": (
        "q=harry+potter&fq=type:work&rows=20&start=80&wt=json"
    ),
    # Subject search: different query shape, different cache slots
    "subject_search": (
        "q=subject:mystery&fq=type:work&rows=20"
        "&facet=true&facet.field=author_facet&wt=json"
    ),
    # Author page sorted by date — exercises useFilterForSortedQuery (no score sort)
    "author_page_date": (
        "q=*:*&fq=type:work&fq=author_key:OL2162284A"
        "&sort=first_publish_year+desc&rows=20&wt=json"
    ),
    # Boosted search — runs boost function on every matching doc (full OL edismax pattern)
    "boosted_search": (
        "q=lord+of+the+rings&fq=type:work&defType=edismax"
        "&qf=title+author_name+subject"
        "&bf=sum(mul(20,log(sum(3,edition_count))),min(50,def(already_read_count,0)),mul(35,log(div(sum(4,def(readinglog_count,0)),4))))"
        "&rows=100&wt=json"
    ),
    # Spellcheck enabled (default OL production behavior): count=10 adds overhead
    "search_spellcheck_on": (
        "q=mistakn+speling&fq=type:work&rows=20"
        "&spellcheck=true&spellcheck.count=10&wt=json"
    ),
    # Spellcheck disabled: compare to measure spellcheck overhead
    "search_spellcheck_off": (
        "q=mistakn+speling&fq=type:work&rows=20"
        "&spellcheck=false&wt=json"
    ),
}

# Diverse queries for cache pressure testing (drives filterCache evictions)
DIVERSE_QUERIES: list[str] = [
    f"q=*:*&fq=type:work&fq=language:{lang}&rows=20&wt=json"
    for lang in ["eng", "fre", "ger", "spa", "ita", "rus", "por", "pol", "nld",
                 "chi", "jpn", "ara", "swe", "nor", "dan", "fin", "hun", "ces"]
] + [
    "q=history&fq=type:work&rows=20&wt=json",
    "q=science&fq=type:work&rows=20&wt=json",
    "q=fiction&fq=type:work&rows=20&wt=json",
    "q=biography&fq=type:work&rows=20&wt=json",
    "q=mystery&fq=type:work&rows=20&wt=json",
    "q=romance&fq=type:work&rows=20&wt=json",
    "q=poetry&fq=type:work&rows=20&wt=json",
    "q=philosophy&fq=type:work&rows=20&wt=json",
    "q=*:*&fq=type:work&fq=ebook_access:borrowable&rows=20&wt=json",
    "q=*:*&fq=type:work&fq=ebook_access:public&rows=20&wt=json",
    "q=*:*&fq=type:work&sort=edition_count+desc&rows=20&wt=json",
    "q=*:*&fq=type:work&sort=first_publish_year+desc&rows=20&wt=json",
]


def fetch(url: str, timeout: int = 10, body: bytes | None = None) -> dict[str, Any]:
    req = urllib.request.Request(url, data=body, method="POST" if body else "GET")
    if body:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def warmup(solr: str, rounds: int = 10) -> None:
    """Run warmup queries to populate caches before measurement."""
    for _ in range(rounds):
        for q in QUERIES.values():
            try:
                fetch(f"{solr}/select?{q}")
            except Exception:
                pass


def measure_sequential(solr: str, rounds: int = 30) -> dict[str, list[int]]:
    """Return {query_name: [QTime_ms, ...]} for each query pattern."""
    results: dict[str, list[int]] = {name: [] for name in QUERIES}
    for _ in range(rounds):
        for name, q in QUERIES.items():
            try:
                d = fetch(f"{solr}/select?{q}")
                results[name].append(d["responseHeader"]["QTime"])
            except Exception:
                results[name].append(-1)
    return results


def measure_concurrent(solr: str, workers: int, duration: int = 30) -> dict[str, Any]:
    """Run concurrent load test, return throughput and latency stats."""
    stop_at = time.time() + duration
    all_times: list[int] = []
    errors = 0
    lock = threading.Lock()

    q_list = list(QUERIES.values()) + DIVERSE_QUERIES

    def worker(wid: int) -> None:
        nonlocal errors
        local_times: list[int] = []
        i = wid
        while time.time() < stop_at:
            q = q_list[i % len(q_list)]
            try:
                d = fetch(f"{solr}/select?{q}")
                local_times.append(d["responseHeader"]["QTime"])
            except Exception:
                with lock:
                    errors += 1
            i += 1
        with lock:
            all_times.extend(local_times)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    s = sorted(all_times)
    n = len(s)
    if not n:
        return {"requests": 0, "errors": errors, "rps": 0.0}
    return {
        "requests": n,
        "errors": errors,
        "rps": n / duration,
        "avg": mean(s),
        "p50": s[n // 2],
        "p75": s[int(n * 0.75)],
        "p90": s[int(n * 0.90)],
        "p99": s[int(n * 0.99)],
        "max": max(s),
    }


def get_cache_stats(solr: str) -> dict[str, dict[str, Any]]:
    """Fetch cache statistics from Solr MBeans.

    Solr 9 MBeans structure:
      {"solr-mbeans": ["CACHE", {"filterCache": {...}, "queryResultCache": {...}, ...}]}
    Stats keys are prefixed: "CACHE.searcher.filterCache.hits", etc.
    """
    url = f"{solr}/admin/mbeans?stats=true&cat=CACHE&wt=json"
    try:
        d = fetch(url)
    except Exception:
        return {}
    beans = d.get("solr-mbeans", [])
    result: dict[str, dict[str, Any]] = {}

    # Solr 9: alternating [category_string, {cache_name: {stats}, ...}, ...]
    cache_names = ("filterCache", "queryResultCache", "documentCache", "fieldValueCache")
    for i in range(0, len(beans) - 1, 2):
        if not isinstance(beans[i], str) or not isinstance(beans[i + 1], dict):
            continue
        for cname in cache_names:
            if cname not in beans[i + 1]:
                continue
            cdata = beans[i + 1][cname]
            # Solr 9: stats are in a nested "stats" sub-dict, with prefixed keys
            # like "CACHE.searcher.filterCache.hits"
            prefix = f"CACHE.searcher.{cname}."
            s: dict[str, Any] = {}
            raw_stats = cdata.get("stats", cdata) if isinstance(cdata, dict) else {}
            for k, v in raw_stats.items():
                short = k[len(prefix):] if k.startswith(prefix) else k
                s[short] = v
            result[cname] = {
                "hitRatio": float(s.get("hitratio", s.get("cumulative_hitratio", 0))),
                "evictions": int(s.get("cumulative_evictions", s.get("evictions", 0))),
                "size": int(s.get("size", 0)),
                "lookups": int(s.get("cumulative_lookups", s.get("lookups", 0))),
                "inserts": int(s.get("cumulative_inserts", s.get("inserts", 0))),
            }
    return result


def get_jvm_stats(solr: str) -> dict[str, Any]:
    """Fetch JVM heap and GC stats.

    The metrics endpoint is at the Solr instance level, not the core level.
    If solr = http://host:8983/solr/openlibrary, the metrics URL is
    http://host:8983/solr/admin/metrics (strip the core name).
    """
    # Strip core path to get instance-level endpoint
    base = solr.rstrip("/")
    # e.g. http://solr:8983/solr/openlibrary -> http://solr:8983/solr
    parts = base.rsplit("/", 1)
    instance_url = parts[0] if len(parts) > 1 else base
    url = f"{instance_url}/admin/metrics?group=jvm&wt=json"
    try:
        d = fetch(url)
    except Exception:
        return {}
    m = d.get("metrics", {}).get("solr.jvm", {})
    heap_used = m.get("memory.heap.used", 0) / 1e9
    heap_max = m.get("memory.heap.max", 0) / 1e9
    pct = (heap_used / heap_max * 100) if heap_max else 0
    yc = m.get("gc.G1-Young-Generation.count", m.get("gc.ZGC-Cycles.count", 0))
    yt = m.get("gc.G1-Young-Generation.time", m.get("gc.ZGC-Cycles.time", 0))
    oc = m.get("gc.G1-Old-Generation.count", m.get("gc.ZGC-Pauses.count", 0))
    ot = m.get("gc.G1-Old-Generation.time", m.get("gc.ZGC-Pauses.time", 0))
    return {
        "heap_used_gb": heap_used,
        "heap_max_gb": heap_max,
        "heap_pct": pct,
        "gc_young_count": int(yc),
        "gc_young_ms": int(yt),
        "gc_old_count": int(oc),
        "gc_old_ms": int(ot),
    }


def measure_readinglog(solr: str, counts: list[int] = None, rounds: int = 5) -> dict[str, dict[str, Any]]:
    """
    Benchmark the reading-log OR-clause query pattern at increasing key counts.

    This is the hot path in bookshelves.py that constructs:
        fq=key:("/works/OL1W" OR "/works/OL2W" OR ...)

    The fix replaces it with:
        fq={!terms f=key}/works/OL1W,/works/OL2W,...

    Both are tested here so the improvement is measurable even at small local index sizes.
    The URL is sent as a POST to avoid HTTP GET query-string length limits.
    """
    if counts is None:
        counts = [100, 1000, 5000, 10000]

    results: dict[str, dict[str, Any]] = {}
    base_url = f"{solr}/select"

    for n in counts:
        keys = [f"/works/OL{i}W" for i in range(1, n + 1)]

        # --- BooleanQuery (current production pattern) ---
        or_fq = "key:(%s)" % " OR ".join(f'"{k}"' for k in keys)
        or_body = urllib.parse.urlencode({
            "q": "*:*",
            "fq": ["type:work", or_fq],
            "rows": "0",
            "wt": "json",
        }, doseq=True).encode()

        # --- TermsQuery (proposed fix) ---
        terms_fq = "{!terms f=key}" + ",".join(keys)
        terms_body = urllib.parse.urlencode({
            "q": "*:*",
            "fq": ["type:work", terms_fq],
            "rows": "0",
            "wt": "json",
        }, doseq=True).encode()

        or_times: list[int] = []
        terms_times: list[int] = []

        for _ in range(rounds):
            try:
                d = fetch(base_url, body=or_body)
                or_times.append(d["responseHeader"]["QTime"])
            except Exception:
                or_times.append(-1)
            try:
                d = fetch(base_url, body=terms_body)
                terms_times.append(d["responseHeader"]["QTime"])
            except Exception:
                terms_times.append(-1)

        def _stats(times: list[int]) -> dict[str, Any]:
            valid = sorted(t for t in times if t >= 0)
            if not valid:
                return {"p50": -1, "p90": -1, "avg": -1}
            n_ = len(valid)
            return {
                "p50": valid[n_ // 2],
                "p90": valid[int(n_ * 0.9)],
                "avg": round(mean(valid), 1),
                "raw": valid,
            }

        results[f"or_{n}"] = _stats(or_times)
        results[f"terms_{n}"] = _stats(terms_times)

    return results


def print_readinglog_results(rl: dict[str, dict[str, Any]]) -> None:
    print()
    print("-- Reading Log Query Pattern: BooleanQuery vs TermsQuery --")
    print(f"  {'N keys':<10} {'OR p50':>8} {'OR p90':>8} {'terms p50':>10} {'terms p90':>10} {'speedup':>8}")
    print("  " + "-" * 60)
    counts = sorted({int(k.split("_")[1]) for k in rl})
    for n in counts:
        or_ = rl.get(f"or_{n}", {})
        terms_ = rl.get(f"terms_{n}", {})
        or_p90 = or_.get("p90", -1)
        terms_p90 = terms_.get("p90", -1)
        if or_p90 > 0 and terms_p90 > 0:
            speedup = f"{or_p90 / terms_p90:.1f}x" if terms_p90 > 0 else "N/A"
        else:
            speedup = "N/A"
        print(
            f"  {n:<10} {or_.get('p50',-1):>7}ms {or_p90:>7}ms"
            f" {terms_.get('p50',-1):>9}ms {terms_p90:>9}ms {speedup:>8}"
        )
    print("  (values are Solr QTime; negative = error)")


def print_results(
    label: str,
    seq: dict[str, list[int]],
    conc: dict[str, Any],
    caches: dict[str, dict[str, Any]],
    jvm: dict[str, Any],
) -> None:
    print(f"\n=== {label} | {time.strftime('%Y-%m-%dT%H:%M:%S')} ===")
    print()
    print("-- Sequential QTime (warmup=10, measure=30) --")
    for name, times in sorted(seq.items()):
        valid = [t for t in times if t >= 0]
        if not valid:
            print(f"  {name:<25} (no data)")
            continue
        s = sorted(valid)
        n = len(s)
        p50 = s[n // 2]
        p90 = s[int(n * 0.9)]
        avg = mean(s)
        print(f"  {name:<25} avg={avg:6.1f}ms  p50={p50:4d}ms  p90={p90:4d}ms  max={max(s):4d}ms")

    print()
    print("-- Cache Stats --")
    for cname, stats in sorted(caches.items()):
        print(
            f"  {cname:<20} hitRatio={stats['hitRatio']:.3f}"
            f"  evictions={stats['evictions']:8,}"
            f"  sz={stats['size']:5,}"
            f"  lookups={stats['lookups']:8,}"
            f"  inserts={stats['inserts']:6,}"
        )
    if not caches:
        print("  (cache stats unavailable)")

    print()
    print("-- JVM Memory & GC --")
    if jvm:
        print(f"  Heap: {jvm['heap_used_gb']:.2f}GB used / {jvm['heap_max_gb']:.2f}GB max  ({jvm['heap_pct']:.1f}%)")
        print(f"  GC Young: count={jvm['gc_young_count']}  time={jvm['gc_young_ms']}ms")
        print(f"  GC Major: count={jvm['gc_old_count']}  time={jvm['gc_old_ms']}ms  <- heap pressure indicator")
    else:
        print("  (JVM metrics unavailable)")

    if conc:
        n = conc.get("requests", 0)
        if n:
            print()
            print(f"-- Concurrent Load: workers={conc.get('_workers','?')} x {conc.get('_duration','?')}s --")
            print(f"  {n} requests, {conc.get('errors',0)} errors => {conc['rps']:.1f} req/s")
            print(
                f"  QTime: avg={conc['avg']:.1f}ms  p50={conc['p50']}ms"
                f"  p90={conc['p90']}ms  p99={conc['p99']}ms  max={conc['max']}ms"
            )

    print(f"\n=== done: {label} ===")


def save_json(path: str, data: dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fast Solr benchmark for Open Library")
    parser.add_argument("--label", default="baseline", help="Label for this run")
    parser.add_argument("--solr", default=SOLR, help="Solr base URL")
    parser.add_argument("--concurrency", type=int, default=1, help="Concurrent workers (0=skip)")
    parser.add_argument("--warmup", type=int, default=10, help="Warmup rounds per query")
    parser.add_argument("--rounds", type=int, default=30, help="Measurement rounds per query")
    parser.add_argument("--duration", type=int, default=30, help="Concurrent test duration (seconds)")
    parser.add_argument("--results-dir", default="scripts/solr_perf_results", help="Output directory")
    parser.add_argument("--readinglog", action="store_true", help="Run reading-log OR vs TermsQuery benchmark")
    parser.add_argument(
        "--readinglog-counts",
        default="100,1000,5000,10000",
        help="Comma-separated key counts for readinglog benchmark (default: 100,1000,5000,10000)",
    )
    args = parser.parse_args()

    solr = args.solr.rstrip("/")

    print(f"Connecting to Solr: {solr}")
    # Quick connectivity check
    try:
        info = fetch(f"{solr}/admin/ping?wt=json")
        print(f"Solr status: {info.get('status', 'unknown')}")
    except Exception as e:
        print(f"ERROR: Cannot connect to Solr at {solr}: {e}")
        sys.exit(1)

    print(f"Warming up ({args.warmup} rounds per query)...")
    warmup(solr, args.warmup)

    print(f"Measuring ({args.rounds} rounds per query)...")
    seq_results = measure_sequential(solr, args.rounds)

    print("Collecting cache stats...")
    cache_stats = get_cache_stats(solr)

    print("Collecting JVM stats...")
    jvm_stats = get_jvm_stats(solr)

    conc_results: dict[str, Any] = {}
    if args.concurrency > 1:
        print(f"Running concurrent load test ({args.concurrency} workers x {args.duration}s)...")
        conc_results = measure_concurrent(solr, args.concurrency, args.duration)
        conc_results["_workers"] = args.concurrency
        conc_results["_duration"] = args.duration

    rl_results: dict[str, dict] = {}
    if args.readinglog:
        counts = [int(x) for x in args.readinglog_counts.split(",")]
        print(f"Running reading-log benchmark (counts={counts}, rounds=5)...")
        rl_results = measure_readinglog(solr, counts=counts)
        print_readinglog_results(rl_results)

    print_results(args.label, seq_results, conc_results, cache_stats, jvm_stats)

    # Save structured results for comparison scripts
    out_path = f"{args.results_dir}/{args.label}.json"
    save_json(out_path, {
        "label": args.label,
        "solr": solr,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "sequential": {name: times for name, times in seq_results.items()},
        "concurrent": conc_results,
        "caches": cache_stats,
        "jvm": jvm_stats,
        "readinglog": rl_results,
    })
    print(f"\nResults saved to: {out_path}")


if __name__ == "__main__":
    main()
