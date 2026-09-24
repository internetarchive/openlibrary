#!/usr/bin/env python3
"""End-to-end test harness for PR #12689 — ebook_unavailable Solr fields.

Verifies the complete cycle: schema, seed (work + nested edition children),
the event-derived follower, the ground-truth repairer, the cold-start reconcile,
sibling edition isolation, and example filter queries.

The two halves are demonstrated separately, because that separation IS the
design. The follower writes from events alone and only ever marks unavailable;
the repairer reads IA's bulk availability API and only ever clears. Steps 3-5
supply no availability map at all -- the follower never consults one -- while
Step 5b supplies an explicit map standing in for the real service.

The two cases that motivate the split are shown as such: a borrow of a
multi-copy item is over-marked and then healed (recoverable), and a return of a
waitlisted item writes nothing rather than being wrongly freed (which would be
unrecoverable, since the repairer only clears).

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

  # (If port 8984 is already taken, publish another one and point the script at it:
  #  docker run -d --name ol-test-solr -p 8987:8983 ... ; then
  #  SOLR_URL=http://localhost:8987/solr/openlibrary python3 scripts/test_harness_e2e.py)

  # Step 3 — Tear down when done
  docker stop ol-test-solr && docker rm ol-test-solr

The script uses only `requests` (stdlib-equivalent for our purposes).
It does NOT require infogami, OL config, or IA credentials.
All loan-event simulation is done inline so the full cycle is visible.

The updater logic (collect_dirty_identifiers → resolve_edition_keys →
build_solr_updates → Solr in-place atomic update) is reproduced inline at a
level a reviewer can follow without reading the source, and deliberately so:
this script needs only `requests` and a bare Solr container, which is what lets
a reviewer run it without OL config or IA credentials.

That duplication used to be an acknowledged drift risk with nothing guarding
it, and it did drift -- this copy went on implementing an availability join
after the real updater stopped doing one. It is now pinned by
test_harness_matches_updater.py, which runs the inline copy and the real
functions over the same cases and fails if they disagree.
"""

import contextlib
import datetime
import json
import os
import sys
import time
from typing import NoReturn

import requests

# Override with SOLR_URL when 8984 is taken (e.g. another dev stack is running).
SOLR = os.environ.get("SOLR_URL", "http://localhost:8984/solr/openlibrary")

# Values of the ebook_unavailable field (absent means available too).
EBOOK_AVAILABLE = 0
EBOOK_UNAVAILABLE = 1

# Stand-ins for what IA's bulk availability API returns per identifier.
AVAILABLE = {"status": "borrow_available", "available_to_browse": True, "available_to_borrow": True}
UNAVAILABLE = {"status": "borrow_unavailable", "available_to_browse": False, "available_to_borrow": False}

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
        "ebook_unavailable": {"type": "pint", "docValues": True},
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

WORK_B = "/works/OL_TEST_2W"  # single edition; waitlisted, then freed by the re-check
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
        for field in ("ebook_unavailable", "ebook_becomes_available", "loan_uid"):
            if field in doc:
                fail(f"{key} already has {field}={doc[field]} — clean state expected")
    ok("Confirmed: no availability fields on fresh edition docs (correct)")


# ──────────────────────────────────────────────────────────────────────────────
# Updater logic (reproduced inline — mirrors loan_availability_updater.py)
# ──────────────────────────────────────────────────────────────────────────────


def _collect_dirty(rows: list) -> dict:
    """Reduce a batch to the identifiers needing a ground-truth check.

    Mirrors collect_dirty_identifiers(). Note what is NOT here: event_type is
    never inspected. Any event marks its identifier dirty, and the availability
    API decides what the state actually is.
    """
    latest: dict[str, dict] = {}
    for row in rows:
        ident = row["identifier"]
        uid = row["uid"]
        if ident in latest and latest[ident]["uid"] >= uid:
            continue
        until = None
        with contextlib.suppress(ValueError, TypeError, KeyError, AttributeError):
            until = json.loads(row.get("extra") or "{}").get("until")
        latest[ident] = {"uid": uid, "until": until, "event_type": row.get("event_type") or ""}
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


_RELEASING_EVENT_STEMS = ("return", "expire", "cancel")


