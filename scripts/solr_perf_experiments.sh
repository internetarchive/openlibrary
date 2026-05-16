#!/usr/bin/env bash
# scripts/solr_perf_experiments.sh
#
# Run a structured series of Solr configuration experiments.
# Each experiment modifies solrconfig.xml, reloads the core, benchmarks, then
# compares against the stored baseline.  Only improvements are kept.
#
# Usage:
#   ./scripts/solr_perf_experiments.sh [--concurrency N] [--skip-baseline]
#
# Results are written to scripts/solr_perf_results/ (one file per experiment).
set -euo pipefail

SOLR="http://localhost:8983/solr/openlibrary"
SOLRCONFIG="conf/solr/conf/solrconfig.xml"
RESULTS_DIR="scripts/solr_perf_results"
CONCURRENCY="${CONCURRENCY:-4}"
SKIP_BASELINE="${SKIP_BASELINE:-false}"

mkdir -p "$RESULTS_DIR"

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
reload_core() {
  echo "  [reload] reloading Solr core..."
  curl -s "http://localhost:8983/solr/admin/cores?action=RELOAD&core=openlibrary&wt=json" | \
    python3 -c "import json,sys; r=json.load(sys.stdin); print('  [reload]', 'OK' if r.get('responseHeader',{}).get('status')==0 else 'FAILED')"
  # Allow warmup queries (configured via QuerySenderListener) to settle
  sleep 5
}

run_bench() {
  local label="$1"
  local concurrency="${2:-$CONCURRENCY}"
  bash scripts/solr_benchmark.sh "$label" "$concurrency" | tee "$RESULTS_DIR/$label.txt"
}

extract_metric() {
  # extract_metric <file> <query_name> <metric>  ->  numeric value
  # metric: avg_ms | p50_ms | p90_ms | max_ms | rps | p99_ms
  local file="$1" qname="$2" metric="$3"
  case "$metric" in
    avg_ms) grep "$qname" "$file" 2>/dev/null | grep -oP 'avg=\K[\d.]+' | head -1 ;;
    p50_ms) grep "$qname" "$file" 2>/dev/null | grep -oP 'p50=\K\d+' | head -1 ;;
    p90_ms) grep "$qname" "$file" 2>/dev/null | grep -oP 'p90=\K\d+' | head -1 ;;
    rps)    grep "req/s" "$file" 2>/dev/null | grep -oP '[\d.]+(?= req/s)' | head -1 ;;
    p99_ms) grep "p99=" "$file" 2>/dev/null | grep -oP 'p99=\K\d+' | head -1 ;;
  esac
}

extract_cache() {
  # extract_cache <file> <cache_name> <stat>  ->  value
  # stat: hitRatio | evictions
  local file="$1" cache="$2" stat="$3"
  grep "$cache" "$file" 2>/dev/null | grep -oP "${stat}=\K[\d.]+" | head -1
}

