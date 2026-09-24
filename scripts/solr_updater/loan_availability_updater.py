"""Near-realtime loan availability updater for Solr.

New to this file? The 30-second version
---------------------------------------
This is a small standalone daemon -- not a cron, not part of the web app. It
runs as a backgrounded process inside the solr-updater container (launched by
docker/ol-solr-updater-start.sh, next to the main solr_updater). Every ~30s it:

  1. Asks IA's loan-changes API which books had a loan event since last time
     (lending.get_loan_changes -> GET services/loans/loan/?action=changes).
  2. Looks up the Solr EDITION document for each of those books (by ocaid).
  3. Marks the ones whose latest event TOOK capacity (borrow, browse, renew)
     as unavailable. Releasing events (return, expire, cancel) write nothing.
  4. Separately, every ~10 minutes, re-checks the books currently marked
     unavailable against IA's bulk availability API
     (lending.get_availability_batch -> GET services/availability/) and frees
     the ones that are actually borrowable.
  5. Saves a "uid" cursor to a state file so it resumes where it left off; on
     a cold start it collects the last ~14 days of loan changes and settles
     them in one batched availability pass before following events.

Nothing reads these Solr fields yet -- wiring search/pages to them is a
follow-up.

Two independent halves
----------------------
The design is two loops that share only the Solr field, and the split is what
makes each one simple:

  * The FOLLOWER writes from events alone and only ever sets `unavailable`. It
    has no dependency on the availability service, so it keeps consuming the
    feed while that service is lagging or down. An earlier revision joined
    every batch against availability and held the cursor whenever the service
    answered nothing -- which meant a lagging dependency stopped ingestion
    entirely.
  * The REPAIRER reads ground truth and only ever clears `unavailable`. It is
    scoped to the editions currently marked -- not a small set, so it is capped
    per pass and rotated oldest-mark-first rather than re-reading one prefix.

Neither half can undo the other's direction, so they converge instead of
fighting. Everything published as available has been checked; nothing is
published as available on the strength of an event.

What each half gets wrong, and why that is the right way round
--------------------------------------------------------------
The feed carries loan *events*; availability is lending *state* that only IA
can compute. Two facts make the events insufficient on their own:

  - Multi-copy items: an item may own several copies of a book. A borrow of
    one copy leaves the others borrowable, so a borrow event does not mean
    unavailable.
  - Waitlists: a return does not mean available. If people are queued, the
    freed copy goes to the head of the queue and the book stays unborrowable.
  - Neither copy counts nor queue depth appear anywhere in a changes row
    ({time, identifier, username, loan_id, event_type, extra, uid}), and Open
    Library does not track them either.

So each fact is handled on the side that can be wrong safely:

  - Multi-copy: the follower marks the book unavailable even though a copy is
    still free. Wrong, but it hides a borrowable book rather than offering an
    unborrowable one, and the repairer frees it within RECHECK_INTERVAL.
  - Waitlist: the follower must NOT clear on a return, because the repairer
    only ever clears. A wrongly-cleared waitlisted book would be published as
    borrowable with nothing to correct it. So releasing events write nothing
    and the clear waits for a ground-truth answer.

The asymmetry is the whole point: the recoverable error is allowed to happen
often, and the unrecoverable one is made as hard as this design can make it.
Not impossible: an availability snapshot takes minutes to gather and can
outlive the mark it would clear, so the re-check refuses to clear anything the
follower marked while that snapshot was in flight.

Known gap: a book whose acquiring event we never see -- a feed gap, or a
reindex that wipes the field (see below) -- stays published as available. The
repairer cannot catch that, because it only looks at books already marked. A
cold start (or --reset) is the recovery, and it is why the cold-start path
refuses to begin when the availability service is silent rather than starting
from the head against an unmarked index.

Default-available, exceptions only
----------------------------------
An `ebook_access:borrowable` edition is assumed AVAILABLE. Solr stores only
the exceptions: `ebook_unavailable` is 1 for books with no borrowing capacity
right now, 0 once they free up, and absent for the overwhelming majority that
have never had a loan event. Absent and 0 therefore mean the same thing, and a
consumer must query

    ebook_access:borrowable AND -ebook_unavailable:1

rather than treating a missing value as unknown. Writing "available" for the
whole borrowable corpus would be both enormous and pointless; writing it only
for recently-returned books (the previous design) produced a value that looked
authoritative while covering a tiny, biased slice of the index.

Solr mechanics
--------------
ebook_unavailable and ebook_becomes_available are numeric so writes qualify for
Solr's update.partial.requireInPlace: string and pdate fields are rejected by
Solr for in-place updates regardless of docValues/stored/indexed config, and a
*non*-in-place atomic update to a nested child document reindexes the entire
work + all its editions rather than just the one document, which would defeat
the point of a near-realtime updater. Edition updates therefore always include
"_root_" (the parent work's key) -- Solr requires this to target a child
document rather than create/replace a root-level one.

Solr also rejects "set": null under requireInPlace -- a value can be set or
incremented in-place, but not cleared, even on a field with no prior value.
So a book freeing up never clears ebook_becomes_available; it's left at its
last (now stale) value. ebook_becomes_available is advisory display data
("available in N days") and is meaningful only while ebook_unavailable is 1.

Recovering from drift
---------------------
Because the changes feed only tells us which books to look at, a book whose
availability changes without a loan event (lending policy change, copies added
or removed, item going dark) is never noticed. As a partial safety net, the
known-unavailable set -- editions currently carrying ebook_unavailable:1, a
bounded and small population -- is re-checked against ground truth every
RECHECK_INTERVAL seconds and flipped to 0 when it frees up. That covers missed
return/expire events and hold fulfillment, but it can only re-check editions we
still know about.

Reindex coordination (known limitation): a full Solr reindex of a work rebuilds
its edition children WITHOUT these loan fields -- the main indexer is unaware of
them -- so every reindex WIPES ebook_unavailable/loan_uid on the affected
editions. Under a default-available field that means a borrowed book silently
reads as available, and because the wipe also destroys the known-unavailable
list, the re-check above cannot repair it. This updater does NOT auto-detect a
reindex, and a *plain restart does not recover*: the state file persists in the
solr-updater-data volume, so on restart it resumes from the surviving last_uid
and skips reconstruction entirely. Recovery requires --reset (or deleting the
state file), which rebuilds the last ~14 days from the changes API. Stronger
guarantees (indexer-side field preservation, a reindex-triggered re-apply, or
wipe auto-detection) are a maintainer follow-up, out of scope here.
"""