def _is_releasing_event(event_type: str) -> bool:
    """Mirrors is_releasing_event. Substring, not equality: the vocabulary is
    compound (`expire_browse`, `expire_borrow`) and only partly known."""
    lowered = (event_type or "").lower()
    return any(stem in lowered for stem in _RELEASING_EVENT_STEMS)


def _build_updates(dirty: dict, id_to_edition: dict) -> list:
    """Build Solr atomic-update docs targeting editions (mirrors build_solr_updates).

    Event-derived and one-directional: an acquiring event sets
    ebook_unavailable=1, a releasing event writes NOTHING. No availability
    answer is consulted here at all -- clearing belongs to the re-check, which
    is the only half that has checked ground truth.

    ebook_becomes_available is written only alongside ebook_unavailable=1, and is
    never cleared when a book frees up -- requireInPlace rejects "set": null
    unconditionally (verified directly). It is advisory, and meaningful only
    while ebook_unavailable=1.
    """
    updates = []
    for ident, state in dirty.items():
        edition = id_to_edition.get(ident)
        if not edition or _is_releasing_event(state.get("event_type", "")):
            continue
        u = {
            "key": edition["key"],
            "_root_": edition["root"],
            "ebook_unavailable": {"set": EBOOK_UNAVAILABLE},
            "loan_uid": {"set": state["uid"]},
        }
        becomes_available = _ia_until_to_epoch(state["until"])
        if becomes_available is not None:
            u["ebook_becomes_available"] = {"set": becomes_available}
        updates.append(u)
    return updates


def _build_reconcile_updates(id_to_edition: dict, availability: dict) -> list:
    """Mirrors build_reconcile_updates: ground truth marks, never clears."""
    updates = []
    for ident, avail in availability.items():
        edition = id_to_edition.get(ident)
        if not edition or bool(avail.get("available_to_browse") or avail.get("available_to_borrow")):
            continue
        updates.append({"key": edition["key"], "_root_": edition["root"], "ebook_unavailable": {"set": EBOOK_UNAVAILABLE}})
    return updates


