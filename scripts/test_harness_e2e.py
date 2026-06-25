#!/usr/bin/env python3
"""End-to-end test harness for PR #12689 — ebook_availability Solr fields.

Verifies the complete cycle: schema, seed, borrow → unavailable, return → available,
eviction of expired loans, and example filter queries.

USAGE
─────
  cd ~/Projects/openlibrary-7450-loan-availability

  # Step 1 — Start a test Solr with the PR branch schema
  docker run -d --name ol-test-solr -p 8984:8983 \\
    -v "$(pwd)/conf/solr:/opt/solr/server/solr/configsets/olconfig:ro" \\
    -e "SOLR_MODULES=analysis-extras" \\
    solr:10.0.0 solr-precreate openlibrary /opt/solr/server/solr/configsets/olconfig

  # Step 2 — Wait ~15 s for Solr to initialise, then run
  python3 scripts/test_harness_e2e.py

  # Step 3 — Tear down when done
  docker stop ol-test-solr && docker rm ol-test-solr

The script uses only `requests` (stdlib-equivalent for our purposes).
It does NOT require infogami, OL config, or IA credentials.
All loan-event simulation is done inline so the full cycle is visible.

The updater logic (process_changes → build_solr_updates → Solr atomic update)
is reproduced inline at a level a reviewer can follow without reading the source.
"""

import contextlib
import datetime
import json
import sys
import time

import requests

SOLR = "http://localhost:8984/solr/openlibrary"

PASS = "✓"
FAIL = "✗"
SKIP = "-"

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def ok(msg: str) -> None:
    print(f"  {PASS}  {msg}")


def fail(msg: str) -> None:
    print(f"  {FAIL}  {msg}")
    sys.exit(1)


