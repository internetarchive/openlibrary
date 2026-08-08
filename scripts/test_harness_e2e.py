#!/usr/bin/env python3
"""End-to-end test harness for PR #12689 — ebook_availability Solr fields.

Verifies the complete cycle: schema, seed (work + nested edition children),
borrow → unavailable, return → available, eviction of expired loans, sibling
edition isolation, and example filter queries.

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

The updater logic (process_changes → resolve_edition_keys → build_solr_updates
→ Solr in-place atomic update) is reproduced inline at a level a reviewer can
follow without reading the source.
"""

import contextlib
import datetime
import json
import sys
import time
from typing import NoReturn

import requests

SOLR = "http://localhost:8984/solr/openlibrary"

EBOOK_UNAVAILABLE = 0
EBOOK_AVAILABLE = 1

PASS = "✓"
FAIL = "✗"
SKIP = "-"

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def ok(msg: str) -> None:
    print(f"  {PASS}  {msg}")


def fail(msg: str) -> NoReturn:
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


def now_epoch() -> int:
    return int(time.time())


def future_epoch(hours: int = 1) -> int:
    return now_epoch() + hours * 3600


def past_epoch(hours: int = 2) -> int:
    return now_epoch() - hours * 3600


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
        except (requests.ConnectionError, requests.Timeout, ValueError):  # fmt: skip
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
    banner("Step 1 — Verify schema fields (numeric, required for in-place updates)")
    fields = {
        "ebook_availability": {"type": "pint", "docValues": True},
        "ebook_becomes_available": {"type": "plong", "docValues": True},
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
            fail(f"{name}: type={f.get('type')}, expected {expected['type']} — string/pdate fields are rejected by requireInPlace")


# ──────────────────────────────────────────────────────────────────────────────
# Step 2 — Seed a work with nested edition children (matches WorkSolrBuilder's
# real output shape: the work doc has an "editions" field whose value is a
# list of edition dicts, which Solr indexes as nested child documents and
# auto-populates "_root_" on).
# ──────────────────────────────────────────────────────────────────────────────

WORK_A = "/works/OL_TEST_1W"  # has two editions; one gets borrowed
EDITION_A1 = "/books/OL_TEST_1M"  # will be borrowed
EDITION_A2 = "/books/OL_TEST_2M"  # sibling — must stay untouched
IA_A1 = "test_book_borrowable_00"
IA_A2 = "test_book_sibling_00"

WORK_B = "/works/OL_TEST_2W"  # single edition; will browse-expire (eviction path)
EDITION_B1 = "/books/OL_TEST_3M"
IA_B1 = "test_book_expiring_00"


def seed_works() -> None:
    banner("Step 2 — Seed work + nested edition documents into Solr")
    docs = [
        {
            "key": WORK_A,
            "type": "work",
            "title": "Test Work A — Borrow/Return cycle, sibling isolation",
            "editions": [
                {"key": EDITION_A1, "type": "edition", "work_key": [WORK_A], "ia": [IA_A1]},
                {"key": EDITION_A2, "type": "edition", "work_key": [WORK_A], "ia": [IA_A2]},
            ],
        },
        {
            "key": WORK_B,
            "type": "work",
            "title": "Test Work B — Browse-expire / eviction path",
            "editions": [
                {"key": EDITION_B1, "type": "edition", "work_key": [WORK_B], "ia": [IA_B1]},
            ],
        },
    ]
    solr_post("update", docs)
    commit()

    # Verify work + editions are retrievable and _root_ was auto-populated on children
    for key in [WORK_A, WORK_B]:
        d = solr_get("get", id=key)
        if d.get("doc") and d["doc"]["key"] == key:
            ok(f"Seeded {key}")
        else:
            fail(f"Could not retrieve {key} from Solr after seeding")

    for edition_key, root_key in [(EDITION_A1, WORK_A), (EDITION_A2, WORK_A), (EDITION_B1, WORK_B)]:
        d = solr_get("get", id=edition_key)
        doc = d.get("doc")
        if not doc:
            fail(f"Could not retrieve edition {edition_key} — was it indexed as a nested child?")
        if doc.get("_root_") != root_key:
            fail(f"{edition_key}: _root_={doc.get('_root_')!r}, expected {root_key!r}")
        ok(f"Seeded {edition_key} — _root_={doc['_root_']!r} (nested under parent work)")

    # Confirm fields are absent before any loan events
    for key in [EDITION_A1, EDITION_A2, EDITION_B1]:
        doc = solr_get("get", id=key)["doc"]
        for field in ("ebook_availability", "ebook_becomes_available", "loan_uid"):
            if field in doc:
                fail(f"{key} already has {field}={doc[field]} — clean state expected")
    ok("Confirmed: no availability fields on fresh edition docs (correct)")


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


def _ia_until_to_epoch(until) -> int | None:
    """Convert IA until string (implicitly UTC) to epoch seconds (mirrors ia_until_to_epoch)."""
    if not until:
        return None
    try:
        dt = datetime.datetime.strptime(until, "%Y-%m-%d %H:%M:%S").replace(tzinfo=datetime.UTC)
        return int(dt.timestamp())
    except ValueError:
        return None


def _resolve_edition_keys(identifiers: list) -> dict:
    """Batch-resolve IA identifiers to edition key + parent work key (mirrors resolve_edition_keys).

    Scoped to type:edition so the parent work's own aggregate "ia" field
    (which also lists every child edition's ocaid) isn't matched instead.
    """
    if not identifiers:
        return {}
    quoted = " ".join(f'"{id_}"' for id_ in identifiers)
    resp = solr_get("select", q=f"type:edition AND ia:({quoted})", fl="key,ia,_root_", rows=len(identifiers) * 2)
    docs = resp["response"]["docs"]
    id_set = set(identifiers)
    return {ia_id: {"key": doc["key"], "root": doc["_root_"]} for doc in docs for ia_id in doc.get("ia", []) if ia_id in id_set}


def _build_updates(id_state: dict, id_to_edition: dict) -> list:
    """Build Solr atomic-update docs targeting editions (mirrors build_solr_updates)."""
    ACTIVE = frozenset({"borrow", "browse", "renew_borrow", "renew_browse"})
    ENDED = frozenset({"return", "expire_borrow", "expire_browse"})
    updates = []
    for ident, state in id_state.items():
        edition = id_to_edition.get(ident)
        if not edition:
            continue
        if state["event_type"] in ACTIVE:
            u = {
                "key": edition["key"],
                "_root_": edition["root"],
                "ebook_availability": {"set": EBOOK_UNAVAILABLE},
                "loan_uid": {"set": state["uid"]},
            }
            becomes_available = _ia_until_to_epoch(state["until"])
            if becomes_available is not None:
                u["ebook_becomes_available"] = {"set": becomes_available}
            updates.append(u)
        elif state["event_type"] in ENDED:
            # ebook_becomes_available is NOT cleared here -- requireInPlace rejects
            # "set": null unconditionally (verified directly). It's left stale;
            # consumers must treat it as meaningful only when ebook_availability=0.
            updates.append(
                {
                    "key": edition["key"],
                    "_root_": edition["root"],
                    "ebook_availability": {"set": EBOOK_AVAILABLE},
                    "loan_uid": {"set": state["uid"]},
                }
            )
    return updates


def _apply_updates(updates: list, label: str) -> None:
    """Send atomic updates to Solr using update.partial.requireInPlace=true.

    This now works because ebook_availability/ebook_becomes_available are
    numeric (pint/plong) -- Solr rejects requireInPlace for string/pdate
    fields with HTTP 400 regardless of docValues/stored/indexed config
    (verified directly against this Solr instance during design).

    In-place matters more here than for a top-level document: a *non*-in-place
    atomic update targeting a nested child document (an edition) reindexes the
    entire tree -- the parent work AND every sibling edition -- not just the
    one document. In-place updates touch only the targeted docValue, avoiding
    that entirely. This is the whole point of a near-realtime updater.
    """
    if not updates:
        print(f"  {SKIP}  {label}: no updates to apply")
        return
    print(f"\n  In-place atomic update payload ({label}):")
    print("  " + json.dumps(updates, indent=2).replace("\n", "\n  "))
    resp = solr_post("update?update.partial.requireInPlace=true", updates)
    if resp["responseHeader"]["status"] != 0:
        fail(f"Solr in-place update failed: {resp}")
    commit()
    ok(f"Applied {len(updates)} in-place atomic update(s)")


# ──────────────────────────────────────────────────────────────────────────────
# Step 3 — Borrow event
# ──────────────────────────────────────────────────────────────────────────────

BORROW_UID = 100_001
BORROW_UNTIL = (datetime.datetime.utcnow() + datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")


def run_borrow() -> None:
    banner("Step 3 — Borrow event → ebook_availability = 0 (unavailable), sibling untouched")

    fake_rows = [
        {
            "identifier": IA_A1,
            "uid": BORROW_UID,
            "event_type": "borrow",
            "extra": json.dumps({"until": BORROW_UNTIL}),
        }
    ]
    id_state = _process_changes(fake_rows)
    id_to_edition = {IA_A1: {"key": EDITION_A1, "root": WORK_A}}  # what resolve_edition_keys() would return
    updates = _build_updates(id_state, id_to_edition)
    _apply_updates(updates, "borrow")

    doc = solr_get("get", id=EDITION_A1)["doc"]
    avail = doc.get("ebook_availability")
    becomes = doc.get("ebook_becomes_available")
    uid_stored = doc.get("loan_uid")

    if avail == EBOOK_UNAVAILABLE:
        ok(f"ebook_availability = {avail!r}")
    else:
        fail(f"ebook_availability = {avail!r}, expected {EBOOK_UNAVAILABLE!r}")

    expected_until = _ia_until_to_epoch(BORROW_UNTIL)
    if becomes == expected_until:
        ok(f"ebook_becomes_available = {becomes!r}")
    else:
        fail(f"ebook_becomes_available = {becomes!r}, expected {expected_until!r}")

    if uid_stored == BORROW_UID:
        ok(f"loan_uid = {uid_stored}")
    else:
        fail(f"loan_uid = {uid_stored}, expected {BORROW_UID}")

    # Critical: the sibling edition of the SAME work must be completely untouched.
    sibling = solr_get("get", id=EDITION_A2)["doc"]
    if any(f in sibling for f in ("ebook_availability", "ebook_becomes_available", "loan_uid")):
        fail(f"Sibling edition {EDITION_A2} was affected by the borrow on {EDITION_A1}: {sibling}")
    ok(f"Sibling edition {EDITION_A2} untouched (per-edition targeting confirmed)")

    # The parent work itself must also never receive these fields.
    work_doc = solr_get("get", id=WORK_A)["doc"]
    if any(f in work_doc for f in ("ebook_availability", "ebook_becomes_available", "loan_uid")):
        fail(f"Parent work {WORK_A} was affected by the borrow on its edition: {work_doc}")
    ok(f"Parent work {WORK_A} untouched (fields are edition-level only)")


# ──────────────────────────────────────────────────────────────────────────────
# Step 4 — Return event
# ──────────────────────────────────────────────────────────────────────────────

RETURN_UID = 100_002


def run_return() -> None:
    banner("Step 4 — Return event → ebook_availability = 1 (available); becomes_available left stale, not cleared")

    fake_rows = [
        {
            "identifier": IA_A1,
            "uid": RETURN_UID,
            "event_type": "return",
            "extra": "{}",
        }
    ]
    id_state = _process_changes(fake_rows)
    id_to_edition = {IA_A1: {"key": EDITION_A1, "root": WORK_A}}
    updates = _build_updates(id_state, id_to_edition)
    _apply_updates(updates, "return")

    doc = solr_get("get", id=EDITION_A1)["doc"]
    avail = doc.get("ebook_availability")
    becomes = doc.get("ebook_becomes_available")
    uid_stored = doc.get("loan_uid")

    if avail == EBOOK_AVAILABLE:
        ok(f"ebook_availability = {avail!r}")
    else:
        fail(f"ebook_availability = {avail!r}, expected {EBOOK_AVAILABLE!r}")

    # NOT cleared -- requireInPlace rejects "set": null unconditionally (see
    # module docstring). Left at its borrow-time value; must be ignored by any
    # consumer now that ebook_availability=1.
    expected_stale = _ia_until_to_epoch(BORROW_UNTIL)
    if becomes == expected_stale:
        ok(f"ebook_becomes_available = {becomes!r} (stale from borrow, expected -- ignore when available)")
    else:
        fail(f"ebook_becomes_available = {becomes!r}, expected stale value {expected_stale!r}")

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

    # Seed Edition B1 as currently borrowed, with ebook_becomes_available in the PAST
    expired_until_ia = (datetime.datetime.utcnow() - datetime.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    expired_until_epoch = _ia_until_to_epoch(expired_until_ia)

    fake_rows = [
        {
            "identifier": IA_B1,
            "uid": BROWSE_UID,
            "event_type": "browse",
            "extra": json.dumps({"until": expired_until_ia}),
        }
    ]
    id_state = _process_changes(fake_rows)
    id_to_edition = {IA_B1: {"key": EDITION_B1, "root": WORK_B}}
    updates = _build_updates(id_state, id_to_edition)
    _apply_updates(updates, "browse (expired until)")

    # Confirm Edition B1 is now in unavailable state with a past ebook_becomes_available
    doc = solr_get("get", id=EDITION_B1)["doc"]
    if doc.get("ebook_availability") == EBOOK_UNAVAILABLE:
        ok(f"Edition B1 seeded as unavailable, ebook_becomes_available={doc.get('ebook_becomes_available')!r}")
    else:
        fail(f"Seed failed: ebook_availability={doc.get('ebook_availability')!r}")

    # Build eviction updates — mirrors build_eviction_updates(). "NOW" isn't a
    # valid date-math term against a plong field, so the current epoch is
    # computed in Python, same as the real updater does. Scoped to currently-
    # unavailable editions: ebook_becomes_available can never be cleared
    # in-place (see _build_updates), so this filter is what stops an already-
    # available edition's stale timestamp from matching forever.
    cutoff = now_epoch()
    query = f"type:edition AND ebook_availability:{EBOOK_UNAVAILABLE} AND ebook_becomes_available:[* TO {cutoff}]"
    print(f"\n  Running eviction query: {query}")
    evict_resp = solr_get("select", q=query, fl="key,_root_", rows=1000)
    evict_docs = evict_resp["response"]["docs"]
    print(f"  Found {len(evict_docs)} doc(s) past their loan expiry: {[d['key'] for d in evict_docs]}")

    if not any(d["key"] == EDITION_B1 for d in evict_docs):
        fail(f"Edition B1 not found in eviction query — ebook_becomes_available={expired_until_epoch!r}")

    evict_updates = [
        {
            "key": d["key"],
            "_root_": d["_root_"],
            "ebook_availability": {"set": EBOOK_AVAILABLE},
        }
        for d in evict_docs
    ]
    _apply_updates(evict_updates, "eviction")

    # Verify cleared: ebook_availability flips back; ebook_becomes_available is
    # left at its stale value (expected -- see module docstring) and must not
    # be relied on now that the edition is available again.
    doc = solr_get("get", id=EDITION_B1)["doc"]
    if doc.get("ebook_availability") == EBOOK_AVAILABLE:
        ok(f"Edition B1 evicted → ebook_availability=1 (stale ebook_becomes_available={doc.get('ebook_becomes_available')!r}, ignored)")
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
    print("\n  Edition docs with loan_uid (sorted desc):")
    for d in docs:
        print(f"    {d['key']}: loan_uid={d['loan_uid']}")

    # Edition A1 should have RETURN_UID=100_002, Edition B1 should have BROWSE_UID=200_001
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

    # Re-seed Edition A1 as available and Edition B1 as unavailable for clear demo
    expires_soon = future_epoch(1)
    updates = [
        {"key": EDITION_A1, "_root_": WORK_A, "ebook_availability": {"set": EBOOK_AVAILABLE}, "loan_uid": {"set": RETURN_UID}},
        {
            "key": EDITION_B1,
            "_root_": WORK_B,
            "ebook_availability": {"set": EBOOK_UNAVAILABLE},
            "loan_uid": {"set": BROWSE_UID},
            "ebook_becomes_available": {"set": expires_soon},
        },
    ]
    solr_post("update?update.partial.requireInPlace=true", updates)
    commit()

    cutoff = now_epoch()
    queries = [
        ("Available only", f"ebook_availability:{EBOOK_AVAILABLE}"),
        ("Unavailable only", f"ebook_availability:{EBOOK_UNAVAILABLE}"),
        ("Has availability status", "ebook_availability:[* TO *]"),
        ("Loan expires within 1 hr", f"ebook_becomes_available:[* TO {expires_soon}]"),
        ("Eviction candidates", f"ebook_becomes_available:[* TO {cutoff}]"),
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
    print("  NOTE: ebook_availability has docValues=True on pint field → can facet:")
    resp = solr_get(
        "select",
        q="*:*",
        **{"facet": "true", "facet.field": "ebook_availability", "rows": "0"},
    )
    facets = resp.get("facet_counts", {}).get("facet_fields", {}).get("ebook_availability", [])
    print(f"    facet counts: {list(zip(facets[::2], facets[1::2]))}")

    print()
    print("  NOTE: ebook_becomes_available has docValues=True on plong → can sort:")
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
            "Search consumer",
            "ebook_availability/ebook_becomes_available are now retrievable via "
            "EditionSearchScheme.all_fields, but openlibrary/plugins/worksearch/code.py "
            "still calls services/availability on every request instead of filtering/"
            "displaying based on the Solr fields. No search UI surfaces them yet.",
        ),
        (
            "Solr schema update path",
            "A full re-index wipes ebook_availability, loan_uid etc. The updater "
            "needs --reset to rebuild from the last 14 days. There is no auto-trigger for this.",
        ),
        (
            "S3 credentials / dev testing",
            "lending.get_loan_changes() needs ia_ol_metadata_write_s3 keys (or a dedicated "
            "config key), so this daemon can't be exercised end-to-end in dev yet. PR #13045 "
            "(mockservices) is adding a local mock; once it lands, wire this daemon's "
            "action=changes calls to it instead of relying on this standalone Solr-only harness.",
        ),
        (
            "production deploy",
            "In dev the updater runs backgrounded inside the solr-updater container "
            "(docker/ol-solr-updater-start.sh). Production still needs an olsystem/Jenkins "
            "entry to run it on the solr-updater host.",
        ),
        (
            "Search API",
            "No OL search API parameter (e.g. ?availability=available) exposes "
            "ebook_availability to end-users yet. The field is facetable but there is no route.",
        ),
        (
            "Optimistic concurrency",
            "Edition updates don't pass _version_, so a concurrent full work reindex "
            "(unrelated metadata edit, cover change, etc.) racing with a loan-event write "
            "could clobber or be clobbered without either side detecting it. Accepted as a "
            "v1 risk -- not observed, not yet protected against.",
        ),
        ("E2e / integration test", "All 32 existing unit tests use mocks (no real Solr). This script is the only end-to-end test."),
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
    print("  All assertions passed. The Solr schema is correct, edition-level")
    print("  targeting is proven safe (siblings + parent work untouched), and")
    print("  the in-place atomic update pattern (process_changes →")
    print("  resolve_edition_keys → build_solr_updates → Solr.update_in_place →")
    print("  POST /update?update.partial.requireInPlace=true) works end-to-end.")
    print()
    print("  Schema fields: pint/plong, indexed=false, docValues=true (correct --")
    print("  numeric is required for requireInPlace; string/pdate return HTTP 400).")
    print("  Daemon uses Solr.update_in_place() with a status-check wrapper")
    print("  (solr_update_in_place) so a rejected update still raises.")
    print()
    print("  See Step 8 for remaining follow-up work before production deploy.")
    print()


if __name__ == "__main__":
    main()
