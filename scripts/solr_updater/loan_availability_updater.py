"""Near-realtime loan availability updater for Solr.

How this design arrived here (v1 -> v2 -> v3)
--------------------------------------------
Three approaches, each abandoned for a measured reason. Recorded because the
two superseded ones look reasonable on paper and the next person will think of
them again:

  * **v1 - replay 14 days of loan changes on every cold start.** Produced only
    CANDIDATES, each needing an availability call to settle, which made a
    restart's cost scale with feed volume. Unbounded in the one place a daemon
    must not be.
  * **v2 - seed from the index once, then follow the changes feed** (this
    file's follower/repairer below, plus MR 6634). Abandoned on Ximm's finding
    that the changes API **cannot report loan EXPIRY** -- only initiation -- so
    the feed can never free a book on its own, and the per-item Lending Status
    Endpoint that would have covered the gap is too slow (>10s/item) to sustain
    at traffic.
  * **v3 - poll the index and reconcile** (`build_poll_updates`). The ES index
    ALREADY reflects expiry, through IA's own LENDING-EXPIRE followers, and
    AdvancedSearch reads that finished answer fast. So the index publishes the
    snapshot the previous two designs were reconstructing. One read of "who is
    unavailable now", one read of what Solr has marked, one bulk update
    carrying both directions. A first poll is a cold start; a reindex wipe
    self-heals on the next one.

Credit for the v2 blockers is Ximm's (ES lead); they are what moved this.

What v3 gives up, deliberately
------------------------------
The per-search Bulk Availability call being removed returns rich per-book
lending data -- browsable, has-14-day-borrow, waitlistable, waitlist DEPTH --
and the poll keeps only binary `ebook_unavailable`. Being precise about what is
lost versus merely relocated, because the two get conflated:

  * **Static capability** (browsable / 14-day-borrow / waitlistable) is item
    CONFIG, not loan state, and is already partly in the index as lending flags
    (`lending___status` carries `is_browsable`). It belongs in the MAIN indexer
    for ALL books, not in this daemon, so it is not blocked by this design --
    it is a separate additive workstream.
  * **Genuinely lost**: waitlist DEPTH and the real-time reason a book is
    unavailable. Both are dynamic, neither is in the index. Note they only
    matter for the currently-unavailable set -- a waitlist is irrelevant while
    a book is on the shelf -- which is exactly the ~766-book set this polls, so
    they are cheaply recoverable later within this model for that small subset,
    NOT at 25k/min across every search.
  * The coarse Read-vs-Borrow control on search results comes from
    `ebook_access` (main indexer) and is unaffected. The fine-grained choice
    within borrowable is resolved at the book page, which already fetches live.

So: search is served from Solr; rich, authoritative, real-time data is fetched
at the book page. What is given up is rich DYNAMIC data in search RESULTS for
every book -- which is precisely the 25k/min load being removed.

Scale, for why exceptions-only is right rather than a limitation: 4.5M browse,
860k borrowable, 24k waitlistable, and a currently-unavailable set measured at
766 on 2026-10-05. Browse books are never "unavailable", so the set is drawn
from the borrowable 860k. The poll never touches the 4.5M.

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
     (lending.get_availability_async -> GET services/availability/) and frees
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

import asyncio
import itertools
import logging
import time

import infogami
from openlibrary.config import load_config
from openlibrary.core import lending
from openlibrary.plugins.worksearch.search import get_solr
from openlibrary.utils.request_context import create_context_for_script, req_context
from openlibrary.utils.sentry import init_sentry

logger = logging.getLogger("openlibrary.loan-availability-updater")

# Values of the ebook_unavailable field. Absent means available too.
EBOOK_AVAILABLE = 0
EBOOK_UNAVAILABLE = 1

"""Substrings that identify a capacity-RELEASING event type.

Matched as substrings rather than compared to a fixed set, because the
vocabulary is compound and we have only seen part of it: the shapes in hand
include `return`, `expire_browse` and `expire_borrow`, so an exact-match set
built from `{"return", "expire"}` would read `expire_browse` as an acquiring
event and mark a just-expired loan unavailable. The stems survive a suffix we
have not seen; a whole new verb still falls through to acquiring, which is the
safe direction.
"""


"""Nominal maximum loan length, in days.

No longer used to seed a cold start -- the index query does that directly --
and retained only for callers that still want the figure.

Treat it as an UNVERIFIED assumption. It was chosen because 14 days is the
standard borrow period, not because anyone confirmed it bounds how long a book
can stay continuously unavailable. A renewal, a longer lending period, or a
waitlist holding a book after an old return would all break that reading. The
seed no longer depends on it being true; nothing else should start to.
"""

"""Events replayed after the index seed, to cover the index's lag.

The seed is a snapshot computed at an unknown instant, so a book borrowed just
after it is absent from the seed -- unmarked, published as borrowable while it
is out, and nothing recovers that. This window is the insurance.