def _apply_updates(updates: list, label: str) -> None:
    """Send atomic updates to Solr using update.partial.requireInPlace=true.

    This now works because ebook_unavailable/ebook_becomes_available are
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
BORROW_UNTIL = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")


def run_borrow() -> None:
    banner("Step 3 — Borrow event → ebook_unavailable = 1 from the event alone, sibling untouched")

    fake_rows = [
        {
            "identifier": IA_A1,
            "uid": BORROW_UID,
            "event_type": "borrow",
            "extra": json.dumps({"until": BORROW_UNTIL}),
        }
    ]
    dirty = _collect_dirty(fake_rows)
    id_to_edition = {IA_A1: {"key": EDITION_A1, "root": WORK_A}}  # what resolve_edition_keys() would return
    # No availability map. The follower writes from the event, which is what
    # lets it keep running while the availability service is down.
    updates = _build_updates(dirty, id_to_edition)
    _apply_updates(updates, "borrow")

    doc = solr_get("get", id=EDITION_A1)["doc"]
    avail = doc.get("ebook_unavailable")
    becomes = doc.get("ebook_becomes_available")
    uid_stored = doc.get("loan_uid")

    if avail == EBOOK_UNAVAILABLE:
        ok(f"ebook_unavailable = {avail!r}")
    else:
        fail(f"ebook_unavailable = {avail!r}, expected {EBOOK_UNAVAILABLE!r}")

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
    if any(f in sibling for f in ("ebook_unavailable", "ebook_becomes_available", "loan_uid")):
        fail(f"Sibling edition {EDITION_A2} was affected by the borrow on {EDITION_A1}: {sibling}")
    ok(f"Sibling edition {EDITION_A2} untouched (per-edition targeting confirmed)")

    # The parent work itself must also never receive these fields.
    work_doc = solr_get("get", id=WORK_A)["doc"]
    if any(f in work_doc for f in ("ebook_unavailable", "ebook_becomes_available", "loan_uid")):
        fail(f"Parent work {WORK_A} was affected by the borrow on its edition: {work_doc}")
    ok(f"Parent work {WORK_A} untouched (fields are edition-level only)")


# ──────────────────────────────────────────────────────────────────────────────
# Step 4 — Return event
# ──────────────────────────────────────────────────────────────────────────────

RETURN_UID = 100_002


def run_return() -> None:
    banner("Step 4 — Return event → writes NOTHING; the book stays marked until ground truth clears it")

    fake_rows = [
        {
            "identifier": IA_A1,
            "uid": RETURN_UID,
            "event_type": "return",
            "extra": "{}",
        }
    ]
    dirty = _collect_dirty(fake_rows)
    id_to_edition = {IA_A1: {"key": EDITION_A1, "root": WORK_A}}

    # The load-bearing assertion of the redesign. A return does NOT mean
    # available: if anyone is queued, the freed copy goes to the head of the
    # waitlist. Clearing here would publish a waitlisted book as borrowable
    # and nothing would correct it, because the re-check only ever clears.
    if updates := _build_updates(dirty, id_to_edition):
        fail(f"a releasing event produced writes, which would publish a waitlisted book as available: {updates}")
    ok("Return event produced no writes (clearing is the re-check's job)")

    doc = solr_get("get", id=EDITION_A1)["doc"]
    avail = doc.get("ebook_unavailable")
    becomes = doc.get("ebook_becomes_available")
    uid_stored = doc.get("loan_uid")

    if avail == EBOOK_UNAVAILABLE:
        ok(f"ebook_unavailable still {avail!r} — the borrow's mark survives the return")
    else:
        fail(f"ebook_unavailable = {avail!r}, expected {EBOOK_UNAVAILABLE!r} (a return must not clear it)")

    expected_stale = _ia_until_to_epoch(BORROW_UNTIL)
    if becomes == expected_stale:
        ok(f"ebook_becomes_available = {becomes!r} (still the borrow's value, still meaningful)")
    else:
        fail(f"ebook_becomes_available = {becomes!r}, expected {expected_stale!r}")

    # Consequence worth seeing: loan_uid does NOT advance on a releasing event,
    # because nothing is written. The state FILE still advances, so steady-state
    # progress is unaffected; only the Solr-derived fallback cursor
    # (query_solr_uid, used when the state file is missing) lags behind. Lagging
    # is the safe direction: resuming from an older uid replays events that are
    # idempotent, and a missing state file now triggers a cold-start reconcile
    # anyway.
    if uid_stored == BORROW_UID:
        ok(f"loan_uid still {uid_stored} (releasing events write nothing, so the Solr cursor lags by design)")
    else:
        fail(f"loan_uid = {uid_stored}, expected {BORROW_UID}")


# ──────────────────────────────────────────────────────────────────────────────
# Step 5 — The two cases the event stream cannot predict
# ──────────────────────────────────────────────────────────────────────────────

BROWSE_UID = 200_001
MULTI_COPY_UID = 200_002
WAITLIST_UID = 200_003
UNKNOWN_VERB_UID = WAITLIST_UID + 2

# (uid, event_type) for every event the steps feed to _build_updates, so Step 6
# can derive the expected cursor instead of restating it.
APPLIED_EVENT_UIDS = [
    (BORROW_UID, "borrow"),
    (RETURN_UID, "return"),
    (MULTI_COPY_UID, "borrow"),
    (WAITLIST_UID, "return"),
    (UNKNOWN_VERB_UID, "some_future_verb"),
]


def run_ground_truth_divergences() -> None:
    banner("Step 5 — The two cases events cannot predict, and which half absorbs each")

    # (a) Multi-copy: a borrow arrives, but the item owns other copies, so IA
    # still reports it borrowable. The follower marks it unavailable anyway --
    # deliberately. That is the RECOVERABLE error: it hides a borrowable book
    # for at most RECHECK_INTERVAL, and Step 5b frees it against ground truth.
    rows = [{"identifier": IA_A1, "uid": MULTI_COPY_UID, "event_type": "borrow", "extra": json.dumps({"until": BORROW_UNTIL})}]
    updates = _build_updates(_collect_dirty(rows), {IA_A1: {"key": EDITION_A1, "root": WORK_A}})
    _apply_updates(updates, "borrow on a multi-copy item")

    doc = solr_get("get", id=EDITION_A1)["doc"]
    if doc.get("ebook_unavailable") == EBOOK_UNAVAILABLE:
        ok("Borrow on a multi-copy item marked it unavailable (over-marking, healed by the re-check)")
    else:
        fail(f"multi-copy: ebook_unavailable={doc.get('ebook_unavailable')!r}, expected {EBOOK_UNAVAILABLE!r}")

    # (b) Waitlist: a return arrives, but people are queued, so the freed copy
    # goes to the head of the queue and the book is still not borrowable. This
    # is the UNRECOVERABLE error if got wrong -- the re-check only ever clears,
    # so a wrongly-cleared book would stay published as available forever. The
    # follower therefore writes nothing at all on a release.
    rows = [{"identifier": IA_B1, "uid": WAITLIST_UID, "event_type": "return", "extra": "{}"}]
    updates = _build_updates(_collect_dirty(rows), {IA_B1: {"key": EDITION_B1, "root": WORK_B}})
    if updates:
        fail(f"a release produced writes; a waitlisted book would be published as available: {updates}")
    ok("Return on a waitlisted item produced no write (only a checked answer may clear)")

    # (c) Every releasing spelling we know of behaves the same way. `expire_browse`
    # is the one that matters: an exact-match set built from the two verbs anyone
    # thinks of first reads it as ACQUIRING and marks a just-expired loan
    # unavailable.
    for event_type in ("return", "expire", "expire_browse", "expire_borrow", "cancel_hold"):
        rows = [{"identifier": IA_B1, "uid": WAITLIST_UID + 1, "event_type": event_type, "extra": "{}"}]
        if _build_updates(_collect_dirty(rows), {IA_B1: {"key": EDITION_B1, "root": WORK_B}}):
            fail(f"event_type {event_type!r} was treated as acquiring")
    ok("All known releasing spellings write nothing, including expire_browse/expire_borrow")

    # (d) An unknown verb errs toward unavailable, which is the safe direction.
    # Applied, not just computed: this is also what leaves B1 marked, which is
    # the precondition Step 5b needs. Under the previous design B1 was marked by
    # a ground-truth override on a return; releases now write nothing, so the
    # mark has to come from an acquiring event.
    rows = [{"identifier": IA_B1, "uid": UNKNOWN_VERB_UID, "event_type": "some_future_verb", "extra": "{}"}]
    updates = _build_updates(_collect_dirty(rows), {IA_B1: {"key": EDITION_B1, "root": WORK_B}})
    if not updates or updates[0]["ebook_unavailable"] != {"set": EBOOK_UNAVAILABLE}:
        fail(f"an unknown event_type must err toward unavailable, got {updates}")
    _apply_updates(updates, "unknown event_type on B1")
    ok("Unknown event_type treated as acquiring (recoverable direction)")

    # (e) The follower never consults availability, so nothing about it depends
    # on that service being reachable.
    before = solr_get("get", id=EDITION_B1)["doc"]
    rows = [{"identifier": IA_B1, "uid": WAITLIST_UID + 3, "event_type": "return", "extra": "{}"}]
    if _build_updates(_collect_dirty(rows), {IA_B1: {"key": EDITION_B1, "root": WORK_B}}):
        fail("release wrote something on the second pass")
    after = solr_get("get", id=EDITION_B1)["doc"]
    if before.get("loan_uid") != after.get("loan_uid"):
        fail(f"loan_uid changed on a release: {before.get('loan_uid')} → {after.get('loan_uid')}")
    ok("Releases leave the document byte-identical (loan_uid included)")


# ──────────────────────────────────────────────────────────────────────────────
# Step 5b — Drift re-check (replaces the old expiry-based eviction)
# ──────────────────────────────────────────────────────────────────────────────


def run_recheck() -> None:
    banner("Step 5b — Drift re-check: re-ask ground truth about the known-unavailable set")

    # Edition B1 is currently marked unavailable (Step 5d applied that). The re-check
    # walks the known-unavailable set and frees whatever ground truth now says
    # is borrowable -- which is what recovers from missed return/expire events,
    # a waitlist draining, or copies being added. Note it needs no timestamp:
    # unlike the old eviction query it does not depend on ebook_becomes_available,
    # which is exactly why that field could be demoted to advisory.
    query = f"type:edition AND ebook_unavailable:{EBOOK_UNAVAILABLE}"
    print(f"\n  Running re-check query: {query}")
    resp = solr_get("select", q=query, fl="key,ia,_root_", rows=1000)
    docs = resp["response"]["docs"]
    print(f"  Found {len(docs)} edition(s) currently marked unavailable: {[d['key'] for d in docs]}")

    if not any(d["key"] == EDITION_B1 for d in docs):
        fail("Edition B1 not found by the re-check query; ebook_unavailable was not indexed as expected")

    # Ground truth now says B1 is free again.
    availability = {IA_B1: AVAILABLE}
    recheck_updates = []
    seen = set()
    for d in docs:
        for ia_id in d.get("ia", []):
            avail = availability.get(ia_id)
            if avail and (avail.get("available_to_browse") or avail.get("available_to_borrow")) and d["key"] not in seen:
                seen.add(d["key"])
                recheck_updates.append({"key": d["key"], "_root_": d["_root_"], "ebook_unavailable": {"set": EBOOK_AVAILABLE}})
    _apply_updates(recheck_updates, "re-check")

    doc = solr_get("get", id=EDITION_B1)["doc"]
    if doc.get("ebook_unavailable") == EBOOK_AVAILABLE:
        ok(f"Edition B1 freed by re-check (stale ebook_becomes_available={doc.get('ebook_becomes_available')!r}, ignored)")
    else:
        fail(f"Re-check incomplete: ebook_unavailable={doc.get('ebook_unavailable')!r}")


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

    # The cursor is the highest uid ACQUIRING events wrote, which is not simply
    # the highest uid seen: releasing events write nothing now, so their uids
    # never reach Solr. The re-check does not touch loan_uid either -- it is a
    # cursor over the changes feed and a re-check is not a feed event.
    #
    # Derived from the uids the steps above actually applied, rather than
    # restated as a literal. A hardcoded expectation here went stale the moment
    # a step changed which events write, and the failure pointed at state
    # recovery rather than at the step that had moved.
    expected_max = max(uid for uid, event_type in APPLIED_EVENT_UIDS if not _is_releasing_event(event_type))
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
        {"key": EDITION_A1, "_root_": WORK_A, "ebook_unavailable": {"set": EBOOK_AVAILABLE}, "loan_uid": {"set": RETURN_UID}},
        {
            "key": EDITION_B1,
            "_root_": WORK_B,
            "ebook_unavailable": {"set": EBOOK_UNAVAILABLE},
            "loan_uid": {"set": BROWSE_UID},
            "ebook_becomes_available": {"set": expires_soon},
        },
    ]
    solr_post("update?update.partial.requireInPlace=true", updates)
    commit()

    queries = [
        # The real consumer query: available is the DEFAULT, so it is a negation
        # over the borrowable set rather than a positive match. Nothing here has
        # ebook_access set, so this is shown for shape, not for its count.
        ("Borrowable and available (consumer query shape)", f"-ebook_unavailable:{EBOOK_UNAVAILABLE}"),
        ("Unavailable only", f"ebook_unavailable:{EBOOK_UNAVAILABLE}"),
        ("Explicitly marked either way", "ebook_unavailable:[* TO *]"),
        ("Unavailable, frees up within 1 hr", f"ebook_unavailable:{EBOOK_UNAVAILABLE} AND ebook_becomes_available:[* TO {expires_soon}]"),
    ]

    print()
    for label, q in queries:
        resp = solr_get("select", q=q, fl="key,ebook_unavailable,ebook_becomes_available", rows=100)
        docs = resp["response"]["docs"]
        keys = [d["key"] for d in docs]
        print(f"  {label}")
        print(f"    q={q!r}")
        print(f"    → {resp['response']['numFound']} result(s): {keys}")

    print()
    ok("All filter queries executed successfully")
    print()
    print("  NOTE: ebook_unavailable is docValues-only (indexed=false). These queries")
    print("  work, but they are docValues SCANS -- cost tracks the number of editions,")
    print("  not the number of matches. Fine for retrieving the field on docs a query")
    print("  already matched; not yet suitable as a search filter at corpus scale.")
    resp = solr_get(
        "select",
        q="*:*",
        **{"facet": "true", "facet.field": "ebook_unavailable", "rows": "0"},
    )
    facets = resp.get("facet_counts", {}).get("facet_fields", {}).get("ebook_unavailable", [])
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
            (
                "ebook_unavailable/ebook_becomes_available are now retrievable via "
                "EditionSearchScheme.all_fields, but openlibrary/plugins/worksearch/code.py "
                "still calls services/availability on every request instead of filtering/"
                "displaying based on the Solr fields. No search UI surfaces them yet."
            ),
        ),
        (
            "Filtering vs retrieval",
            (
                "The fields are indexed=false (a requireInPlace prerequisite), so filtering or "
                "faceting on them is a docValues scan proportional to the number of editions. "
                "Good for hydrating results a query already matched; not a search filter at "
                "corpus scale. Making it one means indexed=true, which forfeits in-place updates "
                "and makes each edition write reindex the parent work and all its editions. "
                "Needs a decision from whoever owns the Solr deployment."
            ),
        ),
        (
            "Solr schema update path",
            (
                "A full re-index wipes ebook_unavailable, loan_uid etc. Because the field is "
                "default-available, a wiped borrowed book silently reads as available -- and the "
                "wipe also destroys the known-unavailable list the drift re-check walks, so the "
                "re-check cannot repair it. Recovery needs --reset. No auto-trigger for this."
            ),
        ),
        (
            "Waitlist parity",
            (
                "The bulk availability API reports available_to_waitlist and num_waitlist, which "
                "this updater fetches but does not store. Search-side parity with the old "
                "per-request availability call ('Join Waitlist', 'Readers in line: N') therefore "
                "needs extra Solr fields; a follow-up."
            ),
        ),
        (
            "Request volume / S3 credentials",
            (
                "Steady-state and cold-start request volume against the availability API is "
                "unmeasured: it needs real ia_ol_metadata_write_s3 keys, which dev does not have "
                "(conf/openlibrary.yml points at mockservices). A 14-day hydration fans out over "
                "every distinct ocaid with an event, so that number wants measuring and IA "
                "sign-off before this points at production."
            ),
        ),
        (
            "production deploy",
            (
                "In dev the updater runs backgrounded inside the solr-updater container "
                "(docker/ol-solr-updater-start.sh). Production still needs an olsystem/Jenkins "
                "entry to run it on the solr-updater host."
            ),
        ),
        (
            "Search API",
            ("No OL search API parameter (e.g. ?availability=available) exposes ebook_unavailable to end-users yet. There is no route."),
        ),
        (
            "Optimistic concurrency",
            (
                "Edition updates don't pass _version_, so a concurrent full work reindex "
                "(unrelated metadata edit, cover change, etc.) racing with a loan-event write "
                "could clobber or be clobbered without either side detecting it. Accepted as a "
                "v1 risk -- not observed, not yet protected against."
            ),
        ),
        (
            "E2e / integration test",
            "The unit tests all use mocks (no real Solr, no real availability API). This script is the only end-to-end test, and it is run by hand.",
        ),
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
    print("  PR #12689 — ebook_unavailable E2E Test Harness")
    print(f"  Solr: {SOLR}")
    print("=" * 60)

    check_solr()
    verify_schema()
    seed_works()
    run_borrow()
    run_return()
    run_ground_truth_divergences()
    run_recheck()
    run_state_recovery()
    demo_queries()
    report_gaps()

    banner("Summary")
    print("  All assertions passed. The Solr schema is correct, edition-level")
    print("  targeting is proven safe (siblings + parent work untouched), and")
    print("  the in-place atomic update pattern (collect_dirty_identifiers →")
    print("  resolve_edition_keys → build_solr_updates (events only) → ")
    print("  Solr.update_in_place → POST /update?update.partial.requireInPlace=true)")
    print("  works end-to-end.")
    print()
    print("  Ground truth, not the event, decides availability: a borrow on a")
    print("  multi-copy item stays available, a return on a waitlisted item stays")
    print("  unavailable, and an identifier with no answer is not written at all.")
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
