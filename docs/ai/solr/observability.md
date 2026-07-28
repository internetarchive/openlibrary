# Solr Observability — the "why", not just the "what"

Saul's working analysis of OL's Solr observability gap. Written 2026-07-27.

**Framing (per Mek):** Grafana already shows *what* is slow (which endpoint/query label is
sitting in a high-latency bucket). It shows nothing about *why* — no query execution
breakdown, no GC, no cache behaviour, no thread contention.

Everything below marked ✅ was verified locally against a real `solr:10.0.0` container running
Open Library's own configset (`conf/solr`). Everything marked 🔒 needs VPN/production access.
The two lists are kept strictly separate on purpose.

---

## What exists today

`scripts/monitoring/solr_logs_monitor.py`, registered in `scripts/monitoring/monitor.py:77`
under `@limit_server(["ol-solr0", "ol-solr1", "ol-solr2"])`, tails `docker logs` of the Solr
container, parses `o.a.s.c.S.Request` lines, and pushes Graphite events:

- `requests.total`
- `requests.path.{path}`
- `requests.time.{bucket}` — QTime bucketed into 10/100/1000/5000/10000/20000ms
- `requests.query.{ol.label}.time.{bucket}`

That is a complete "what" pipeline and a genuinely good one — `ol.label` gives per-feature
attribution. It is also the *entire* Solr metrics story. Everything else Solr knows about
itself is on the floor.

`conf/solr/haproxy.cfg` exposes `http-request use-service prometheus-exporter if { path /metrics }`
on port 8984 — but those are *HAProxy's* metrics (backend health, connection counts), not Solr's.
More "what".

---

## Findings

### 1. ✅ The existing pipeline is silently broken on Solr 10 — **PR #13212**

Solr 10 removed `webapp=/solr` from request log lines and added `rid=`.
`RequestLogEntry.parse_log_entry` reads `fields["webapp"]` — a hard lookup — so **every**
request line raises `KeyError`, which `safe_parse_log_entry` swallows. No metrics are emitted
at all; the dashboards flatline to zero rather than erroring, so nothing alerts.

Measured against a live `solr:10.0.0` container:

| | Graphite events | parse errors |
|---|---|---|
| before | **0** | 15 |
| after | **45** | 0 |

Fixed in PR #13212. This gates everything else: there is no point layering "why" metrics on a
collection path that silently drops everything.