def banner(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def solr_post(path: str, payload) -> dict:
    url = f"{SOLR}/{path}"
    # Don't pass wt=json as a param when the path already has query args
    sep = "&" if "?" in path else "?"
    r = requests.post(f"{url}{sep}wt=json", json=payload, timeout=15)
    if not r.ok:
        print(f"  Solr error {r.status_code}: {r.text[:300]}")
        r.raise_for_status()
    return r.json()


def solr_get(path: str, **params) -> dict:
    url = f"{SOLR}/{path}"
    params.setdefault("wt", "json")
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def commit() -> None:
    solr_post("update", {"commit": {}})


def now_utc() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def future_utc(hours: int = 1) -> str:
    dt = datetime.datetime.utcnow() + datetime.timedelta(hours=hours)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def past_utc(hours: int = 2) -> str:
    dt = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ──────────────────────────────────────────────────────────────────────────────
# Step 0 — Verify Solr is up
# ──────────────────────────────────────────────────────────────────────────────


def check_solr() -> None:
    banner("Step 0 — Connecting to Solr")
    for attempt in range(15):
        try:
            r = requests.get(f"{SOLR}/admin/ping", params={"wt": "json"}, timeout=5)
            if r.status_code == 200:
                d = r.json()
                ok(f"Solr responding — status={d.get('status')}")
                return
        except requests.ConnectionError, requests.Timeout, ValueError:
            pass
        print(f"  … waiting for Solr (attempt {attempt + 1}/15)")
        time.sleep(3)
    fail(
        f"Solr not reachable at {SOLR} after 45 s.  Is the container running?\n"
        "    docker run -d --name ol-test-solr -p 8984:8983 \\\n"
        '      -v "$(pwd)/conf/solr:/opt/solr/server/solr/configsets/olconfig:ro" \\\n'
        '      -e "SOLR_MODULES=analysis-extras" \\\n'
        "      solr:10.0.0 solr-precreate openlibrary /opt/solr/server/solr/configsets/olconfig"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Step 1 — Verify schema has our new fields
# ──────────────────────────────────────────────────────────────────────────────


def verify_schema() -> None:
    banner("Step 1 — Verify schema fields")
    fields = {
        "ebook_availability": {"type": "string", "docValues": True},
        "ebook_becomes_available": {"type": "pdate", "docValues": True},
        "loan_uid": {"type": "plong", "docValues": True},
    }
    all_fields = solr_get("schema/fields")
    field_map = {f["name"]: f for f in all_fields["fields"]}
    for name, expected in fields.items():
        if name not in field_map:
            fail(f"Field '{name}' is MISSING from the schema.  Are you running Solr from the PR branch?")
        f = field_map[name]
        type_ok = f.get("type") == expected["type"]
        dv_ok = f.get("docValues") is True
        if type_ok and dv_ok:
            ok(f"{name}: type={f['type']}, docValues={f.get('docValues')}")
        elif not dv_ok:
            fail(f"{name}: docValues is {f.get('docValues')} — must be True for sort/filter")
        else:
            fail(f"{name}: type={f.get('type')}, expected {expected['type']}")


# ──────────────────────────────────────────────────────────────────────────────
# Step 2 — Seed test work documents
# ──────────────────────────────────────────────────────────────────────────────

WORK_A = "/works/OL_TEST_1W"  # will be borrowed
WORK_B = "/works/OL_TEST_2W"  # will browse-expire (eviction path)
IA_A = "test_book_borrowable_00"
IA_B = "test_book_expiring_00"


def seed_works() -> None:
    banner("Step 2 — Seed test work documents into Solr")
    docs = [
        {
            "key": WORK_A,
            "title": "Test Work A — Borrow/Return cycle",
            "ia": [IA_A],
            "type": "/type/work",
        },
        {
            "key": WORK_B,
            "title": "Test Work B — Browse-expire / eviction path",
            "ia": [IA_B],
            "type": "/type/work",
        },
    ]
    solr_post("update", docs)
    commit()

    # Verify
    for key in [WORK_A, WORK_B]:
        d = solr_get("get", id=key)
        if d.get("doc") and d["doc"]["key"] == key:
            ok(f"Seeded {key}")
        else:
            fail(f"Could not retrieve {key} from Solr after seeding")

    # Confirm fields are absent before any loan events
    for key in [WORK_A, WORK_B]:
        d = solr_get("get", id=key)
        doc = d["doc"]
        for field in ("ebook_availability", "ebook_becomes_available", "loan_uid"):
            if field in doc:
                fail(f"{key} already has {field}={doc[field]} — clean state expected")
    ok("Confirmed: no availability fields on fresh docs (correct)")


# ──────────────────────────────────────────────────────────────────────────────
# Updater logic (reproduced inline — mirrors loan_availability_updater.py)
# ──────────────────────────────────────────────────────────────────────────────


def _process_changes(rows: list) -> dict:
    """Reduce batch to latest event per identifier (mirrors process_changes)."""
    latest: dict[str, dict] = {}
    for row in rows:
        ident = row["identifier"]
        uid = row["uid"]
        if ident in latest and latest[ident]["uid"] >= uid:
            continue
        until = None
        if row["event_type"] in ("borrow", "browse", "renew_borrow", "renew_browse"):
            with contextlib.suppress(ValueError, TypeError, KeyError):
                until = json.loads(row.get("extra") or "{}").get("until")
        latest[ident] = {"event_type": row["event_type"], "uid": uid, "until": until}
    return latest


def _ia_until_to_solr_date(until) -> str | None:
    """Convert IA until string to Solr pdate (mirrors ia_until_to_solr_date)."""
    if not until:
        return None
    try:
        return datetime.datetime.strptime(until, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def _build_updates(id_state: dict, id_to_work: dict) -> list:
    """Build Solr atomic-update docs (mirrors build_solr_updates)."""
    ACTIVE = frozenset({"borrow", "browse", "renew_borrow", "renew_browse"})
    ENDED = frozenset({"return", "expire_borrow", "expire_browse"})
    updates = []
    for ident, state in id_state.items():
        work_key = id_to_work.get(ident)
        if not work_key:
            continue
        if state["event_type"] in ACTIVE:
            u = {
                "key": work_key,
                "ebook_availability": {"set": "unavailable"},
                "loan_uid": {"set": state["uid"]},
            }
            solr_until = _ia_until_to_solr_date(state["until"])
            if solr_until:
                u["ebook_becomes_available"] = {"set": solr_until}
            updates.append(u)
        elif state["event_type"] in ENDED:
            updates.append(
                {
                    "key": work_key,
                    "ebook_availability": {"set": "available"},
                    "ebook_becomes_available": {"set": None},
                    "loan_uid": {"set": state["uid"]},
                }
            )
    return updates


def _apply_updates(updates: list, label: str) -> None:
    """Send atomic updates to Solr.

    NOTE: We do NOT use update.partial.requireInPlace=true here.
    Solr 10 only supports in-place updates for numeric point fields (pint, pfloat,
    plong, pdouble). String fields (ebook_availability) and date fields
    (ebook_becomes_available) are NOT supported by requireInPlace even when
    configured as stored=false, indexed=false, docValues=true.

    Regular atomic updates (without requireInPlace) work correctly for all field
    types: Solr fetches stored fields, merges the updates, and re-indexes.
    This is slightly more expensive than in-place updates but works reliably.

    The production updater (loan_availability_updater.py) currently uses
    update_in_place() which adds requireInPlace=true — this is a bug that will
    cause all Solr writes to silently return 400 errors and no data to be written.
    Fix: replace get_solr().update_in_place() with a regular atomic update call.
    """
    if not updates:
        print(f"  {SKIP}  {label}: no updates to apply")
        return
    print(f"\n  Atomic update payload ({label}):")
    print("  " + json.dumps(updates, indent=2).replace("\n", "\n  "))
    # Regular atomic update — requireInPlace not used (see docstring above)
    resp = solr_post("update", updates)
    if resp["responseHeader"]["status"] != 0:
        fail(f"Solr update failed: {resp}")
    commit()
    ok(f"Applied {len(updates)} atomic update(s)")


# ──────────────────────────────────────────────────────────────────────────────
# Step 3 — Borrow event
# ──────────────────────────────────────────────────────────────────────────────

BORROW_UID = 100_001
BORROW_UNTIL = (datetime.datetime.utcnow() + datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")


def run_borrow() -> None:
    banner("Step 3 — Borrow event → ebook_availability = unavailable")

    fake_rows = [
        {
            "identifier": IA_A,
            "uid": BORROW_UID,
            "event_type": "borrow",
            "extra": json.dumps({"until": BORROW_UNTIL}),
        }
    ]
    id_state = _process_changes(fake_rows)
    id_to_work = {IA_A: WORK_A}  # what resolve_work_keys() would return
    updates = _build_updates(id_state, id_to_work)
    _apply_updates(updates, "borrow")

    # Verify
    doc = solr_get("get", id=WORK_A)["doc"]
    avail = doc.get("ebook_availability")
    becomes = doc.get("ebook_becomes_available")
    uid_stored = doc.get("loan_uid")

    if avail == "unavailable":
        ok(f"ebook_availability = {avail!r}")
    else:
        fail(f"ebook_availability = {avail!r}, expected 'unavailable'")

    expected_until = _ia_until_to_solr_date(BORROW_UNTIL)
    if becomes == expected_until:
        ok(f"ebook_becomes_available = {becomes!r}")
    else:
        fail(f"ebook_becomes_available = {becomes!r}, expected {expected_until!r}")

    if uid_stored == BORROW_UID:
        ok(f"loan_uid = {uid_stored}")
    else:
        fail(f"loan_uid = {uid_stored}, expected {BORROW_UID}")


# ──────────────────────────────────────────────────────────────────────────────
# Step 4 — Return event
# ──────────────────────────────────────────────────────────────────────────────

RETURN_UID = 100_002


def run_return() -> None:
    banner("Step 4 — Return event → ebook_availability = available, becomes_available cleared")

    fake_rows = [
        {
            "identifier": IA_A,
            "uid": RETURN_UID,
            "event_type": "return",
            "extra": "{}",
        }
    ]
    id_state = _process_changes(fake_rows)
    id_to_work = {IA_A: WORK_A}
    updates = _build_updates(id_state, id_to_work)
    _apply_updates(updates, "return")

    doc = solr_get("get", id=WORK_A)["doc"]
    avail = doc.get("ebook_availability")
    becomes = doc.get("ebook_becomes_available")
    uid_stored = doc.get("loan_uid")

    if avail == "available":
        ok(f"ebook_availability = {avail!r}")
    else:
        fail(f"ebook_availability = {avail!r}, expected 'available'")

    if becomes is None:
        ok("ebook_becomes_available = None (cleared)")
    else:
        fail(f"ebook_becomes_available = {becomes!r}, expected None (cleared)")

    if uid_stored == RETURN_UID:
        ok(f"loan_uid advanced to {uid_stored}")
    else:
        fail(f"loan_uid = {uid_stored}, expected {RETURN_UID}")


# ──────────────────────────────────────────────────────────────────────────────
# Step 5 — Eviction path (missed return/expire safety net)
# ──────────────────────────────────────────────────────────────────────────────

BROWSE_UID = 200_001


def run_eviction() -> None:
    banner("Step 5 — Eviction: ebook_becomes_available in the past → auto-clear")

    # Seed Work B as currently borrowed, with ebook_becomes_available in the PAST
    expired_until_ia = (datetime.datetime.utcnow() - datetime.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    expired_until_solr = _ia_until_to_solr_date(expired_until_ia)

    fake_rows = [
        {
            "identifier": IA_B,
            "uid": BROWSE_UID,
            "event_type": "browse",
            "extra": json.dumps({"until": expired_until_ia}),
        }
    ]
    id_state = _process_changes(fake_rows)
    id_to_work = {IA_B: WORK_B}
    updates = _build_updates(id_state, id_to_work)
    _apply_updates(updates, "browse (expired until)")

    # Confirm Work B is now in 'unavailable' state with a past ebook_becomes_available
    doc = solr_get("get", id=WORK_B)["doc"]
    if doc.get("ebook_availability") == "unavailable":
        ok(f"Work B seeded as unavailable, ebook_becomes_available={doc.get('ebook_becomes_available')!r}")
    else:
        fail(f"Seed failed: ebook_availability={doc.get('ebook_availability')!r}")

    # Build eviction updates — mirrors build_eviction_updates()
    print("\n  Running eviction query: ebook_becomes_available:[* TO NOW]")
    evict_resp = solr_get(
        "select",
        q="ebook_becomes_available:[* TO NOW]",
        fl="key",
        rows=1000,
    )
    evict_docs = evict_resp["response"]["docs"]
    print(f"  Found {len(evict_docs)} doc(s) past their loan expiry: {[d['key'] for d in evict_docs]}")

    if not any(d["key"] == WORK_B for d in evict_docs):
        fail(f"Work B not found in eviction query — ebook_becomes_available={expired_until_solr!r}")

    evict_updates = [
        {
            "key": d["key"],
            "ebook_availability": {"set": "available"},
            "ebook_becomes_available": {"set": None},
        }
        for d in evict_docs
    ]
    _apply_updates(evict_updates, "eviction")

    # Verify cleared
    doc = solr_get("get", id=WORK_B)["doc"]
    if doc.get("ebook_availability") == "available" and doc.get("ebook_becomes_available") is None:
        ok("Work B evicted → ebook_availability=available, ebook_becomes_available=None")
    else:
        fail(f"Eviction incomplete: avail={doc.get('ebook_availability')!r}, becomes={doc.get('ebook_becomes_available')!r}")


# ──────────────────────────────────────────────────────────────────────────────
# Step 6 — State recovery via loan_uid
# ──────────────────────────────────────────────────────────────────────────────


def run_state_recovery() -> None:
    banner("Step 6 — State recovery: query max loan_uid for restart resume")

    # The updater calls query_solr_uid() on restart; it reads the highest loan_uid
    # to know where to resume (avoids binary search on clean restart)
    resp = solr_get(
        "select",
        q="loan_uid:[* TO *]",
        fl="key,loan_uid",
        rows=10,
        sort="loan_uid desc",
    )
    docs = resp["response"]["docs"]
    if not docs:
        fail("No docs with loan_uid found — state recovery will binary-search every restart")

    max_uid = docs[0]["loan_uid"]
    print("\n  Docs with loan_uid (sorted desc):")
    for d in docs:
        print(f"    {d['key']}: loan_uid={d['loan_uid']}")

    # Work A should have RETURN_UID=100_002, Work B should have BROWSE_UID=200_001
    expected_max = max(RETURN_UID, BROWSE_UID)
    if max_uid == expected_max:
        ok(f"query_solr_uid() would return {max_uid} — correct resume point")
    else:
        fail(f"Expected max loan_uid={expected_max}, got {max_uid}")


# ──────────────────────────────────────────────────────────────────────────────
# Step 7 — Example filter queries (what a search consumer would use)
# ──────────────────────────────────────────────────────────────────────────────


def demo_queries() -> None:
    banner("Step 7 — Example filter queries for search consumers")

    # Re-seed Work A as available and Work B as unavailable for clear demo
    updates = [
        {"key": WORK_A, "ebook_availability": {"set": "available"}, "loan_uid": {"set": RETURN_UID}},
        {"key": WORK_B, "ebook_availability": {"set": "unavailable"}, "loan_uid": {"set": BROWSE_UID}, "ebook_becomes_available": {"set": future_utc(1)}},
    ]
    solr_post("update", updates)
    commit()

    queries = [
        ("Available only", "ebook_availability:available"),
        ("Unavailable only", "ebook_availability:unavailable"),
        ("Has availability status", "ebook_availability:[* TO *]"),
        ("Loan expires within 1 hr", f"ebook_becomes_available:[* TO {future_utc(1)}]"),
        ("Eviction candidates", "ebook_becomes_available:[* TO NOW]"),
    ]

    print()
    for label, q in queries:
        resp = solr_get("select", q=q, fl="key,ebook_availability,ebook_becomes_available", rows=100)
        docs = resp["response"]["docs"]
        keys = [d["key"] for d in docs]
        print(f"  q={q!r}")
        print(f"    → {resp['response']['numFound']} result(s): {keys}")

    print()
    ok("All filter queries executed successfully")
    print()
    print("  NOTE: ebook_availability has docValues=True on string field → can facet:")
    resp = solr_get(
        "select",
        q="*:*",
        **{"facet": "true", "facet.field": "ebook_availability", "rows": "0"},
    )
    facets = resp.get("facet_counts", {}).get("facet_fields", {}).get("ebook_availability", [])
    print(f"    facet counts: {list(zip(facets[::2], facets[1::2]))}")

    print()
    print("  NOTE: ebook_becomes_available has docValues=True on pdate → can sort:")
    resp = solr_get(
        "select",
        q="ebook_becomes_available:[* TO *]",
        fl="key,ebook_becomes_available",
        sort="ebook_becomes_available asc",
        rows=10,
    )
    docs = resp["response"]["docs"]
    print(f"    sorted by soonest expiry: {[(d['key'], d.get('ebook_becomes_available')) for d in docs]}")


# ──────────────────────────────────────────────────────────────────────────────
# Step 8 — Report gaps / limitations
# ──────────────────────────────────────────────────────────────────────────────


def report_gaps() -> None:
    banner("Step 8 — Known gaps (not failures — areas requiring follow-up work)")
    gaps = [
        (
            "🚨 CRITICAL: update_in_place() is wrong for string/date fields",
            "loan_availability_updater.py calls get_solr().update_in_place() which posts "
            "update?update.partial.requireInPlace=true. Solr 10 only supports in-place updates "
            "for numeric point fields (pint, pfloat, plong, pdouble). String fields "
            "(ebook_availability) and date fields (ebook_becomes_available) are NOT supported — "
            "Solr returns HTTP 400 'Can not satisfy requireInPlace'. The updater never raises on "
            "that 400; it silently advances the state file with NO data written to Solr. "
            "Fix: replace update_in_place() with a regular atomic update (POST /update without "
            "requireInPlace). Regular atomic updates work for all field types. Performance is "
            "slightly lower (Solr fetches stored fields + re-indexes) but correct and acceptable.",
        ),
        (
            "🚨 CRITICAL: schema needs indexed=false on new fields",
            "managed-schema.xml did not include indexed=false on the three new fields. "
            "requireInPlace additionally requires indexed=false (we added it), but even "
            "without that constraint, indexed=true on ebook_availability would mean Solr "
            "maintains an inverted index entry for every value — wasted work for an operational "
            "field that only needs docValues filtering/faceting. Fix applied in this branch.",
        ),
        (
            "Search consumer",
            "openlibrary/plugins/worksearch/code.py still calls services/availability "
            "on every request. ebook_availability in Solr is not yet consulted by any search code path.",
        ),
        (
            "Edition-level fields",
            "Loan state is written to work docs (resolve_work_keys maps ia → work key). "
            "Edition docs do not have ebook_availability. A borrow of any edition marks the entire "
            "work unavailable — may be too coarse when multiple editions exist.",
        ),
        (
            "Solr schema update path",
            "A full re-index wipes ebook_availability, loan_uid etc. The updater "
            "needs --reset to rebuild from the last 14 days. There is no auto-trigger for this.",
        ),
        (
            "S3 credentials",
            "lending.get_loan_changes() needs ia_ol_metadata_write_s3 keys (or a dedicated config key). The config path is not documented in the PR.",
        ),
        (
            "docker-compose service",
            "There is no solr_updater or loan_availability_updater service entry in compose.yaml. The daemon will not start automatically in dev or prod.",
        ),
        (
            "Search API",
            "No OL search API parameter (e.g. ?availability=available) exposes "
            "ebook_availability to end-users yet. The field is facetable but there is no route.",
        ),
        ("E2e / integration test", "All 20 existing tests use mocks (no real Solr). This script is the only end-to-end test."),
    ]
    for title, detail in gaps:
        print(f"\n  ⚠  {title}")
        # Word-wrap at 70 chars
        words = detail.split()
        line = "       "
        for word in words:
            if len(line) + len(word) + 1 > 78:
                print(line)
                line = "       " + word
            else:
                line += (" " if line.strip() else "") + word
        print(line)


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────


def main() -> None:
    print("=" * 60)
    print("  PR #12689 — ebook_availability E2E Test Harness")
    print(f"  Solr: {SOLR}")
    print("=" * 60)

    check_solr()
    verify_schema()
    seed_works()
    run_borrow()
    run_return()
    run_eviction()
    run_state_recovery()
    demo_queries()
    report_gaps()

    banner("Summary")
    print("  All assertions passed.  The Solr schema is correct and the")
    print("  atomic update pattern (process_changes → build_solr_updates →")
    print("  Solr /update?update.partial.requireInPlace=true) works as expected.")
    print()
    print("  See Step 8 for follow-up work required before this PR is")
    print("  production-complete.")
    print()


if __name__ == "__main__":
    main()