compare_runs() {
  local baseline="$RESULTS_DIR/baseline.txt"
  local candidate="$RESULTS_DIR/$1.txt"
  echo ""
  echo "=== Comparison: $1 vs baseline ==="
  for qname in fulltext_faceted author_sorted ebook_access lang_filter multi_filter paginate_p2 paginate_p5 subject_search; do
    b_p50=$(extract_metric "$baseline" "$qname" p50_ms)
    c_p50=$(extract_metric "$candidate" "$qname" p50_ms)
    b_p90=$(extract_metric "$baseline" "$qname" p90_ms)
    c_p90=$(extract_metric "$candidate" "$qname" p90_ms)
    [ -z "$b_p50" ] && continue
    python3 -c "
b50,c50,b90,c90 = $b_p50,$c_p50,$b_p90,$c_p90
d50 = (b50-c50)/b50*100 if b50>0 else 0
d90 = (b90-c90)/b90*100 if b90>0 else 0
sign = lambda x: '+' if x<0 else '-'
arrow = lambda x: '<---REGRESS' if x<-5 else ('IMPROVE' if x>5 else '~same')
print(f'  {\"$qname\":<25} p50: {b50:4d}->{c50:4d}ms ({sign(d50)}{abs(d50):.0f}% {arrow(d50)})  p90: {b90:4d}->{c90:4d}ms ({sign(d90)}{abs(d90):.0f}% {arrow(d90)})')
"
  done
  echo ""
  echo "  Cache comparisons:"
  for cache in filterCache queryResultCache documentCache; do
    b_hr=$(extract_cache "$baseline" "$cache" hitRatio)
    c_hr=$(extract_cache "$candidate" "$cache" hitRatio)
    b_ev=$(extract_cache "$baseline" "$cache" evictions)
    c_ev=$(extract_cache "$candidate" "$cache" evictions)
    [ -z "$b_hr" ] && continue
    python3 -c "
bhr,chr=$b_hr,$c_hr; bev,cev=$b_ev,$c_ev
print(f'  {\"$cache\":<20} hitRatio: {float(bhr):.3f}->{float(chr):.3f}  evictions: {int(float(bev)):,}->{int(float(cev)):,}')
"
  done
  echo ""
  # Concurrent req/s if available
  b_rps=$(extract_metric "$baseline" "" rps)
  c_rps=$(extract_metric "$candidate" "" rps)
  if [ -n "$b_rps" ] && [ -n "$c_rps" ]; then
    python3 -c "
brps,crps = $b_rps,$c_rps
d = (crps-brps)/brps*100 if brps>0 else 0
print(f'  Concurrent req/s: {brps:.1f} -> {crps:.1f} ({d:+.1f}%)')
"
  fi
}

