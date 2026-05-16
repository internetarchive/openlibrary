#!/usr/bin/env bash
# scripts/solr_benchmark.sh <label> [concurrency=1]
#
# Measures Solr query latency (QTime), cache stats, and JVM memory.
# Run before and after each config change to get evidence for keeping/reverting.
#
# Examples:
#   ./scripts/solr_benchmark.sh baseline 1
#   ./scripts/solr_benchmark.sh after-exp1-filterCache 1
#   ./scripts/solr_benchmark.sh load-test 16
set -euo pipefail

SOLR="${SOLR:-http://localhost:8983/solr/openlibrary}"
LABEL="${1:-baseline}"
CONCURRENCY="${2:-1}"

echo "=== $LABEL | $(date -Iseconds) | concurrency=$CONCURRENCY ==="
echo ""

# ---------------------------------------------------------------------------
# Representative OL query patterns — mirrors real search/browse paths.
# Keys are short names printed in output; values are query strings.
# ---------------------------------------------------------------------------
declare -A QUERIES=(
  # Full-text + facets: the most common pattern (homepage search box)
  ["fulltext_faceted"]="q=harry+potter&fq=type:work&rows=20&facet=true&facet.field=author_facet&facet.field=language&facet.field=subject_facet&facet.field=first_publish_year&wt=json"
  # Author page: sorts by edition_count (non-score) — key test for useFilterForSortedQuery
  ["author_sorted"]="q=*:*&fq=type:work&fq=author_key:OL2162284A&sort=edition_count+desc&rows=20&facet=true&facet.field=subject_facet&wt=json"
  # Ebook-only browse: heavy fq filter, common for borrowable-books feature
  ["ebook_access"]="q=*:*&fq=type:work&fq=ebook_access:%5Bprintdisabled+TO+*%5D&rows=20&facet=true&facet.field=language&wt=json"
  # Language filter: enum-like fq, should be filterCache-friendly
  ["lang_filter"]="q=*:*&fq=type:work&fq=language:fre&sort=edition_count+desc&rows=20&wt=json"
  # Two combined fq filters: exercises filterCache intersection
  ["multi_filter"]="q=*:*&fq=type:work&fq=language:spa&fq=ebook_access:%5Bprintdisabled+TO+*%5D&rows=20&wt=json"
  # Page 2 of results: cache hit only if queryResultWindowSize >= 40
  ["paginate_p2"]="q=harry+potter&fq=type:work&rows=20&start=20&wt=json"
  # Page 5 of results: cache hit only if queryResultWindowSize >= 100
  ["paginate_p5"]="q=harry+potter&fq=type:work&rows=20&start=80&wt=json"
  # Subject search: different query shape, different cache slots
  ["subject_search"]="q=subject:mystery&fq=type:work&rows=20&facet=true&facet.field=author_facet&wt=json"
)

# ---------------------------------------------------------------------------
# Sequential latency measurement
# ---------------------------------------------------------------------------
echo "-- Sequential QTime (warmup=10, measure=30) --"

for name in "${!QUERIES[@]}"; do
  for i in {1..10}; do curl -gs "$SOLR/select?${QUERIES[$name]}" > /dev/null; done
done

for name in "${!QUERIES[@]}"; do
  qtimes=()
  for i in {1..30}; do
    qt=$(curl -gs "$SOLR/select?${QUERIES[$name]}" \
      | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['responseHeader']['QTime'])" 2>/dev/null || echo "0")
    qtimes+=("$qt")
  done
  python3 -c "
