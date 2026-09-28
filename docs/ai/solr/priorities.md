# Solr Priorities

Saul's living record of what matters in Solr land and why. Updated as context changes. Not a task tracker — a "why does this matter" reference so priorities don't get lost between sessions.

Last updated: 2026-06-23

---

## Active priorities (ranked)

### 1. `/search/carousels.json` — PR #12987

**Why it matters:** The BookServer mobile app and `opds.openlibrary.org` currently hit OL with N parallel search queries to build homepage carousels. This bursts past OL's rate limiter, causing 429s that degrade the reader.archive.org experience. This endpoint bundles up to 20 Solr queries into one request, returning results in order — one cached HTTP call per page load instead of N.

**Downstream:** pyopds2_openlibrary PR #102 (Odie) depends on this endpoint being live before it can ship. The OPDS home feed is broken at scale until both land.

**Current state:** PR #12987 open, bot commit squashed, CI passing, ready for code review. Endpoint is confirmed `/search/carousels.json`. The OPDS system doc (`pm/workflows/opds-system.md`) still references `/search/batch.json` — Odie must update pyopds2 PR #102 to use the correct URL before shipping.

**Owner:** PR by @mekarpeles; Odie owns the pyopds2 consumer side.

---

### 2. Near-realtime loan availability — PR #12689

**Why it matters:** Every OL search result currently requires a separate bulk call to `archive.org/services/availability` to fold in realtime availability (is this copy borrowable right now?). That's an expensive N+1 join on a hot path — every search page, every subject page, every OPDS feed. The standalone `loan_availability_updater.py` polls IA's loan changes API and atomically updates `ebook_availability` on work docs so Solr can serve availability without any external join.

**Current state:** Open, P2, MERGEABLE. `Needs: Special Deploy` label now present. Author still needs to add `docValues="true"` to `ebook_becomes_available` (pdate field). No reviewer assigned. 32+ days open.

**Owner:** PR by mekarpeles + bendeitch collaborating.

---

### 3. Cover dimensions in Solr — PR #12916

**Why it matters:** OL and the BookServer app need cover width/height at render time to pre-allocate space and prevent layout shifting (CLS). Currently the front-end has no way to know dimensions without fetching the cover image first. These fields (`cover_width`, `cover_height`) come from the covers DB at index time, so the search result carries the dimensions.

**Current state:** Open, `Needs: Special Deploy`, dependency #12915 merged. PR body says "confirmed works locally" but **no unit tests exist** for the new code paths (`get_cover_dimensions`, `cover_width`/`cover_height` on both `WorkSolrBuilder` and `EditionSolrBuilder`). Solr-builder Jenkinsfile changes explicitly noted as untested. `coverstore` DB connection not in standard Docker setup — silent `None` for dimensions in local dev without additional setup.

**Owner:** cdrini.

---

### 4. Prices / acquisition fields — WIP (no PR yet)

**Why it matters:** Required to filter, facet, and query for buyable books in search results (e.g. "show me works where I can buy an ebook"). Also directly unblocks Impa (Import Pipeline agent): ingesting OPDS feeds from publishers requires the acquisition object (price, currency, format, link) to be representable in Solr so imported editions can surface in filtered search.

**Current state:** DB layer exists (PRs #12852 and #12846 by ronibhakta1 — `tbp_feed_registry` table + `FeedRegistry` class). Affiliate server fix in PR #12993 (cdrini, active). **Solr schema PR not yet open** — cdrini confirmed working on it. Field names TBD. No Solr design doc yet.

**Owner:** cdrini (Solr schema); ronibhakta1 (TBP ingest); Impa (OPDS consumer).

---

## Secondary / stale (needs triage)

| PR | Title | Age | Notes |
|----|-------|-----|-------|
| #11724 | Add quality score metrics to solr | ~80d | `Needs: Special Deploy` — stale schema PR, unknown current status |
| #12873 | Fix 3,063 lists with subjects failing to index | 14d | Bug fix, no labels, cdrini |
| #12874 | OR → terms query perf improvement | active | `Needs: Response` from Mek today, cdrini |
| #12660 | Simplify solr query for performance | 26d | cdrini, no labels |
| #11523 | Use solr ebook_access if availability errors | ~7mo | cdrini, no labels — may be superseded by #12689 |
| #12663 | `/search/editions.json` API + UI | P2 | Phase 1 & 2 of editions search — separate from above |

---

## Background / context

- **Why availability matters more than it looks:** `archive.org/services/availability` is a separate service under separate load. OL joins against it synchronously on search. If it's slow or rate-limiting, search latency spikes. Folding availability into Solr makes search latency independent of IA availability service health.
- **Why carousels.json is highest priority:** It's actively causing 429s in production. The OPDS homepage is degraded today.
- **Why prices unblocks Impa:** OPDS feed ingestion (publisher partnerships) requires acquisition objects to be searchable. Without Solr fields for price/format/availability, imported editions from OPDS feeds are dark — they land in OL's DB but don't surface in filtered search.
- **`ebook_access` vs `ebook_availability`:** These are complementary. `ebook_access` (enum: protected/printdisabled/borrowable/public) is the static "highest tier available for this work." `ebook_availability` (string: available/unavailable) is the realtime "is the borrowable copy checked out right now." Both are needed; neither replaces the other.