decide() {
  # decide <experiment_label> <config_to_revert_to_if_bad>
  local label="$1"
  local revert_config="$2"
  echo ""
  echo "=== Decision for $label ==="
  # Check if p90 improved on average
  local baseline="$RESULTS_DIR/baseline.txt"
  local candidate="$RESULTS_DIR/$label.txt"
  local improved=$(python3 -c "
import sys, re

def p90s(f):
    vals = []
    for line in open(f):
        m = re.search(r'p90=(\d+)ms', line)
        if m:
            vals.append(int(m.group(1)))
    return vals

b = p90s('$baseline')
c = p90s('$candidate')
if not b or not c or len(b) != len(c):
    print('INCONCLUSIVE')
    sys.exit(0)
improve = sum(1 for bv,cv in zip(b,c) if cv < bv)
regress = sum(1 for bv,cv in zip(b,c) if cv > bv * 1.05)
if improve > regress and regress == 0:
    print('KEEP')
elif regress > 0:
    print('REVERT')
else:
    print('NEUTRAL')
")
  echo "  Result: $improved"
  if [ "$improved" = "REVERT" ]; then
    echo "  Reverting to: $revert_config"
    cp "$revert_config" "$SOLRCONFIG"
    reload_core
  elif [ "$improved" = "KEEP" ]; then
    echo "  Keeping $label — updating baseline snapshot"
    cp "$SOLRCONFIG" "$RESULTS_DIR/solrconfig_after_$label.xml"
    # The candidate becomes the new baseline for subsequent tests
    cp "$candidate" "$baseline"
  else
    echo "  Neutral change — keeping for now (no regression)"
    cp "$SOLRCONFIG" "$RESULTS_DIR/solrconfig_after_$label.xml"
  fi
}

# ---------------------------------------------------------------------------
# BASELINE
# ---------------------------------------------------------------------------
if [ "$SKIP_BASELINE" != "true" ]; then
  echo "================================================================"
  echo "STEP 0: Baseline (current solrconfig.xml, no changes)"
  echo "================================================================"
  cp "$SOLRCONFIG" "$RESULTS_DIR/solrconfig_baseline.xml"
  run_bench baseline "$CONCURRENCY"
fi

# ---------------------------------------------------------------------------
# EXP 1: Enable useFilterForSortedQuery
# ---------------------------------------------------------------------------
echo ""
echo "================================================================"
echo "EXP 1: Enable useFilterForSortedQuery"
echo "  Hypothesis: sorted non-score queries (author pages, language sort)"
echo "  can reuse filterCache entries instead of re-scanning the index."
echo "================================================================"
cp "$RESULTS_DIR/solrconfig_baseline.xml" "$SOLRCONFIG"
# Enable useFilterForSortedQuery (there are two commented blocks; enable the first one)
python3 - "$SOLRCONFIG" <<'PYEOF'
import sys, re

content = open(sys.argv[1]).read()

# Replace the first commented-out useFilterForSortedQuery block
old = '''    <!--
       <useFilterForSortedQuery>true</useFilterForSortedQuery>
      -->

    <!-- Result Window Size'''

new = '''    <useFilterForSortedQuery>true</useFilterForSortedQuery>

    <!-- Result Window Size'''

if old not in content:
    print("WARNING: could not find expected useFilterForSortedQuery block, trying alternate", file=sys.stderr)
    # Try alternate patterns
    content = content.replace(
        '<!--\n       <useFilterForSortedQuery>true</useFilterForSortedQuery>\n      -->',
        '<useFilterForSortedQuery>true</useFilterForSortedQuery>',
        1
    )
else:
    content = content.replace(old, new, 1)

open(sys.argv[1], 'w').write(content)
print("Done")
PYEOF

reload_core
run_bench exp1-useFilterForSortedQuery "$CONCURRENCY"
compare_runs exp1-useFilterForSortedQuery
decide exp1-useFilterForSortedQuery "$RESULTS_DIR/solrconfig_baseline.xml"

# ---------------------------------------------------------------------------
# EXP 2: Increase cache sizes
# ---------------------------------------------------------------------------
echo ""
echo "================================================================"
echo "EXP 2: Increase cache sizes"
echo "  filterCache: 512->4096, queryResultCache: 512->2048,"
echo "  documentCache: 512->1024, autowarmCount: 128->256"
echo "  Hypothesis: more entries cached = higher hit ratios,"
echo "  fewer cold queries, lower p90 latency."
echo "================================================================"
PREV_CONFIG="$RESULTS_DIR/solrconfig_after_exp1-useFilterForSortedQuery.xml"
[ -f "$PREV_CONFIG" ] || PREV_CONFIG="$RESULTS_DIR/solrconfig_baseline.xml"
cp "$PREV_CONFIG" "$SOLRCONFIG"

python3 - "$SOLRCONFIG" <<'PYEOF'
import sys, re

content = open(sys.argv[1]).read()

# filterCache: 512 -> 4096, autowarmCount 128 -> 256
content = re.sub(
    r'(<filterCache\s+size=)"512"(\s+initialSize=)"512"(\s+autowarmCount=)"128"',
    r'\g<1>"4096"\2"512"\3"256"',
    content
)
# queryResultCache: 512 -> 2048, autowarmCount 128 -> 256
content = re.sub(
    r'(<queryResultCache\s+size=)"512"(\s+initialSize=)"512"(\s+autowarmCount=)"128"',
    r'\g<1>"2048"\2"512"\3"256"',
    content
)
# documentCache: 512 -> 1024 (no autowarm for doc cache)
content = re.sub(
    r'(<documentCache\s+size=)"512"(\s+initialSize=)"512"(\s+autowarmCount=)"0"',
    r'\g<1>"1024"\2"512"\3"0"',
    content
)

open(sys.argv[1], 'w').write(content)
print("Done")
PYEOF

reload_core
run_bench exp2-larger-caches "$CONCURRENCY"
compare_runs exp2-larger-caches
decide exp2-larger-caches "$PREV_CONFIG"

# ---------------------------------------------------------------------------
# EXP 3: Increase queryResultWindowSize 20 -> 50
# ---------------------------------------------------------------------------
echo ""
echo "================================================================"
echo "EXP 3: Increase queryResultWindowSize from 20 to 50"
echo "  Hypothesis: page 2 (start=20) hits the same cache entry as"
echo "  page 1, eliminating the re-query. p50 for paginate_p2 drops."
echo "================================================================"
PREV_CONFIG="$(ls -1t "$RESULTS_DIR"/solrconfig_after_exp*.xml 2>/dev/null | head -1 || echo "$RESULTS_DIR/solrconfig_baseline.xml")"
cp "$PREV_CONFIG" "$SOLRCONFIG"

python3 - "$SOLRCONFIG" <<'PYEOF'
import sys

content = open(sys.argv[1]).read()
content = content.replace(
    '<queryResultWindowSize>20</queryResultWindowSize>',
    '<queryResultWindowSize>50</queryResultWindowSize>',
    1
)
open(sys.argv[1], 'w').write(content)
print("Done")
PYEOF

reload_core
run_bench exp3-queryResultWindow50 "$CONCURRENCY"
compare_runs exp3-queryResultWindow50
decide exp3-queryResultWindow50 "$PREV_CONFIG"

# ---------------------------------------------------------------------------
# EXP 4: Increase queryResultMaxDocsCached 200 -> 400
# ---------------------------------------------------------------------------
echo ""
echo "================================================================"
echo "EXP 4: Increase queryResultMaxDocsCached from 200 to 400"
echo "  Hypothesis: deeper result sets (e.g. facet browsing) stay"
echo "  cached instead of requiring index re-traversal."
echo "================================================================"
PREV_CONFIG="$(ls -1t "$RESULTS_DIR"/solrconfig_after_exp*.xml 2>/dev/null | head -1 || echo "$RESULTS_DIR/solrconfig_baseline.xml")"
cp "$PREV_CONFIG" "$SOLRCONFIG"

python3 - "$SOLRCONFIG" <<'PYEOF'
import sys

content = open(sys.argv[1]).read()
content = content.replace(
    '<queryResultMaxDocsCached>200</queryResultMaxDocsCached>',
    '<queryResultMaxDocsCached>400</queryResultMaxDocsCached>',
    1
)
open(sys.argv[1], 'w').write(content)
print("Done")
PYEOF

reload_core
run_bench exp4-deeperResultCache "$CONCURRENCY"
compare_runs exp4-deeperResultCache
decide exp4-deeperResultCache "$PREV_CONFIG"

# ---------------------------------------------------------------------------
# EXP 5: Explicit fieldValueCache (for faceting)
# ---------------------------------------------------------------------------
echo ""
echo "================================================================"
echo "EXP 5: Explicit fieldValueCache configuration"
echo "  Hypothesis: explicitly sizing the fieldValueCache for OL's"
echo "  facet fields (author, subject, language) improves faceted search."
echo "================================================================"
PREV_CONFIG="$(ls -1t "$RESULTS_DIR"/solrconfig_after_exp*.xml 2>/dev/null | head -1 || echo "$RESULTS_DIR/solrconfig_baseline.xml")"
cp "$PREV_CONFIG" "$SOLRCONFIG"

python3 - "$SOLRCONFIG" <<'PYEOF'
import sys

content = open(sys.argv[1]).read()
# Replace the commented-out fieldValueCache with an explicit one
old = '''    <!--
       <fieldValueCache size="512"
                        autowarmCount="128"
                        />
      -->'''
new = '''    <!-- fieldValueCache: explicitly sized for OL's multi-valued string facet fields -->
    <fieldValueCache size="2048"
                     autowarmCount="256"
                     />'''
if old in content:
    content = content.replace(old, new, 1)
    open(sys.argv[1], 'w').write(content)
    print("Done")
else:
    print("WARNING: fieldValueCache block not found, skipping", file=sys.stderr)
PYEOF

reload_core
run_bench exp5-fieldValueCache "$CONCURRENCY"
compare_runs exp5-fieldValueCache
decide exp5-fieldValueCache "$PREV_CONFIG"

# ---------------------------------------------------------------------------
# EXP 6: Enable memory circuit breaker
# ---------------------------------------------------------------------------
echo ""
echo "================================================================"
echo "EXP 6: Enable memory circuit breaker (memThreshold=80)"
echo "  Hypothesis: circuit breaker prevents OOM/GC storms without"
echo "  impacting normal query latency. Stability not perf improvement."
echo "================================================================"
PREV_CONFIG="$(ls -1t "$RESULTS_DIR"/solrconfig_after_exp*.xml 2>/dev/null | head -1 || echo "$RESULTS_DIR/solrconfig_baseline.xml")"
cp "$PREV_CONFIG" "$SOLRCONFIG"

python3 - "$SOLRCONFIG" <<'PYEOF'
import sys

content = open(sys.argv[1]).read()
old = '''  <circuitBreaker class="solr.CircuitBreakerManager" enabled="true">
    <!-- Memory Circuit Breaker

     Specific configuration for max JVM heap usage circuit breaker. This configuration defines
     whether the circuit breaker is enabled and the threshold percentage of maximum heap allocated
     beyond which queries will be rejected until the current JVM usage goes below the threshold.
     The valid value for this range is 50-95.

     Consider a scenario where the max heap allocated is 4 GB and memThreshold is defined as 75.
     Threshold JVM usage will be 4 * 0.75 = 3 GB. Its generally a good idea to keep this value
     between 75 - 80% of maximum heap allocated.

     If, at any point, the current JVM heap usage goes above 3 GB, queries will be rejected with 503 error code,
     check for "Circuit Breakers tripped" in logs and the corresponding error message should tell
     you what transpired (if the failure was caused by tripped circuit breakers).
    -->
    <!--
    <str name="memEnabled">true</str>
    <str name="memThreshold">75</str>
    -->'''
new = '''  <circuitBreaker class="solr.CircuitBreakerManager" enabled="true">
    <!-- Memory circuit breaker: reject queries when heap > 80% to prevent GC storms -->
    <str name="memEnabled">true</str>
    <str name="memThreshold">80</str>'''
if old in content:
    content = content.replace(old, new, 1)
    open(sys.argv[1], 'w').write(content)
    print("Done")
else:
    # Try a simpler replacement approach
    import re
    content = re.sub(
        r'<!--\s*\n\s*<str name="memEnabled">true</str>\s*\n\s*<str name="memThreshold">75</str>\s*\n\s*-->',
        '<str name="memEnabled">true</str>\n    <str name="memThreshold">80</str>',
        content
    )
    open(sys.argv[1], 'w').write(content)
    print("Done (alternate path)")
PYEOF

reload_core
run_bench exp6-circuitBreaker "$CONCURRENCY"
compare_runs exp6-circuitBreaker
decide exp6-circuitBreaker "$PREV_CONFIG"

# ---------------------------------------------------------------------------
# EXP 7: Combined best config - concurrent load test
# ---------------------------------------------------------------------------
echo ""
echo "================================================================"
echo "EXP 7: Combined best config — concurrent load test (16 workers)"
echo "  Running the final configuration under sustained concurrent load"
echo "  to measure throughput and tail latency improvements."
echo "================================================================"
FINAL_CONFIG="$(ls -1t "$RESULTS_DIR"/solrconfig_after_exp*.xml 2>/dev/null | head -1 || echo "$RESULTS_DIR/solrconfig_baseline.xml")"
echo "  Using config: $FINAL_CONFIG"
cp "$FINAL_CONFIG" "$SOLRCONFIG"
reload_core

run_bench baseline-concurrent-load 16
run_bench final-concurrent-load 16
compare_runs final-concurrent-load

# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------
echo ""
echo "================================================================"
echo "FINAL SUMMARY"
echo "================================================================"
echo "Baseline config: $RESULTS_DIR/solrconfig_baseline.xml"
echo "Final config:    $FINAL_CONFIG"
echo ""
echo "Results in: $RESULTS_DIR/"
ls -1t "$RESULTS_DIR/"*.txt 2>/dev/null | head -20
echo ""
echo "To apply final config to production, copy the latest"
echo "solrconfig_after_exp*.xml to conf/solr/conf/solrconfig.xml"
echo "and redeploy the Solr container."