🔒 Which Solr version `ol-solr0`/`ol-solr2` actually run right now is **unverified** — the
`solr`/`solr_replica` services in `compose.production.yaml` are profile-disabled ("Disabled
until next solr reindex due to solr version upgrade") while `compose.yaml` pins `solr:10.0.0`.
So this either fixes a live outage or defuses a landmine. Can't tell from outside.

### 2. ✅ Solr already emits the entire "why" dataset. Nobody scrapes it.

`/solr/admin/metrics` on each node. **Note: Solr 10 removed JSON output** — `wt=json` now
returns HTTP 400 (`"Only Prometheus and OpenMetrics metric formats supported"`). It's
Prometheus text format only. Confirmed present on OL's configset (630 lines, 87KB):

| Metric family | Answers |
|---|---|
| `solr_core_indexsearcher_cache_lookups_total{name,result=hit\|miss}` | **cache hit ratio**, per cache |
| `solr_core_indexsearcher_cache_ops_total{name,ops=evictions\|inserts}` | **eviction pressure** — is `size=512` too small? |
| `solr_core_indexsearcher_cache_warmup_time_milliseconds` | **autowarm cost** per searcher |
| `solr_core_searcher_new_total` | searcher churn from soft commits |
| `jvm_gc_duration_seconds` (histogram, per G1 phase) | **GC pause distribution** |
| `jvm_memory_used_after_last_gc_bytes` | true live-set — the real heap-pressure signal |
| `solr_node_requests_times_milliseconds` / `_errors_total` | latency + errors at the node |
| `solr_core_segments`, `solr_core_index_size_megabytes` | merge pressure |
| `solr_core_update_docs_pending_commit`, `solr_core_update_auto_commits_total` | indexing vs query contention |

**Proposal:** a sibling `scripts/monitoring/solr_metrics_monitor.py` polling
`http://localhost:8983/solr/admin/metrics` and emitting `GraphiteEvent`s, registered next to
the existing `monitor_solr()` job. It runs *on* the Solr host, so it's localhost — no
cross-host networking, no auth. The only new work is a Prometheus-text → Graphite mapping.
This is the single biggest win and it needs no production access to build or test.

### 3. ✅ Slow-query logging is off, and turning it on isn't enough

`conf/solr/conf/solrconfig.xml` has **no `<slowQueryThresholdMillis>`**. Solr's most direct
"why this specific query" instrument is simply absent.

Verified: adding `<slowQueryThresholdMillis>2</slowQueryThresholdMillis>` to the `<query>`
section works, producing full params + QTime:

```
WARN ... o.a.s.c.S.SlowRequest slow: path=/select params={q=*:*&...&ol.label=SAUL_SLOWTEST} rid=... QTime=5
```

**But** the Solr image's `log4j2.xml` routes `org.apache.solr.core.SolrCore.SlowRequest` with
`additivity="false"` to a `SlowLogFile` appender only — it **never reaches stdout**, so a
`docker logs`-based monitor cannot see it. Confirmed: the line lands in
`/var/solr/logs/solr_slow_requests.log` and is absent from `docker logs`.

So this ships as two pieces: the config threshold *and* a log4j2 override adding `STDOUT`
(or a reader for the slow-requests file). Worth doing — this is what names the actual
offending query.

### 4. ✅ `debug=timing` gives a per-component breakdown, cheaply

`debug=timing` **without** `debugQuery=true` returns *only* the timing tree and skips the
expensive `explain` computation — verified: `sections: ['timing']`. It splits prepare vs
process across every component:

```
prepare: 5.0ms  (query 5.0, facet 0.0, highlight 0.0, ...)
process: 3.0ms  (query 2.0, facet 0.0, ...)
```

That is precisely "which part of this query ate the time."

There is already a shipped precedent for exposing Solr internals through OL's own API:
`SolrInternalsParams` (`openlibrary/fastapi/models.py:81`), a pydantic model of dismax
overrides, gated behind the `OL_EXPOSE_SOLR_INTERNALS_PARAMS` env flag
(`openlibrary/plugins/worksearch/code.py:852`). Adding a `solr_debug` passthrough there is an
extension of an accepted pattern, with gating already built.

### 5. ✅ Caches are still Solr's stock example defaults

```xml
<filterCache      size="512" initialSize="512" autowarmCount="128"/>
<queryResultCache size="512" initialSize="512" autowarmCount="128"/>
<documentCache    size="512" initialSize="512" autowarmCount="0"/>
```

These are the values shipped in Solr's sample config — nobody has tuned them for a ~40M-doc
index where every subject page and `fq` clause competes for 512 filterCache slots.

I am **not** claiming they're wrong. That claim requires hit-rate and eviction data, which is
exactly finding #2. **#2 gates #5** — collect first, then tune.

### 6. ✅ Production heap is 8g, not 10g — the repo's own open question, answered

`compose.production.yaml` sets both, with a literal comment `# This might overwrite the above?`:

```yaml
- SOLR_JAVA_MEM=-Xms10g -Xmx10g
- SOLR_HEAP=8g          # "This might overwrite the above?"
```

Tested directly (`SOLR_JAVA_MEM=-Xms300m -Xmx300m` + `SOLR_HEAP=500m`): resulting JVM args
were `-Xms500m -Xmx500m`, max heap 500MB. **`SOLR_HEAP` wins.** Production Solr runs an 8g
heap, not the 10g the config appears to promise.

Heap sizing is the primary driver of GC pause behaviour, i.e. the most common answer to "why
was that query randomly slow." The team currently can't answer "how much heap does Solr have"
from reading the config. Cheap cleanup PR: drop the redundant `SOLR_JAVA_MEM` and the comment.

### 7. ✅ A soft-commit hypothesis I checked and discarded

`solrconfig.xml` defaults to `autoSoftCommit.maxTime=3000` with `maxWarmingSearchers=4`,
`useColdSearcher=false`, and `autowarmCount=128` on two caches — a classic warming-pileup
death spiral. **Production overrides it to 60000 (60s)** in `compose.production.yaml`, so this
is dev-only and is *not* a prod root cause. Recording it so nobody re-runs the same dead end.

---

## Proposed order

1. **PR #13212** — fix Solr 10 log parsing. *(shipped; unblocks everything)*
2. **`solr_metrics_monitor.py`** — scrape `/solr/admin/metrics` → Graphite. Cache hit rates,
   evictions, GC, warmup time. Biggest single win; fully buildable now.
3. **Heap cleanup** — remove the ambiguous `SOLR_JAVA_MEM`/`SOLR_HEAP` pair. Trivial.
4. **Slow-query logging** — `slowQueryThresholdMillis` + log4j2 STDOUT routing.
   ⚠️ blocked on 🔒 (how does solrconfig reach prod? — see below).
5. **`debug=timing` passthrough** behind `OL_EXPOSE_SOLR_INTERNALS_PARAMS`.
6. **Cache tuning** — only once #2 has produced real hit-rate data.

---

## 🔒 Requires VPN / production access

Explicitly **not** doable from this environment. Confirmed unreachable: Grafana
`wwwb-grafana0.us.archive.org` DNS resolves to 207.241.234.66 but **TCP 443 is filtered**
(8s timeout). `ol-solr0/1/2.us.archive.org` all resolve, all filtered. Public
`openlibrary.org/search.json` returns 200 — so this is specifically IA-internal gating, not a
general network problem. I did not silently assume this; I probed it.

1. **Which Solr version is actually running on `ol-solr0`/`ol-solr2`.** Determines whether
   PR #13212 fixes a live metrics outage or prevents a future one.
2. **How `conf/solr/conf/solrconfig.xml` actually reaches production**, given both prod Solr
   compose services are profile-disabled. A config-as-code PR may never reach the running
   nodes. **This gates items 4 and 6 above** — needs answering before I write those PRs.
3. **Whether `/solr/admin/metrics` is already scraped** by something outside this repo
   (a separate Prometheus job I can't see). Would change #2 from "build it" to "wire it up."
4. **Whether HAProxy's `/metrics` on :8984 is currently scraped**, and into what.
5. **Real cache hit ratios and eviction rates.** The only way to settle whether `size=512` is
   undersized. Everything about cache tuning is guesswork until this exists.
6. **Real GC behaviour under real load.** `solr_gc.log` is already written by default inside
   the container (confirmed locally) — nobody is collecting it.
7. **A real slow-query corpus.** Which queries actually exceed threshold in production, at
   what rate, and with which `ol.label`.
8. **Thread dumps under load** — for contention, which no metric above captures.
9. **What the existing Grafana Solr dashboard (`d/000000174`) already panels**, so a metrics
   PR extends it rather than duplicating it.

Items 5–8 are the actual "why" diagnosis. Items 1–4 and 9 are questions that change *what I
should build*, and are the ones worth answering first.