Counted in events rather than hours because a time window converts to an
unknown number of feed pages. At the feed's measured ~240,000 uids/day this is
roughly five hours, and 50 pages of work, once.

Conservative on purpose: replaying too much only re-marks books that are
already marked, while replaying too little leaves a gap of exactly the kind
this exists to close. Tighten it when the index lag has actually been
measured -- it has not been.
"""
"""Roughly how far the changes feed's uid advances in a day (measured 2026-10).

Now informs only OVERLAP_EVENTS -- it is how that event count is translated
into a rough number of hours.
Only sizes the start-uid search's first step back from the head, so being off
in either direction costs a few probes, never accuracy."""
"""Rows per feed page. Pinned to IA's own ceiling rather than restated: asking
for more is silently capped, so a larger number here would quietly mean fewer
events per request than the code claims."""
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
HEARTBEAT_INTERVAL = 300  # seconds between proof-of-life log lines
"""Editions re-checked per pass. Sized so a pass fits inside RECHECK_INTERVAL.

`get_availability_async` sends AVAILABILITY_BATCH_SIZE (100) ids per request,
sequentially. At 10000 that is 100 requests; if archive.org is slow or down and
each hits the HTTP timeout, a single pass runs far longer than the 600s interval
-- so the re-check would run back to back forever and, being in the same
single-threaded loop, starve the follower completely. The feed would stop being
consumed for the length of the outage.

At 2000 it is 20 requests: a few seconds healthy, a few minutes at worst, always
finishing before the next pass is due. Nothing is lost by the smaller window
because the select rotates (`sort=loan_uid asc`), so successive passes advance
through the marked set rather than re-reading one prefix.
"""


async def resolve_edition_keys(identifiers: list[str]) -> dict[str, dict]:
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
    for chunk in itertools.batched(identifiers, SOLR_QUERY_CHUNK, strict=False):
        quoted = " ".join(_phrase(id_) for id_ in chunk)
        result = await get_solr().select_async(
            query=f"type:edition AND ia:({quoted})",
            fields=["key", "ia", "_root_"],
            rows=len(chunk) * 2,
        )
        for doc in result.docs:
            for ia_id in doc.get("ia", []):
                if ia_id in id_set:
                    resolved[ia_id] = {"key": doc["key"], "root": doc["_root_"]}
    return resolved


async def solr_update_in_place(request: list[dict], commit: bool = False) -> None:
    """Call Solr.update_in_place_async and raise if Solr reports failure.

    update_in_place_async returns the parsed response without checking status
    -- other callers (trending_updater_daily/hourly) rely on that and just log
    it, so the check is done here rather than changing the shared method.
    """
    resp = await get_solr().update_in_place_async(request, commit=commit)
    if resp.get("responseHeader", {}).get("status") != 0:
        raise RuntimeError(f"Solr in-place update error: {resp}")


POLL_INTERVAL = 15
"""Seconds between polls of the index's unavailable set.

Measured 2026-10-05 against live archive.org: the set moved by 4 books across
several minutes, so it changes per-minute rather than per-second. At two pages
per poll, 10s is ~17,000 requests/day and 30s is ~5,700, for no freshness any
measurement here could distinguish.
"""

MARKED_SET_MAX = 50_000
"""Ceiling on the marked set read back from Solr.

Not a working limit -- the live unavailable set measured 766 on 2026-10-05 --
but the read must be COMPLETE or the reconcile is wrong in the dangerous
direction: an edition outside a capped window is indistinguishable from one the
index no longer calls unavailable, and would be cleared.
"""

CLEAR_BREAKER_FRACTION = 0.10
CLEAR_BREAKER_FLOOR = 25
"""Clear-direction circuit breaker: refuse a poll that clears implausibly many.

The poll's clear direction rests entirely on ABSENCE from a lagged index, with
no ground-truth call anywhere -- the single largest change from the design this
replaced, where the follower could only mark and the repairer could only clear
against ground truth.

The existing seed guards catch a result larger than the paging window and a
read shorter than its own numFound. Neither can catch a result that is SMALL
BUT INTERNALLY CONSISTENT: a mid-reindex or partially degraded index honestly
reporting numFound 5 and returning 5 passes every check, and the reconcile then
clears the rest -- publishing hundreds of checked-out books as borrowable,
which is the failure mode that must never ship.

Consecutive-absence hysteresis does not fix that, because a degraded index
stays degraded; it delays the mass clear by N cycles and then performs it. A
relative-change guard does. Sized from measurement: a normal cycle clears 0-2
against ~766 marked, well under 1%, so 10% never trips in ordinary operation
while catching anything resembling a mass event. The absolute floor keeps a
small marked set (a fresh install, a test) from tripping on routine movement.