nums = [int(x) for x in '${qtimes[*]}'.split()]
s = sorted(nums)
n = len(s)
p50 = s[n//2]
p90 = s[int(n*0.9)]
avg = sum(nums)/n
print(f'  {\"$name\":<25} avg={avg:6.1f}ms  p50={p50:4d}ms  p90={p90:4d}ms  max={max(nums):4d}ms')
"
done

# ---------------------------------------------------------------------------
# Cache statistics
# ---------------------------------------------------------------------------
echo ""
echo "-- Cache Stats --"
curl -s "$SOLR/admin/mbeans?stats=true&cat=CACHE&wt=json" | python3 -c "
import json, sys
d = json.load(sys.stdin)
beans = d.get('solr-mbeans', [])
i = 0
while i < len(beans) - 1:
    name, data = beans[i], beans[i+1]
    i += 2
    if not isinstance(name, str) or not isinstance(data, dict):
        continue
    if name not in ('filterCache','queryResultCache','documentCache','fieldValueCache'):
        continue
    s = data.get('stats', {})
    hr  = s.get('cumulative_hitratio',  s.get('hitratio',  0))
    ev  = s.get('cumulative_evictions', s.get('evictions',  0))
    sz  = s.get('size', 0)
    lk  = s.get('cumulative_lookups',   s.get('lookups',    0))
    ins = s.get('cumulative_inserts',   s.get('inserts',    0))
    print(f'  {name:<20} hitRatio={float(hr):.3f}  evictions={int(ev):8,}  sz={int(sz):5,}  lookups={int(lk):8,}  inserts={int(ins):6,}')
" 2>/dev/null || echo "  (cache stats unavailable)"

# ---------------------------------------------------------------------------
# JVM memory and GC — primary heap pressure signal
# ---------------------------------------------------------------------------
echo ""
echo "-- JVM Memory & GC --"
curl -s "$SOLR/admin/metrics?group=jvm&wt=json" | python3 -c "
import json, sys
m = json.load(sys.stdin).get('metrics', {}).get('solr.jvm', {})
hu  = m.get('memory.heap.used', 0) / 1e9
hx  = m.get('memory.heap.max',  0) / 1e9
pct = (hu / hx * 100) if hx else 0
# G1GC keys (default for Solr 9 on JDK 17)
yc = m.get('gc.G1-Young-Generation.count', m.get('gc.ZGC-Cycles.count', 0))
yt = m.get('gc.G1-Young-Generation.time',  m.get('gc.ZGC-Cycles.time',  0))
oc = m.get('gc.G1-Old-Generation.count',   m.get('gc.ZGC-Pauses.count', 0))
ot = m.get('gc.G1-Old-Generation.time',    m.get('gc.ZGC-Pauses.time',  0))
print(f'  Heap: {hu:.2f}GB used / {hx:.2f}GB max  ({pct:.1f}%)')
print(f'  GC Young: count={int(yc)}  time={int(yt)}ms')
print(f'  GC Major: count={int(oc)}  time={int(ot)}ms  <- heap pressure indicator')
" 2>/dev/null || echo "  (JVM metrics unavailable)"

# ---------------------------------------------------------------------------
# Concurrent load test — uses Python threading, no external tools needed
# ---------------------------------------------------------------------------
if [[ "${CONCURRENCY}" -gt 1 ]]; then
  echo ""
  echo "-- Concurrent Load: ${CONCURRENCY} workers x 30s --"
  python3 - <<PYEOF
import concurrent.futures, time, urllib.request, json, sys

SOLR    = "http://localhost:8983/solr/openlibrary"
WORKERS = ${CONCURRENCY}
DURATION = 30

QUERIES = [
    "q=harry+potter&fq=type:work&rows=20&facet=true&facet.field=author_facet&facet.field=language&wt=json",
    "q=*:*&fq=type:work&fq=ebook_access:%5Bprintdisabled+TO+*%5D&rows=20&wt=json",
    "q=tolkien&fq=type:work&rows=20&wt=json",
    "q=*:*&fq=type:work&fq=language:fre&rows=20&wt=json",
    "q=mystery&fq=type:work&rows=20&facet=true&facet.field=subject_facet&wt=json",
    "q=*:*&fq=type:work&fq=language:spa&fq=ebook_access:%5Bprintdisabled+TO+*%5D&rows=20&wt=json",
    "q=harry+potter&fq=type:work&rows=20&start=20&wt=json",
    "q=subject:fiction&fq=type:work&rows=20&facet=true&wt=json",
]

stop_at = time.time() + DURATION

def worker(wid):
    qtimes, errors = [], 0
    i = 0
    while time.time() < stop_at:
        q = QUERIES[i % len(QUERIES)]
        try:
            with urllib.request.urlopen(f"{SOLR}/select?{q}", timeout=10) as r:
                d = json.loads(r.read())
                qtimes.append(d["responseHeader"]["QTime"])
        except Exception:
            errors += 1
        i += 1
    return qtimes, errors

all_times, total_errors = [], 0
with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
    for times, errs in ex.map(lambda i: worker(i), range(WORKERS)):
        all_times.extend(times)
        total_errors += errs

s = sorted(all_times)
n = len(s)
rps = n / DURATION
print(f"  {n} requests, {total_errors} errors => {rps:.1f} req/s")
if n:
    print(f"  QTime: avg={sum(s)/n:.1f}ms  p50={s[n//2]}ms  p90={s[int(n*0.9)]}ms  p99={s[int(n*0.99)]}ms  max={max(s)}ms")
PYEOF
fi

echo ""
echo "=== done: $LABEL ==="