import contextlib
import datetime
import json
import logging
import time
from pathlib import Path

import infogami
from openlibrary.config import load_config
from openlibrary.core import lending
from openlibrary.plugins.worksearch.search import get_solr
from openlibrary.utils.sentry import init_sentry

logger = logging.getLogger("openlibrary.loan-availability-updater")

# Values of the ebook_unavailable field. Absent means available too.
EBOOK_AVAILABLE = 0
EBOOK_UNAVAILABLE = 1

# Event types that RELEASE capacity. Everything else is treated as acquiring
# it, including a type we have never seen.
#
# The asymmetry is deliberate and it is the safety property of this design.
# Acquiring is written straight from the event with no ground-truth call, so an
# unknown type errs toward `unavailable` -- which the re-check corrects against
# ground truth within RECHECK_INTERVAL. Erring the other way would publish a
# book as borrowable when it is not, and nothing would correct it.
#
# The row shape is documented (lending.get_loan_changes) but IA's set of
# event_type VALUES is not, anywhere we can see. So this set is what we have
# observed, not what we have been told, and an unseen type is logged at WARNING
# precisely so production tells us what is missing from it.
RELEASING_EVENT_STEMS = ("return", "expire", "cancel")
"""Substrings that identify a capacity-RELEASING event type.

Matched as substrings rather than compared to a fixed set, because the
vocabulary is compound and we have only seen part of it: the shapes in hand
include `return`, `expire_browse` and `expire_borrow`, so an exact-match set
built from `{"return", "expire"}` would read `expire_browse` as an acquiring
event and mark a just-expired loan unavailable. The stems survive a suffix we
have not seen; a whole new verb still falls through to acquiring, which is the
safe direction.
"""


def is_releasing_event(event_type: str) -> bool:
    """Whether this event type frees capacity. Unknown verbs are not releasing."""
    lowered = (event_type or "").lower()
    return any(stem in lowered for stem in RELEASING_EVENT_STEMS)