What this guard does and does not do:

  * It does NOT decide that a large clear is wrong. It decides that a large
    clear may not proceed on the index's word alone. A tripped breaker hands
    the whole clear set to ground truth (:func:`confirm_mass_clear`), which
    decides each edition on its own answer.
  * So a legitimate mass-free -- a batch of same-day loans expiring together --
    proceeds, and an index that has collapsed does not. The daemon recovers
    from both without a human, which matters because the alternative resting
    state is "availability-freeing is frozen until somebody notices".
  * It does not protect the MARK direction, which needs no protection: marking
    is the recoverable error, and the next poll unmarks.
"""


class PollRefused(Exception):
    """This cycle's inputs were not trustworthy, so prior state stands.

    Every untrustworthy-input case resolves the same way -- skip the cycle,
    keep what Solr already has, alarm -- because at poll cadence the
    alternative is a crash loop during routine index churn. Raising was right
    when the read happened once at startup; it is wrong at cadence, and the
    predicate changing is what makes the old response stale.
    """


async def fetch_marked_editions() -> dict[str, dict]:
    """Every edition Solr currently has marked unavailable, or refuse.

    Complete or raises, for the reason in MARKED_SET_MAX: a truncated read
    makes absent-from-the-window look identical to absent-from-the-index, and
    the reconcile clears on absence.
    """
    result = await get_solr().select_async(
        query=f"type:edition AND ebook_unavailable:{EBOOK_UNAVAILABLE}",
        fields=["key", "ia", "_root_"],
        rows=MARKED_SET_MAX,
    )
    docs = result.docs
    if len(docs) >= MARKED_SET_MAX:
        raise PollRefused(f"Marked set reached the {MARKED_SET_MAX}-edition read cap; cannot tell a complete read from a truncated one")
    return {doc["key"]: doc for doc in docs}


async def confirm_mass_clear(to_clear: list[dict], allowed: int, marked_total: int, index_total: int) -> list[dict]:
    """Settle a tripped clear-breaker against ground truth, or refuse.

    The breaker alone cannot tell a degraded index from a legitimate mass-free:
    a batch of same-day loans all expiring together and an ES mid-reindex both
    present as "the clear set is suddenly huge". Refusing both is safe in the
    sense that over-holding only hides a book, but it is NOT safe as a resting
    state -- the clear set stays large on every subsequent cycle, so a real
    mass-free leaves availability permanently frozen until a human notices. A
    guard that is always tripped is one people learn to route around.

    So the exceptional path asks the authority the index is only a view of. The
    answer is per-edition, which is why this is not sampled: a sample that
    comes back available supports "legitimate mass-free" without establishing
    it, and the clear direction is where being wrong is unrecoverable. The
    whole set is checked, each edition decided on its own answer, and anything
    the service has no answer for stays marked.

    Affordable because it is rare and bounded: the clear set is at most the
    marked set, measured at 766 on 2026-10-05, which is ~8 batched requests at
    AVAILABILITY_BATCH_SIZE. That is the cost v2's repairer paid every single
    cycle; here it is paid only when the breaker trips.

    This is two checks whose blind spots do not overlap -- the index is fast
    and lagged, ground truth is slow and authoritative -- and a dangerous clear
    needs both to agree.
    """
    identifiers = [ia for doc in to_clear for ia in (doc.get("ia") or [])]
    logger.warning(
        "Clear breaker tripped: %d of %d marked editions would clear (limit %d); the index returned %d identifiers. "
        "Confirming %d identifiers against ground truth before clearing anything.",
        len(to_clear),
        marked_total,
        allowed,
        index_total,
        len(identifiers),
    )
    if not identifiers:
        raise PollRefused(
            f"Clear breaker: {len(to_clear)} editions would clear but none carry an ocaid, so ground truth cannot be consulted. Keeping prior state."
        )

    availability = await lending.get_availability_async("identifier", identifiers, use_cache=False)

    def is_free(ia_id: str) -> bool:
        answer = availability.get(ia_id)
        # No answer is not an answer: an edition the service skipped keeps its
        # mark, because the clear direction is the unrecoverable one.
        return answer is not None and lending.is_available_for_loan(answer)

    confirmed = [doc for doc in to_clear if any(is_free(ia) for ia in (doc.get("ia") or []))]

    if not confirmed:
        # Every answer disagreed with the index, or the service gave none. The
        # index is the thing that is wrong; hold everything.
        raise PollRefused(
            f"Clear breaker: ground truth confirmed 0 of {len(to_clear)} editions as available, "
            f"so the index is wrong rather than the collection freeing. Keeping prior state."
        )

    logger.warning(
        "Clear breaker: ground truth confirmed %d of %d editions as genuinely available; clearing those and holding the rest.",
        len(confirmed),
        len(to_clear),
    )
    return confirmed


async def build_poll_updates(unavailable_identifiers: list[str]) -> list[dict]:
    """Reconcile Solr's marked set to the index's unavailable set, in one pass.

    This is the whole daemon. `unavailable_identifiers` is what the index says
    is checked out right now; everything Solr has marked that is not in it has
    been returned or expired. One bulk in-place update carries both directions.

    It replaces a cold start, a follower, a repairer, a cursor and an overlap
    replay, because every one of those existed to approximate a snapshot the
    index already publishes. A first poll is a cold start. A reindex wipe
    self-heals on the next poll, with nothing to re-run by hand.
    """
    resolved = await resolve_edition_keys(unavailable_identifiers)
    should_be_marked = {info["key"]: info for info in resolved.values()}
    marked = await fetch_marked_editions()

    to_mark = [info for key, info in should_be_marked.items() if key not in marked]
    to_clear = [doc for key, doc in marked.items() if key not in should_be_marked]

    allowed = max(CLEAR_BREAKER_FLOOR, int(len(marked) * CLEAR_BREAKER_FRACTION))
    if len(to_clear) > allowed:
        to_clear = await confirm_mass_clear(to_clear, allowed, len(marked), len(unavailable_identifiers))

    updates = [{"key": info["key"], "_root_": info["root"], "ebook_unavailable": {"set": EBOOK_UNAVAILABLE}} for info in to_mark]
    updates += [{"key": doc["key"], "_root_": doc["_root_"], "ebook_unavailable": {"set": EBOOK_AVAILABLE}} for doc in to_clear]

    # Counts, every cycle, so write volume is observable without a profiler --
    # the disk-growth investigation needs this and a rate is invisible in a
    # per-event log.
    logger.info(
        "Poll: index=%d resolved=%d marked=%d mark=%d clear=%d",
        len(unavailable_identifiers),
        len(should_be_marked),
        len(marked),
        len(to_mark),
        len(to_clear),
    )
    return updates


async def log_heartbeat(marked: int | None) -> None:
    """Proof of life, because the absence of errors is also what a stall looks like.

    Deliberately a log line and not a metrics integration: the requirement is
    that the question be answerable from outside, not dashboarded.
    """
    logger.info("Heartbeat: editions_marked_unavailable=%s", marked)


async def main(
    ol_config: str,
    poll_interval: int = POLL_INTERVAL,
    dry_run: bool = False,
):
    """Mirror the index's unavailable set into Solr, forever.

    Useful environment variables:
    - OL_SOLR_BASE_URL: Override the Solr base URL

    :param ol_config: Path to openlibrary.yml config file.
    :param poll_interval: Seconds between polls.
    :param dry_run: Compute and log updates but do not write to Solr.

    There is no cursor, no state file and no --reset. Each poll is a complete
    statement of what should be marked, so the first one after any start IS the
    cold start, and a reindex that wipes the field self-heals on the next one.
    The operator step that used to exist is gone rather than automated, which
    is the point: nothing can be forgotten if there is nothing to remember.

    Every failure resolves the same way -- log, keep prior state, try again
    next cycle -- because at this cadence an exception is a crash loop and the
    previous poll's marks are always a better answer than no marks at all.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)-15s %(levelname)s %(message)s")
    logger.info("BEGIN loan_availability_updater poll_interval=%ds dry_run=%s", poll_interval, dry_run)

    load_config(ol_config)
    lending.setup(infogami.config)
    req_context.set(create_context_for_script())
    init_sentry(getattr(infogami.config, "sentry", {}))

    last_heartbeat = 0.0
    while True:
        try:
            unavailable = await lending.get_checked_out_candidates_async()
            updates = await build_poll_updates(unavailable)
        except lending.CheckedOutSeedIncomplete, PollRefused:
            # Both mean "this cycle's inputs are not trustworthy". Prior state
            # stands, which is the safe direction: an over-held book is hidden
            # for one cycle, an under-held one is published as borrowable while
            # it is out and nothing revisits it.
            logger.exception("Poll refused; prior state stands")
        except Exception:
            logger.exception("Poll failed; prior state stands")
        else:
            if updates and not dry_run:
                # Never a hard commit. One opens a new searcher and invalidates
                # every Solr cache on the instance serving openlibrary.org, and
                # at this cadence that is ~5,760 of them a day. autoSoftCommit
                # makes the write visible within a second and autoCommit
                # persists it; neither needs asking. The small write set is not
                # the reason -- commit cost tracks searcher churn, not the
                # number of documents.
                await solr_update_in_place(updates, commit=False)
            elif updates:
                logger.info("Dry run: %d updates not written", len(updates))

            now = time.monotonic()
            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                await log_heartbeat(len(await fetch_marked_editions()))
                last_heartbeat = now

        await asyncio.sleep(poll_interval)


if __name__ == "__main__":
    from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

    FnToCLI(main).run()