# Acquiring types we have actually seen. Used ONLY to decide whether to log a
# surprise -- behaviour is identical for a type in this set and one outside it,
# so adding to it changes nothing except the log line.
_SEEN_ACQUIRING_EVENT_TYPES = frozenset({"borrow", "browse", "renew_borrow", "renew_browse", "renew"})

LOAN_MAX_AGE_DAYS = 14
BATCH_SIZE = 1000
MIN_RECONCILE_COVERAGE = 0.9
"""Fraction of cold-start identifiers that must get a ground-truth answer.

Below this the reconcile is refused rather than half-applied: an unmarked
on-loan book is published as borrowable and nothing corrects it.
"""

SOLR_QUERY_CHUNK = 500
"""Identifiers per `ia:(...)` disjunction.

One clause per identifier, against `solr.max.booleanClauses=30000` in
production. 500 leaves a wide margin and keeps each query small; the cost of
more round trips is irrelevant next to a query that fails outright.
"""
POLL_INTERVAL = 30  # seconds between polls when caught up
RECHECK_INTERVAL = 600  # seconds between ground-truth re-checks of the unavailable set
RECHECK_MAX_EDITIONS = 10000  # cap on editions re-checked per pass


def read_state(path: Path) -> int:
    """Return last processed uid, or 0 if the state file is absent/corrupt."""
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):  # fmt: skip
        return 0


def write_state(path: Path, uid: int) -> None:
    path.write_text(str(uid))


def find_start_uid(target_age_days: int = LOAN_MAX_AGE_DAYS) -> int:
    """Binary-search for the uid whose next event is ~target_age_days old.

    Uses limit=1 probes. Returns 0 if the API has no history or all history
    is newer than target_age_days.
    """
    try:
        resp = lending.get_loan_changes(after_uid=0, limit=1)
    except Exception:
        logger.exception("Loan changes API unreachable on startup probe; starting from uid 0")
        return 0

    if resp.get("status") != "OK":
        logger.warning("Loan changes API non-OK on startup probe; starting from uid 0")
        return 0

    latest_uid = resp.get("latest_uid") or 0
    if not latest_uid:
        return 0

    target_time = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=target_age_days)
    low, high = 0, latest_uid

    for _ in range(40):
        if high - low <= 1000:
            break
        mid = (low + high) // 2
        try:
            rows = lending.get_loan_changes(after_uid=mid, limit=1).get("rows", [])
        except Exception:
            logger.exception("Binary-search probe failed at uid %d; shrinking window", mid)
            high = mid
            continue
        if not rows:
            high = mid
            continue
        try:
            row_time = datetime.datetime.strptime(rows[0]["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=datetime.UTC)
        except KeyError, TypeError, ValueError:
            # Malformed/missing 'time' on a probe row: treat as "go earlier" rather
            # than crash startup. Conservative -- worst case we start a bit further back.
            high = mid
            continue
        if row_time < target_time:
            low = mid
        else:
            high = mid

    logger.info("Starting from uid %d", low)
    return low


def collect_dirty_identifiers(rows: list[dict]) -> dict[str, dict]:
    """Reduce a batch of rows to the set of identifiers needing a ground-truth check.

    Returns {identifier: {"uid": int, "until": str|None, "event_type": str}}
    for the highest-uid row seen per identifier. "until" is the loan-expiry
    string from that row, kept as advisory display data.

    The event type IS interpreted now, by :func:`build_solr_updates` -- an
    earlier revision of this module deliberately did not, because a borrow of
    a multi-copy item does not imply unavailable and a return of a waitlisted
    item does not imply available. Those two facts are still true; what changed
    is where they are handled. Acquiring events are written optimistically and
    the periodic ground-truth re-check corrects them, which keeps the event
    path free of any dependency on the availability service.
    """
    latest: dict[str, dict] = {}
    for row in rows:
        # Defensive: a single malformed row (missing identifier/uid, or a non-int
        # uid) must not crash the whole updater -- skip it and keep going.
        identifier = row.get("identifier")
        uid = row.get("uid")
        if not identifier or not isinstance(uid, int):
            logger.warning("Skipping malformed loan-change row: %r", row)
            continue
        if identifier in latest and latest[identifier]["uid"] >= uid:
            continue
        until = None
        with contextlib.suppress(json.JSONDecodeError, TypeError, AttributeError):
            until = json.loads(row.get("extra") or "{}").get("until")
        latest[identifier] = {"uid": uid, "until": until, "event_type": row.get("event_type") or ""}
    return latest


def ia_until_to_epoch(until: str | None) -> int | None:
    """Convert IA 'until' string ("2026-05-01 15:42:43", implicitly UTC) to epoch seconds."""
    if not until:
        return None
    try:
        dt = datetime.datetime.strptime(until, "%Y-%m-%d %H:%M:%S").replace(tzinfo=datetime.UTC)
        return int(dt.timestamp())
    except ValueError:
        logger.debug("Could not parse 'until' value: %r", until)
        return None


def resolve_edition_keys(identifiers: list[str]) -> dict[str, dict]:
    """Batch-resolve IA identifiers to Solr edition keys + parent work key via the ia field.

    Returns {identifier: {"key": "/books/OL1M", "root": "/works/OL1W"}}.

    Editions are nested children of their work in Solr; "_root_" (the parent
    work's key) must accompany any atomic update targeting the edition, so
    it's captured here alongside the edition key.
    """
    if not identifiers:
        return {}

    # Quote each term so identifiers with special characters are treated literally,
    # AND backslash-escape embedded " and \ -- otherwise a stray quote in an ocaid
    # produces a malformed Lucene query that fails every cycle and stalls the poller.
    def _phrase(id_: str) -> str:
        return '"' + id_.replace("\\", "\\\\").replace('"', '\\"') + '"'

    id_set = set(identifiers)
    resolved: dict[str, dict] = {}
    # Chunked here rather than at the call sites, because one caller cannot see
    # how large another's list is. The cold-start path hands over every
    # identifier touched in LOAN_MAX_AGE_DAYS -- tens of thousands -- and one
    # clause per identifier against Solr's maxBooleanClauses (30000 in
    # production) fails the whole query, which propagated out of the cold start
    # and killed the process before any state was written. A daemon that cannot
    # complete a cold start never starts at all.
    for start in range(0, len(identifiers), SOLR_QUERY_CHUNK):
        chunk = identifiers[start : start + SOLR_QUERY_CHUNK]
        quoted = " ".join(_phrase(id_) for id_ in chunk)
        result = get_solr().select(
            query=f"type:edition AND ia:({quoted})",
            fields=["key", "ia", "_root_"],
            rows=len(chunk) * 2,
        )
        for doc in result.docs:
            for ia_id in doc.get("ia", []):
                if ia_id in id_set:
                    resolved[ia_id] = {"key": doc["key"], "root": doc["_root_"]}
    return resolved


def query_solr_uid() -> int:
    """Return the highest loan_uid written to Solr, or 0 if none."""
    try:
        result = get_solr().select(
            # Constrain by the indexed `type:edition` predicate to seed the candidate
            # set; without it, `loan_uid:[* TO *]` (indexed=false, docValues only) is
            # an unbounded full-collection docValues scan.
            query="type:edition AND loan_uid:[* TO *]",
            fields=["loan_uid"],
            rows=1,
            sort="loan_uid desc",
        )
        if result.docs:
            return result.docs[0].get("loan_uid") or 0
    except Exception:
        logger.exception("Failed to query Solr for max loan_uid; will fall back to binary search")
    return 0


def solr_update_in_place(request: list[dict], commit: bool = False) -> None:
    """Call Solr.update_in_place and raise if Solr reports failure.

    update_in_place_async returns the parsed response without checking status
    -- other callers (trending_updater_daily/hourly) rely on that and just log
    it, so the check is done here rather than changing the shared method.
    """
    resp = get_solr().update_in_place(request, commit=commit)
    if resp.get("responseHeader", {}).get("status") != 0:
        raise RuntimeError(f"Solr in-place update error: {resp}")


def build_solr_updates(
    dirty: dict[str, dict],
    id_to_edition: dict[str, dict],
) -> list[dict]:
    """Build Solr atomic-update documents from the events alone.

    Write-only, in one direction: an acquiring event sets
    ``ebook_unavailable=1``; a releasing event writes NOTHING. All clearing is
    done by :func:`build_recheck_updates` against ground truth.

    That split is the whole design, and the releasing case is the reason for it.
    A return does not mean available -- if anyone is queued, the freed copy goes
    to the head of the waitlist and the book stays unborrowable. Clearing on a
    return event would therefore publish a book as borrowable when it is not,
    and nothing would correct it, because the re-check only ever flips
    unavailable -> available. Declining to write is what keeps every clear on
    the path that has actually checked.

    The converse error is harmless and self-correcting: marking a multi-copy
    item unavailable when one of several copies was borrowed is wrong, and the
    re-check frees it within RECHECK_INTERVAL. So this path never consults the
    availability service, and the updater keeps following the changes feed even
    while that service is down.

    An identifier with no Solr edition is skipped -- a new item, or its work is
    mid-reindex. There is no doc to mark, so the event is skipped while last_uid
    still advances; the book is missed until its next event or a --reset
    rebuild. Accepted as v1: an unindexed book has no searchable doc anyway.

    ebook_becomes_available is written only alongside ebook_unavailable=1, and
    only when the row carried a parsable expiry. It is never cleared when a book
    frees up (requireInPlace rejects "set": null), so it is advisory and
    meaningful only while ebook_unavailable is 1.
    """
    updates = []
    unrecognized: dict[str, int] = {}
    for identifier, state in dirty.items():
        edition = id_to_edition.get(identifier)
        if not edition:
            continue

        event_type = state.get("event_type") or ""
        if is_releasing_event(event_type):
            # Deliberately nothing. See the docstring: the re-check frees it.
            continue
        if event_type not in _SEEN_ACQUIRING_EVENT_TYPES:
            # Collected, not logged per identifier: one new IA verb at feed
            # volume would emit a warning per event per batch and flood both the
            # log and Sentry.
            unrecognized[event_type] = unrecognized.get(event_type, 0) + 1

        update: dict = {
            "key": edition["key"],
            "_root_": edition["root"],
            "ebook_unavailable": {"set": EBOOK_UNAVAILABLE},
            "loan_uid": {"set": state["uid"]},
        }
        becomes_available = ia_until_to_epoch(state.get("until"))
        if becomes_available is not None:
            update["ebook_becomes_available"] = {"set": becomes_available}
        updates.append(update)

    if unrecognized:
        # Not an error -- IA's event_type vocabulary is not published, so this is
        # how we learn of one. Treated as acquiring, the safe direction.
        logger.warning("Unrecognized loan event_types treated as acquiring: %r", unrecognized)
    return updates


def build_reconcile_updates(identifiers: list[str]) -> list[dict]:
    """Mark the genuinely-unavailable members of `identifiers` from ground truth.

    The cold-start half of the design. Replaying ~LOAN_MAX_AGE_DAYS of events
    tells us which books were *touched*, not which are unavailable now -- a book
    borrowed and returned twelve days ago is touched and available. So on a cold
    start the identifiers are collected without writing, and settled here in one
    batched pass against the availability service.

    One direction only, like the event path: it sets `ebook_unavailable=1` and
    never clears. Solr's default is available and :func:`build_recheck_updates`
    owns clearing, so the two together converge without either needing to write
    both ways.
    """
    if not identifiers:
        return []
    id_to_edition = resolve_edition_keys(identifiers)
    resolved = [identifier for identifier in identifiers if identifier in id_to_edition]
    if not resolved:
        return []

    availability = lending.get_availability_batch(resolved)
    # Coverage, not mere non-emptiness. `get_availability_batch` swallows a
    # failed chunk and continues, so with ~800 sequential requests a widespread
    # timeout still returns a non-empty dict -- and an earlier version of this
    # guard passed on it, leaving most genuinely-on-loan books unmarked. The
    # re-check cannot correct that, because it only inspects books already
    # marked. So this insists on most of what it asked for.
    covered = len(availability) / len(resolved)
    if covered < MIN_RECONCILE_COVERAGE:
        raise RuntimeError(f"Availability covered only {len(availability)}/{len(resolved)} identifiers ({covered:.0%}); refusing to reconcile")

    updates = []
    for identifier, avail in availability.items():
        edition = id_to_edition.get(identifier)
        if not edition or lending.is_available_for_loan(avail):
            continue
        updates.append(
            {
                "key": edition["key"],
                "_root_": edition["root"],
                "ebook_unavailable": {"set": EBOOK_UNAVAILABLE},
            }
        )
    return updates


def build_recheck_updates(marked_during_pass: set[str] | None = None) -> list[dict]:
    """Re-check the known-unavailable editions against ground truth.

    Safety net for availability changes the changes feed never reports: missed
    return/expire events, a waitlist draining, copies being added, an item
    leaving lending. Scoped to editions currently marked unavailable.

    That set is not small: it is roughly the books on loan plus every
    multi-copy item the follower has over-marked, and it can exceed
    RECHECK_MAX_EDITIONS. Sorted by `loan_uid` so the window rotates
    oldest-mark-first; unsorted, the same prefix came back every pass and the
    tail was reached only as fast as the head freed.

    Only flips unavailable -> available. Editions the service has no answer for
    keep their current value.

    `marked_during_pass` is the set of edition keys the follower wrote while
    this pass was in flight; they are never cleared here, because the answers
    below may predate those marks.
    """
    marked_during_pass = marked_during_pass or set()
    result = get_solr().select(
        query=f"type:edition AND ebook_unavailable:{EBOOK_UNAVAILABLE}",
        # loan_uid, for two reasons. Sorted, it rotates the window: unsorted the
        # select returns the same lowest-docid prefix every pass, so once more
        # than RECHECK_MAX_EDITIONS are marked the tail is re-checked only as
        # fast as the head frees -- measured at roughly five editions a pass,
        # which strands an over-marked book for months. Oldest-marked-first also
        # happens to be the right priority.
        #
        # Selected as a field so the clear can be guarded against a mark that
        # landed after the availability snapshot was taken. See below.
        fields=["key", "ia", "_root_", "loan_uid"],
        sort="loan_uid asc",
        rows=RECHECK_MAX_EDITIONS,
    )
    docs = result.docs
    if len(docs) >= RECHECK_MAX_EDITIONS:
        logger.warning(
            "Re-check hit the %d-edition cap; the rest rotate in on later passes (sorted by loan_uid)",
            RECHECK_MAX_EDITIONS,
        )

    # One edition can carry several ocaids; map each back to its doc.
    id_to_doc: dict[str, dict] = {}
    for doc in docs:
        for ia_id in doc.get("ia", []):
            id_to_doc[ia_id] = doc
    if not id_to_doc:
        return []

    availability = lending.get_availability_batch(list(id_to_doc))

    updates = []
    seen_keys = set()
    for identifier, avail in availability.items():
        doc = id_to_doc.get(identifier)
        if not doc or not lending.is_available_for_loan(avail):
            continue
        if doc["key"] in seen_keys:
            continue
        # Refuse to clear anything the follower marked while this pass was
        # running. `get_availability_batch` is ~100 sequential requests and
        # takes tens of seconds to minutes; the follower keeps consuming events
        # throughout. Without this, a book borrowed during that window gets
        # marked by the follower and then cleared by a snapshot that predates
        # the borrow -- published as borrowable while on loan, with the event
        # already behind the cursor and the re-check unable to re-mark it. That
        # is the one direction this design calls unrecoverable.
        #
        # Checked in process rather than by re-reading Solr: follower writes use
        # commit=False, so a re-select can lag them by a soft-commit window and
        # would miss exactly the marks this needs to see.
        if doc["key"] in marked_during_pass:
            logger.info("Not clearing %s: the follower marked it during this pass", doc["key"])
            continue
        seen_keys.add(doc["key"])
        updates.append(
            {
                "key": doc["key"],
                "_root_": doc["_root_"],
                "ebook_unavailable": {"set": EBOOK_AVAILABLE},
            }
        )
    return updates


def run_cold_start(last_uid: int, poll_interval: int, dry_run: bool) -> int:
    """Settle the replay window against ground truth, then return the new cursor.

    Replaying the window through the event path would mark every book touched in
    the last LOAN_MAX_AGE_DAYS unavailable -- including the many borrowed and
    returned days ago -- and leave the repairer to walk all of them back. So the
    identifiers are collected without writing and settled in one batched pass.

    This is the one path that genuinely depends on the availability service.
    Steady state deliberately does not, but a cold start has no prior state to
    fall back on: beginning from the head against an index where nothing is
    marked would publish every on-loan book as borrowable. So a service that
    answers for fewer than MIN_RECONCILE_COVERAGE of the identifiers raises
    here rather than degrading -- coverage, not mere non-emptiness, because
    `get_availability_batch` drops a failed chunk and carries on.
    """
    logger.info("Cold start: collecting identifiers from uid %d to the head", last_uid)
    touched: set[str] = set()
    while True:
        try:
            resp = lending.get_loan_changes(after_uid=last_uid, limit=BATCH_SIZE)
        except Exception:
            logger.exception("Cold start: failed to fetch loan changes; retrying in %ds", poll_interval)
            time.sleep(poll_interval)
            continue
        if resp.get("status") != "OK":
            logger.error("Cold start: loan changes returned status=%r; retrying", resp.get("status"))
            time.sleep(poll_interval)
            continue
        rows = resp.get("rows", [])
        if not rows:
            break
        valid = [row for row in rows if isinstance(row.get("uid"), int)]
        if not valid:
            logger.warning("Cold start: batch of %d rows had no valid uid; stopping collection", len(rows))
            break
        touched.update(row["identifier"] for row in valid if row.get("identifier"))
        last_uid = max(row["uid"] for row in valid)
        if len(rows) < BATCH_SIZE:
            break

    logger.info("Cold start: %d identifiers touched; reconciling against ground truth", len(touched))
    if reconcile := build_reconcile_updates(sorted(touched)):
        logger.info("Cold start: marking %d editions unavailable", len(reconcile))
        if not dry_run:
            solr_update_in_place(reconcile, commit=True)
    return last_uid


def main(  # noqa: PLR0915, PLR0912
    ol_config: str,
    state_file: str = "loan-availability-update.state",
    poll_interval: int = POLL_INTERVAL,
    recheck_interval: int = RECHECK_INTERVAL,
    dry_run: bool = False,
    reset: bool = False,
):
    """Follow IA loan changes; repair against bulk availability on an interval.

    Useful environment variables:
    - OL_SOLR_BASE_URL: Override the Solr base URL

    :param ol_config: Path to openlibrary.yml config file.
    :param state_file: Path to state file storing last processed uid (integer).
    :param poll_interval: Seconds to sleep when caught up with the event stream.
    :param recheck_interval: Seconds between ground-truth re-checks of the
                             known-unavailable set.
    :param dry_run: Fetch and log updates but do not write to Solr.
    :param reset: Ignore existing state and binary-search for the start uid.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)-15s %(levelname)s %(message)s")
    logger.info("BEGIN loan_availability_updater dry_run=%s reset=%s", dry_run, reset)

    load_config(ol_config)
    lending.setup(infogami.config)
    init_sentry(getattr(infogami.config, "sentry", {}))

    state_path = Path(state_file)
    last_uid = 0 if reset else read_state(state_path)
    cold_start = False

    if last_uid == 0:
        # --reset forces a rebuild from the changes API; a stale loan_uid still in
        # Solr must not short-circuit that (else reset never goes back ~14 days).
        if not reset:
            last_uid = query_solr_uid()
        if last_uid:
            logger.info("Resuming from Solr loan_uid=%d", last_uid)
            cold_start = True
        else:
            logger.info("No Solr uid; binary-searching for uid ~%d days ago", LOAN_MAX_AGE_DAYS)
            last_uid = find_start_uid()
            cold_start = True
    if cold_start:
        last_uid = run_cold_start(last_uid, poll_interval, dry_run)
        if not dry_run:
            try:
                write_state(state_path, last_uid)
            except OSError:
                logger.exception("Failed to write post-reconcile state file %s", state_path)

    last_recheck = 0.0
    # Edition keys the follower marked since the last re-check pass. The re-check
    # must not clear these: its availability answers may predate the mark.
    marked_this_pass: set[str] = set()

    while True:
        try:
            resp = lending.get_loan_changes(after_uid=last_uid, limit=BATCH_SIZE)
        except Exception:
            logger.exception("Failed to fetch loan changes; will retry in %ds", poll_interval)
            time.sleep(poll_interval)
            continue

        if resp.get("status") != "OK":
            logger.error("Loan changes API returned status=%r; sleeping", resp.get("status"))
            time.sleep(poll_interval)
            continue

        rows = resp.get("rows", [])
        did_updates = False
        write_blocked = False

        if rows:
            # Advance the cursor using only rows with a valid int uid, so one malformed
            # row can neither crash here nor stall the cursor (collect_dirty_identifiers
            # skips it too).
            valid_uids = [r["uid"] for r in rows if isinstance(r.get("uid"), int)]
            if not valid_uids:
                logger.warning("Batch of %d rows had no valid uid; sleeping", len(rows))
                time.sleep(poll_interval)
                continue
            new_uid = max(valid_uids)
            if new_uid <= last_uid:
                # The feed answered with nothing newer. Without this the cursor
                # can move BACKWARDS, and a page whose uids never pass the
                # cursor spins the loop with no sleep -- measured at 201 API
                # calls in 0.21s, hammering IA, Solr and the commit path.
                logger.warning("Feed returned %d rows but none past uid %d; sleeping", len(rows), last_uid)
                time.sleep(poll_interval)
                continue
            dirty = collect_dirty_identifiers(rows)
            try:
                id_to_edition = resolve_edition_keys(list(dirty))
            except Exception:
                logger.exception("Failed to resolve edition keys; skipping batch")
                time.sleep(poll_interval)
                continue

            # No availability call here, deliberately. The steady-state path
            # writes from the events alone, so the updater keeps following the
            # feed while the availability service is slow or down -- an earlier
            # revision consulted it per batch and stalled the cursor whenever it
            # answered nothing, which made a lagging dependency stop ingestion.
            updates = build_solr_updates(dirty, id_to_edition)
            if updates:
                logger.info(
                    "%d Solr updates from %d loan events over %d ocaids (uid %d→%d)",
                    len(updates),
                    len(rows),
                    len(dirty),
                    last_uid,
                    new_uid,
                )
                if not dry_run:
                    try:
                        solr_update_in_place(updates, commit=False)
                    except Exception:
                        # Do not `continue`: that skipped the re-check below, so
                        # one rejected follower batch stopped the repairer too
                        # and both loops wedged together.
                        logger.exception("Solr update failed; state not advanced")
                        write_blocked = True
                    else:
                        marked_this_pass.update(u["key"] for u in updates)
                        did_updates = True

            if not write_blocked:
                last_uid = new_uid

        now = time.monotonic()
        if now - last_recheck >= recheck_interval:
            try:
                rechecks = build_recheck_updates(marked_this_pass)
            except Exception:
                logger.exception("Failed to build re-check updates")
                rechecks = []

            if rechecks:
                logger.info("Freeing %d editions whose ground truth is now available", len(rechecks))
                if not dry_run:
                    try:
                        solr_update_in_place(rechecks, commit=False)
                    except Exception:
                        logger.exception("Solr re-check update failed; skipped this pass")
                        rechecks = []
                did_updates = did_updates or bool(rechecks)
            last_recheck = now
            marked_this_pass = set()

        # No explicit commit. An earlier revision hard-committed every cycle to
        # keep the state file behind a durable write, but it did not achieve
        # that -- last_uid advances in memory before any commit -- and a hard
        # commit opens a new searcher and invalidates every Solr cache, up to
        # once every poll interval, on the Solr serving openlibrary.org. The
        # documents are in the tlog and Solr's own autoCommit (120s) persists
        # them; autoSoftCommit (60s) makes them visible. Replaying a few events
        # after a crash is harmless -- marks are idempotent.
        if not dry_run:
            try:
                write_state(state_path, last_uid)
            except OSError:
                logger.exception("Failed to write state file %s; will retry next cycle", state_path)

        if len(rows) >= BATCH_SIZE:
            continue

        logger.debug("Caught up at uid=%d; sleeping %ds", last_uid, poll_interval)
        time.sleep(poll_interval)


if __name__ == "__main__":
    from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

    FnToCLI(main).run()
