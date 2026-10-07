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
  * **v2 - seed from the index once, then follow the changes feed** (a
    follower/repairer split, plus MR 6634). Abandoned on Ximm's finding
    that the changes API **cannot report loan EXPIRY** -- only initiation -- so
    the feed can never free a book on its own, and the per-item Lending Status
    Endpoint that would have covered the gap is too slow (>10s/item) to sustain
    at traffic. Its follower is RESTORED in v4 below, for marks only, which is
    the direction the blocker never touched.
  * **v3 - poll the index and reconcile** (`build_poll_updates`). The ES index
    ALREADY reflects expiry, through IA's own LENDING-EXPIRE followers, and
    AdvancedSearch reads that finished answer fast. So the index publishes the
    snapshot the previous two designs were reconstructing. One read of "who is
    unavailable now", one read of what Solr has marked, one bulk update
    carrying both directions. A first poll is a cold start; a reindex wipe
    self-heals on the next one.

  * **v4 - the poll, plus v2's follower for MARKS only.** This branch. v3 is
    correct but only ever as current as the index, and the index lags: borrows
    were measured taking minutes to appear, with a tail still missing at 1h40m.
    Through that window v3 shows a just-borrowed book as borrowable. The
    changes feed sees the borrow at once -- and Ximm's blocker was about
    CLEARING, not marking. The feed cannot report expiry, so it can never free
    a book; it can always mark one. So the follower returns in the single
    direction it is sound in: :func:`_feed_loop` marks from events every
    FEED_INTERVAL seconds and never clears, :func:`_poll_loop` remains the only
    thing that clears, every POLL_INTERVAL seconds, against the index. Each
    loop does the half the other is bad at, and neither is able to make the
    unrecoverable mistake.

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
docker/ol-solr-updater-start.sh, next to the main solr_updater). It runs TWO
concurrent loops.

The POLL (:func:`_poll_loop`), every POLL_INTERVAL seconds:

  1. Asks archive.org's search index which books are lendable but currently
     neither borrowable nor browsable -- i.e. who is checked out right now
     (lending.get_checked_out_candidates_async -> GET advancedsearch.php).
  2. Looks up the Solr EDITION document for each of those identifiers (by
     ocaid), and reads back which editions Solr currently has marked.
  3. Issues ONE bulk in-place update: `ebook_unavailable` set to 1 on the
     newly-unavailable, 0 on the ones that have been returned or expired.

The FOLLOWER (:func:`_feed_loop`), every FEED_INTERVAL seconds, reads IA's
loan-changes feed forward from a cursor and marks the identifiers that just had
an acquiring event. It never clears -- that is the whole of its contract -- so
a borrow shows up in Solr within seconds instead of waiting for the index to
notice it.

That is the whole of it. Each poll is a complete statement of what should be
marked rather than an increment on top of what came before, so there is no
state file and no --reset. The follower's cursor is the only state, it lives in
memory, and every start re-places it at the index's currency
(:func:`bootstrap_feed_cursor`) rather than resuming a persisted one.

Nothing reads this Solr field yet -- wiring search/pages to it is a follow-up.

Why there is no cold start
--------------------------
The first poll after any start IS the cold start, and it costs exactly what
every other poll costs. A restart needs no catch-up, a lost state file is not a
concept, and a reindex that wipes the field self-heals on the next cycle. The
operator step that used to exist is deleted rather than automated: nothing can
be forgotten if there is nothing to remember.

The follower has a startup step, but not a catch-up one. It places its cursor
at the index's currency -- one feed read, bounded by BATCH_SIZE, replaying only
the lag gap the poll cannot already see. It never replays a window sized by how
long the daemon was down, which is the unbounded restart cost v1 had.

The asymmetry that shapes everything here
-----------------------------------------
Marking a book unavailable when it is not is RECOVERABLE -- the book is hidden
until the next poll corrects it. Clearing a book that is actually out is NOT:
it is published as borrowable while someone has it, and nothing revisits it.

Every guard in this file follows from that. The mark direction is unguarded on
purpose; the clear direction is the one that refuses, holds and asks for a
second opinion: every clear is confirmed against ground truth before it is
written, at any volume. See :func:`confirm_clears`.

It is also why the index is read as a candidate set and never written through
verbatim. The index is a lagged view, and a sibling lending field was measured
disagreeing with live availability in both directions -- so the availability
service decides every clear, per edition. "Where a dangerous clear is at stake"
used to qualify that sentence; there is no longer a clear that is not.

**Operational consequence, stated plainly: an availability-service outage stops
CLEARS, daemon-wide.** Confirming every clear is what removed the sustained
sub-threshold drain (see :func:`confirm_clears`), and the price is that the
service is now on the path of every clear rather than only of a large one. With
it down, no answers arrive, nothing is confirmed, and every clear is held:
returned books stay hidden from search until it recovers. That is the safe
direction and it is the intended behaviour -- but it is a REST STATE, not a
blip, so an outage long enough to matter wants an alarm rather than patience.
Marking is unaffected: the follower keeps marking borrows throughout, so the
daemon degrades to "slow to free" and never to "publishes a book that is out".

Note where that floor sits, because the widening is easy to read as a
regression and is not one. Search TODAY calls this same bulk service once per
request -- the ~25,000/min this project removes -- so an availability outage
already breaks today's availability annotations outright. Under the hybrid,
search is served from Solr's last-known state throughout and only the CLEARING
stops. The dependency moved from every page load to one daemon loop, so the bad
case degrades to something strictly better than where it degrades to now.

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
`ebook_unavailable` is numeric so writes qualify for Solr's
`update.partial.requireInPlace`: string and pdate fields are rejected for
in-place updates regardless of docValues/stored/indexed config, and a
*non*-in-place atomic update to a nested child document reindexes the entire
work plus all its editions rather than the one document -- which would defeat
the point of a near-realtime updater. Edition updates therefore always carry
`_root_` (the parent work's key); Solr requires it to target a child document
rather than create or replace a root-level one.

Measured 2026-10-06 against Solr 10.0.0 with this configset: the flag is
genuinely enforced on these nested child docs -- a stored+indexed field and an
unknown field are both rejected with HTTP 400 while `ebook_unavailable` is
accepted -- so an accepted write IS an in-place write rather than a silent
fall back to delete-and-re-add.

Solr also rejects `"set": null` under requireInPlace: a value can be set or
incremented in place, never cleared. That is why "available" is written as 0
rather than by removing the field, and it is the constraint
`ebook_unavailable_ts` is built around: a clear cannot erase the stamp, so a
cleared edition keeps the stamp of the mark it no longer has. That is harmless
only because the stamp is read for exactly one purpose -- deciding whether a
MARKED edition is old enough to clear -- and a mark always rewrites it. A stamp
belonging to a mark that is gone is never consulted.

Two fields, deliberately
------------------------
`ebook_unavailable` is the answer; `ebook_unavailable_ts` is when the current
unbroken run of unavailability began, and exists so the poll can refuse to
clear a mark younger than the index's lag -- see :func:`mark_update` for the
exact semantics, which the obvious paraphrase gets wrong.

Two further fields were carried through earlier revisions and are gone.
`loan_uid` persisted the changes-feed cursor per document; the cursor is now
held in memory and re-placed from the index's currency at every start, so
nothing needs to store it. `ebook_becomes_available`
held "available in N days", which the poll cannot know -- the index exposes no
due date (probed with controls: every plausible date field returns 0 documents,
and the one that exists, `loans__status__last_loan_date`, carries 2020 values
on 4% of the unavailable set) -- and which could not be kept honest anyway,
because a renewal moves the date with no event to observe and `"set": null`
cannot clear a stale one.

Recovering from drift
---------------------
No availability answer here is INFERRED from events. The follower reads
events, but only ever to mark, and a mark it misses is simply made by the next
poll -- so a missed event costs latency, never correctness, and there is no
class of change the daemon can get permanently wrong by not seeing one. A
lending policy change, copies added or removed, an item going dark, a hold
being fulfilled -- each simply changes whether the index returns that
identifier, and the next poll reflects it. The design that followed the feed
ALONE needed a separate re-check loop as a partial safety net for exactly
these; the poll has no blind spot for it to cover.

Reindex coordination: a full Solr reindex of a work rebuilds its edition
children WITHOUT this field -- the main indexer is unaware of it -- so every
reindex WIPES `ebook_unavailable` on the affected editions, and a borrowed book
momentarily reads as available.

Under the design this replaced, that was unrecoverable without an operator: the
wipe also destroyed the known-unavailable list the re-check worked from, and a
plain restart resumed from a surviving cursor rather than reconstructing, so
recovery needed --reset and a 14-day replay. **The poll removes the problem
rather than handling it.** Each poll states the whole answer, so a wiped field
is simply re-marked on the next cycle, within POLL_INTERVAL and with nothing to
run by hand. The window of exposure is one poll.
"""

import asyncio
import contextlib
import datetime
import itertools
import json
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


SOLR_QUERY_CHUNK = 500
"""Identifiers per `ia:(...)` disjunction.

One clause per identifier, against `solr.max.booleanClauses=30000` in
production. 500 leaves a wide margin and keeps each query small; the cost of
more round trips is irrelevant next to a query that fails outright.
"""
HEARTBEAT_INTERVAL = 300
"""Seconds between proof-of-life log lines.

The absence of errors is also what a stall looks like, so the daemon says the
marked count out loud on an interval rather than only when something breaks.
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
    # how large another's list is. The poll hands over the whole unavailable
    # set, and one clause per identifier against Solr's maxBooleanClauses
    # (30000 in production) fails the WHOLE query -- which propagated out and
    # killed the process. The set is ~600 today, so this is headroom rather
    # than a live need; the point is that it grows with traffic and nothing
    # here would notice it crossing the limit.
    for chunk in itertools.batched(identifiers, SOLR_QUERY_CHUNK, strict=False):
        quoted = " ".join(_phrase(id_) for id_ in chunk)
        result = await get_solr().select_async(
            query=f"type:edition AND ia:({quoted})",
            fields=["key", "ia", "_root_"],
            rows=len(chunk) * 2,
        )
        # The SAME guard fetch_marked_editions uses, and for the same reason:
        # this is the other half of the comparison that turns absence into a
        # clear. An identifier that fails to resolve is indistinguishable from
        # one the index no longer calls unavailable, so a truncated or
        # timeAllowed-cut read here proposes clearing checked-out books. Ground
        # truth would hold them, but a read known to be short is not evidence
        # of anything: skip the cycle rather than spend a call discovering it.
        #
        # It does not fire on the ordinary case of an identifier having no OL
        # edition: `num_found` counts MATCHING documents, so 3 matches out of
        # 500 requested ids is 3 found and 3 returned, which is complete. What
        # it catches is Solr matching more than it handed back. The comparison
        # is returned-versus-matched, never requested-versus-matched -- two
        # editions can share an ocaid, so matches can legitimately EXCEED the
        # identifiers asked for, and a guard sized against the request halts
        # the daemon every poll, forever.
        refuse_if_incomplete(result, len(result.docs), "edition resolve")
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

FEED_INTERVAL = 5
"""Seconds between reads of the loan-changes feed.

The feed exists here for one job: mark a borrow before the index knows about
it. That gap is the thing v3 could not cover, so this runs an order of
magnitude faster than the poll and does nothing else.
"""

ES_LAG_MARGIN = 86_400
"""How far behind live the index is assumed to be, in seconds. One day.

The poll may only clear marks OLDER than this, because a mark younger than the
index's currency is a borrow the index has not seen yet -- clearing it would
publish a checked-out book as borrowable.

**This must cover the TAIL of the lag, not the typical case**, because the two
directions are not symmetric. Too large over-holds a returned book, which the
next poll past the margin fixes. Too small clears a book the feed just marked,
which nothing fixes. So this is sized for the worst lag we have evidence of and
tightened only against measurement, never loosened on a hunch.

**It has never been measured properly.** Two things are known as of 2026-10-06,
and neither is the number this wants. Of 60 identifiers the index called
unavailable, 3 were already free in live ground truth -- a 5% staleness RATE at
one instant, not a duration. And a watch on those three saw none of them leave
the index's unavailable set within an hour, which says the tail is at least
that and gives no upper bound. An initial 3600 was chosen before that watch and
was very likely already too small.

The real number is the changes feed's event timestamps compared against when
the index reflects them, which needs feed credentials and the production box.
Until then: a day, deliberately.

**The margin is not free, and the target is not "as large as possible".** A
mark cannot be cleared until it is older than the margin, so a returned book is
over-held by:

    over_hold = max(0, margin - loan_duration - lag)

A fourteen-day borrow pays nothing: by the time the index reflects its return
the mark is days old, far past any sane margin. A two-hour browse session under
a day-sized margin with an hour of lag is over-held about 21 hours -- hidden
from search while still borrowable, which is the safe direction and a real
freshness cost all the same. Short sessions pay the whole bill.

So the target is **just above the measured lag tail**: large enough that a
recent borrow can never be cleared, and no larger, because every second beyond
the tail is over-hold on short loans and buys nothing. 86,400 is a conservative
START chosen with no upper bound on the tail in hand. The box measurement
should size it DOWN, and that tightening is the whole of what reduces the cost.

**Versus the poll-only design this descends from:** that one has no margin, so
it clears short returns promptly -- and can wrongly clear a recent borrow the
index has not seen, publishing a checked-out book as borrowable, which nothing
corrects. This moves that error into the safe direction and pays for it in
over-held short loans. The margin is the dial between the two, and measuring
the tail is what lets it be set honestly rather than guessed.
"""

MARKED_SET_MAX = 50_000
"""Ceiling on the marked set read back from Solr.

Not a working limit -- the live unavailable set measured 766 on 2026-10-05 --
but the read must be COMPLETE or the reconcile is wrong in the dangerous
direction: an edition outside a capped window is indistinguishable from one the
index no longer calls unavailable, and would be cleared.
"""


class PollRefused(Exception):
    """This cycle's inputs were not trustworthy, so prior state stands.

    Every untrustworthy-input case resolves the same way -- skip the cycle,
    keep what Solr already has, alarm -- because at poll cadence the
    alternative is a crash loop during routine index churn. Raising was right
    when the read happened once at startup; it is wrong at cadence, and the
    predicate changing is what makes the old response stale.
    """


def refuse_if_incomplete(result, returned: int, what: str) -> None:
    """Raise unless a Solr read returned everything it was asked for.

    Two ways a select comes back short with HTTP 200 and no error: more
    documents matched than `rows` asked for, and `timeAllowed` (10s by default
    in :meth:`Solr.select_async`) tripping mid-query, which sets
    `responseHeader.partialResults`. Both are invisible unless looked for.

    This matters because the reconcile turns ABSENCE into a clear. An edition
    missing from a truncated read is indistinguishable from one the index no
    longer calls unavailable, so a short read is a mass-clear by another route.
    Ground truth would now hold those clears, but refusing here is still right:
    a read known to be short is not evidence of anything, and spending a
    ground-truth call to discover that is worse than skipping the cycle.
    """
    num_found = getattr(result, "num_found", None)
    if isinstance(num_found, int) and num_found > returned:
        raise PollRefused(f"{what}: Solr matched {num_found} documents but returned {returned}; refusing to treat a truncated read as the set")
    header = getattr(result, "response_header", None) or {}
    if isinstance(header, dict) and header.get("partialResults"):
        raise PollRefused(f"{what}: Solr reported partialResults, so the read timed out mid-query; refusing to treat it as the set")


async def fetch_marked_editions() -> dict[str, dict]:
    """Every edition Solr currently has marked unavailable, or refuse.

    Complete or raises, for the reason in MARKED_SET_MAX: a truncated read
    makes absent-from-the-window look identical to absent-from-the-index, and
    the reconcile clears on absence.
    """
    result = await get_solr().select_async(
        query=f"type:edition AND ebook_unavailable:{EBOOK_UNAVAILABLE}",
        fields=["key", "ia", "_root_", "ebook_unavailable_ts"],
        rows=MARKED_SET_MAX,
    )
    docs = result.docs
    if len(docs) >= MARKED_SET_MAX:
        raise PollRefused(f"Marked set reached the {MARKED_SET_MAX}-edition read cap; cannot tell a complete read from a truncated one")
    refuse_if_incomplete(result, len(docs), "marked-set read")
    return {doc["key"]: doc for doc in docs}


async def confirm_clears(to_clear: list[dict], marked_total: int, index_total: int) -> list[dict]:
    """Settle EVERY proposed clear against ground truth, or hold it.

    The poll proposes; ground truth disposes. Nothing is cleared on the index's
    word alone, at any volume. This is the only guard in the clear direction
    that a sustained fault cannot walk past, and it is unconditional for a
    measured reason.

    **What this replaced, and why it had to go.** This used to run only when a
    relative-change breaker tripped -- a clear set larger than
    `max(25, 10% of the editions the index dropped)`. Three facts composed into
    a complete bypass. The 10% only binds above 250 dropped editions, so below
    that the absolute floor WAS the entire guard; the floor was a per-poll
    allowance with no memory across polls; and the poll runs every
    POLL_INTERVAL = 15 seconds. An index degraded such that it dropped ~24
    identifiers per cycle therefore never tripped it and never made a single
    ground-truth call -- and against the measured live unavailable set of 766,
    31 such polls is 465 seconds. The whole marked set could be cleared
    unconfirmed in under eight minutes, 25 at a time, with nothing above INFO
    in the log. That is precisely the event the breaker existed to prevent,
    reached by staying just underneath it, in the direction nothing undoes.

    Neither other layer covers it: the timestamp gate is silent about old marks
    by design, and a breaker that never trips never confirms.

    **Why always-confirm is affordable.** The clear set is bounded by the
    borrow-return rate, not by the collection -- a normal cycle clears 0-2 out
    of ~766 marked (measured 2026-10-05) -- and `get_availability_async`
    batches at AVAILABILITY_BATCH_SIZE. So the steady-state cost is about one
    bulk request per poll, ~4/min, against the ~25,000/min this project
    removes. Even a top-of-hour clump of expiring browses is a handful of
    batched requests. This is the FAST bulk endpoint, not the per-item Lending
    Status Endpoint whose >10s/item is what killed v2.

    The answer is per-edition and never sampled: a sample that comes back
    available supports "legitimate mass-free" without establishing it. Each
    edition is decided on its own answer, and anything the service has no
    answer for keeps its mark.

    Two checks whose blind spots do not overlap -- the index is fast and
    lagged, ground truth is slow and authoritative -- and every clear needs
    both to agree.
    """
    identifiers = [ia for doc in to_clear for ia in (doc.get("ia") or [])]
    if not identifiers:
        logger.error("Clear: %d editions would clear but none carry an ocaid; holding every clear this cycle", len(to_clear))
        return []

    availability = await lending.get_availability_async("identifier", identifiers, use_cache=False)

    def answered(ia_id: str) -> bool:
        answer = availability.get(ia_id)
        # A failed batch comes back as an "error" status per identifier rather
        # than as a missing key, so both shapes mean the same thing: nobody
        # told us anything about this book.
        return isinstance(answer, dict) and answer.get("status") != "error"

    def is_free(ia_id: str) -> bool:
        # No answer is not an answer: an edition the service skipped keeps its
        # mark, because the clear direction is the unrecoverable one.
        return answered(ia_id) and lending.is_available_for_loan(availability[ia_id])

    # SAY SO WHEN THE SERVICE IS NOT ANSWERING. Holding clears is the right
    # response to an outage, but it is also indistinguishable from a quiet
    # collection: the daemon keeps polling, keeps marking, logs its ordinary
    # INFO line, and availability silently stops moving for the duration. A
    # held clear is invisible by construction -- nothing is written -- so if
    # this is not said loudly, nothing says it at all.
    if unanswered := [ia for ia in identifiers if not answered(ia)]:
        logger.error(
            "Clear: the availability service answered for only %d of %d identifiers; %d unanswered, so every clear "
            "resting on one is HELD this cycle. A run of these is an outage, and clears stay frozen for its whole "
            "length while the daemon otherwise looks healthy. Marking is unaffected.",
            len(identifiers) - len(unanswered),
            len(identifiers),
            len(unanswered),
        )

    confirmed = [doc for doc in to_clear if any(is_free(ia) for ia in (doc.get("ia") or []))]

    if not confirmed:
        # Hold every CLEAR -- and let the marks through: an index that has
        # stopped listing returned books is still listing borrowed ones, and
        # refusing to mark those would publish checked-out books as borrowable
        # for the length of the outage.
        #
        # Two different causes reach here and the message has to say which, or
        # an outage reads as a degraded index and gets investigated in the
        # wrong place: either the service answered and disagreed with the
        # index, or it never answered at all.
        cause = (
            "the availability service answered for none of them, so this is an outage rather than a disagreement"
            if len(unanswered) == len(identifiers)
            else "ground truth disagreed with the index, so the index is wrong rather than the collection freeing"
        )
        logger.error(
            "Clear: confirmed 0 of %d editions as available against %d marked and %d returned by the index -- %s; holding every clear this cycle",
            len(to_clear),
            marked_total,
            index_total,
            cause,
        )
        return []

    # Disagreement is the signal worth paging on, not volume: the index saying
    # "returned" while ground truth says "still out" is what a degraded index
    # looks like, at any size. A clean cycle stays at INFO.
    held = len(to_clear) - len(confirmed)
    if held:
        logger.warning(
            "Clear: ground truth confirmed %d of %d editions as genuinely available against %d marked; holding the other %d, "
            "which the index called returned and ground truth did not",
            len(confirmed),
            len(to_clear),
            marked_total,
            held,
        )
    else:
        logger.info("Clear: ground truth confirmed all %d proposed editions as available", len(confirmed))
    return confirmed


# ---------------------------------------------------------------------------
# The FOLLOWER, restored verbatim from the v2 commit b9d2c2504.
#
# It marks from events alone and never clears. That is not a limitation to work
# around -- it is the division of labour the hybrid rests on. The feed knows
# about a borrow within seconds and cannot know about an expiry at all; the
# index knows about both and is late. So the feed marks, the poll clears, and
# neither can undo the other's direction.
#
# It over-marks on purpose: a borrow of one copy of a multi-copy item, or a
# return on a waitlisted book, both write "unavailable" when the book may be
# free. That error is the recoverable one and the poll corrects it. Reaching
# for availability data here to avoid it is the design this whole PR exists to
# not repeat.
# ---------------------------------------------------------------------------

# Event types that RELEASE capacity. Everything else is treated as acquiring
# it, including a type we have never seen.
#
# The asymmetry is deliberate and it is the safety property of this design.
# Acquiring is written straight from the event with no ground-truth call, so an
# unknown type errs toward `unavailable` -- which the next poll corrects against
# the index, within POLL_INTERVAL. Erring the other way would publish a book as
# borrowable when it is not, and nothing would correct it.
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


_SEEN_ACQUIRING_EVENT_TYPES = frozenset({"borrow", "browse", "renew_borrow", "renew_browse", "renew"})
"""Acquiring verbs seen in the wild, used only to decide what to WARN about.

Not a gate: anything not releasing is treated as acquiring regardless, so a new
IA verb errs toward "unavailable" -- the recoverable direction -- and surfaces
in the log rather than silently changing behaviour.
"""


def is_releasing_event(event_type: str) -> bool:
    """Whether this event type frees capacity. Unknown verbs are not releasing."""
    lowered = (event_type or "").lower()
    return any(stem in lowered for stem in RELEASING_EVENT_STEMS)


BATCH_SIZE = lending.LOAN_CHANGES_MAX_LIMIT
"""Rows per feed page. Pinned to IA's own ceiling rather than restated: asking
for more is silently capped, so a larger number here would quietly mean fewer
events per request than the code claims."""


def collect_dirty_identifiers(rows: list[dict]) -> dict[str, dict]:
    """Reduce a batch of rows to the set of identifiers needing a ground-truth check.

    Returns {identifier: {"uid": int, "until": str|None, "event_type": str, "time": str|None}}
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
        # `time` is carried so a mark can be stamped with when the event
        # happened rather than when the batch was read. See event_epoch().
        latest[identifier] = {"uid": uid, "until": until, "event_type": row.get("event_type") or "", "time": row.get("time")}
    return latest


def event_epoch(state: dict) -> int | None:
    """Epoch seconds for when a change event actually happened, if the row says.

    The feed's row carries `time`; `collect_dirty_identifiers` keeps it on the
    state. Parsed leniently because an unparsable timestamp must not stop a
    mark -- the caller falls back to now, which over-protects rather than
    under-protects.
    """
    raw = state.get("time")
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00").replace(" ", "T"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # IA's rows carry "YYYY-MM-DD HH:MM:SS" with NO offset, and a naive
        # datetime's .timestamp() silently applies the HOST's local zone. The
        # result is compared against a UTC epoch currency, so off UTC every
        # feed mark is stamped hours wrong -- and in which direction depends on
        # the sign of the offset, which nothing pins.
        #
        # A day-sized margin absorbs it today. It stops absorbing it the moment
        # ES_LAG_MARGIN is tightened toward the measured lag tail, which is the
        # documented plan: at an hour-sized margin a mark stamped seven hours
        # in the past is clearable by the very next poll, so a borrow would be
        # marked and unmarked within seconds.
        parsed = parsed.replace(tzinfo=datetime.UTC)
    return int(parsed.timestamp())


def build_solr_updates(
    dirty: dict[str, dict],
    id_to_edition: dict[str, dict],
) -> list[dict]:
    """Build Solr atomic-update documents from the events alone.

    Write-only, in one direction: an acquiring event sets ``ebook_unavailable=1``
    and stamps ``ebook_unavailable_ts``; a releasing event writes NOTHING. All
    clearing is done by :func:`build_poll_updates`, from the index.

    That split is the whole design, and the releasing case is the reason for it.
    A return does not mean available -- if anyone is queued, the freed copy goes
    to the head of the waitlist and the book stays unborrowable. Clearing on a
    return event would therefore publish a book as borrowable when it is not,
    and the feed would never say otherwise, because the feed cannot report
    expiry at all. Declining to write is what keeps every clear on the path that
    has actually checked.

    The converse error is harmless and self-correcting: marking a multi-copy
    item unavailable when one of several copies was borrowed is wrong, and the
    next poll frees it once the index agrees. So this path never consults the
    availability service, and the follower keeps up with the changes feed even
    while that service is down -- which is what keeps an availability outage to
    "clears stop" rather than "the daemon stops".

    An identifier with no Solr edition is skipped -- a new item, or its work is
    mid-reindex. There is no doc to mark, so the event is skipped while the
    cursor still advances; the book stays unmarked until its next event or until
    a poll picks it up from the index, which is the backstop that makes the skip
    acceptable rather than a hole.
    """
    now = int(time.time())
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

        # Stamped with WHEN THE EVENT HAPPENED where the feed says so, not with
        # the wall clock. A batch read at 10:00 may carry an event from 09:58,
        # and stamping it 10:00 would claim the mark is fresher than it is --
        # buying it protection from the poll that it has not earned. Falling
        # back to now is the safe direction when the row carries no usable
        # time: it over-protects by seconds, never under-protects.
        updates.append(mark_update(edition["key"], edition["root"], event_epoch(state) or now))

    if unrecognized:
        # Not an error -- IA's event_type vocabulary is not published, so this is
        # how we learn of one. Treated as acquiring, the safe direction.
        logger.warning("Unrecognized loan event_types treated as acquiring: %r", unrecognized)
    return updates


def mark_update(key: str, root: str, at: int) -> dict:
    """One edition marked unavailable, stamped with when.

    Both writers go through here so a mark can never be written without its
    timestamp. The guard in the poll reads that timestamp to decide whether the
    index is entitled to contradict it; a mark with no timestamp would read as
    epoch 0 and be clearable immediately, which is the exact failure the stamp
    exists to prevent.
    **Read the semantics precisely, because the obvious paraphrase is a trap.**
    This is *when the current unbroken run of unavailability began*, not "when
    the mark was last re-asserted". The poll skips editions already in the
    marked set, so a book's stamp is frozen for the life of its mark and is
    refreshed only when it is cleared and marked again, or when the FEED sees a
    fresh acquiring event for it.

    Re-stamping every marked edition each cycle would put the stamp at roughly
    `now` forever, so `stamp > index_currency` would always hold, no clear would
    ever proceed, and availability would freeze permanently. If you are tempted
    to "fix" the skip, that is the bug you are adding.

    The stamp is the daemon host's wall clock, and it is compared against a
    currency derived from archive.org's index: the same UNIT, not the same
    CLOCK. ES_LAG_MARGIN is generous enough to absorb ordinary skew, but a
    margin tightened toward the measured lag tail must leave room for it rather
    than assuming the two agree to the second.
    """
    return {
        "key": key,
        "_root_": root,
        "ebook_unavailable": {"set": EBOOK_UNAVAILABLE},
        "ebook_unavailable_ts": {"set": at},
    }


def stamp_unstamped(doc: dict, at: int) -> dict:
    """Give a marked-but-unstamped edition a stamp, without changing the mark.

    These exist for one window only: documents marked before a daemon that
    writes the stamp. The poll will not clear them, because it refuses to judge
    an unknown age -- so left alone they would be hidden forever. One write
    turns each into an ordinary recent mark, which the next margin's worth of
    polls then handles by the normal rule.

    It writes `ebook_unavailable` as well as the stamp, deliberately: these
    documents ARE marked, so re-asserting the value is a no-op, and sending
    both keeps every write in this daemon going through the same two-field
    shape -- which is the shape the schema and `requireInPlace` were verified
    against.
    """
    return mark_update(doc["key"], doc["_root_"], at)


def _marked_at(doc: dict) -> int | None:
    """When this edition was marked, or None if Solr has no stamp for it.

    None, not 0. An unset docValues field is OMITTED from a Solr response
    rather than returned as zero, so "missing" is a real third state and the
    caller has to decide about it rather than inherit a number.

    Both obvious defaults are wrong, which is why there is no default:

    * Treat it as 0 (very old) and the gate clears it immediately. If that mark
      is in fact recent, the book is published as borrowable while someone has
      it, and no event follows until the loan ends -- the unrecoverable
      direction.
    * Treat it as now (protected) and the gate NEVER clears it. Nothing would
      ever give it a stamp either, so the book stays hidden permanently.

    See :func:`stamp_unstamped` for what the poll does instead.
    """
    value = doc.get("ebook_unavailable_ts")
    return value if isinstance(value, int) else None


async def drop_clears_overtaken_by_a_mark(to_clear: list[dict], index_current_as_of: int) -> list[dict]:
    """Re-read the clear set's stamps and drop any the feed has just marked.

    The gate above decides from a snapshot taken at the start of the cycle, and
    the write lands seconds later. The feed loop writes to these same editions
    throughout. So a book returned days ago, legitimately clearable, can be
    RE-BORROWED during the poll: the feed stamps it, and then the poll's
    already-decided clear lands on top and publishes a checked-out book as
    borrowable. Nothing revisits it until the index notices the new borrow,
    which is a lag window away -- the unrecoverable direction, and the one
    every guard in this file exists for.

    Read through Solr's REAL-TIME GET rather than a select, which is the whole
    reason this works: the feed writes with `commit=False`, so a searcher-based
    read would not see a mark made inside the soft-commit window -- exactly the
    marks that are most likely to be racing. `/get` returns the latest version
    including uncommitted updates.

    This narrows the window from the poll's whole duration to the gap between
    this read and the write. It does not close it. Closing it needs optimistic
    concurrency on `_version_`, which Solr supports and the in-place update
    path here does not currently carry; narrowing is what is cheap and correct
    today, and the residue is bounded by a few milliseconds rather than by how
    long a poll takes.
    """
    if not to_clear:
        return to_clear
    keys = [doc["key"] for doc in to_clear]
    fresh = await get_solr().get_many_async(keys, fields=["key", "ebook_unavailable", "ebook_unavailable_ts"])
    by_key = {doc["key"]: doc for doc in fresh}

    kept, overtaken = [], 0
    for doc in to_clear:
        latest = by_key.get(doc["key"])
        if latest is None:
            # It vanished between the two reads -- a reindex, most likely.
            # Nothing to clear, and writing to it would 400 under
            # requireInPlace anyway.
            overtaken += 1
            continue
        at = _marked_at(latest)
        if at is None or at > index_current_as_of:
            # Re-stamped since the snapshot, or its stamp disappeared. Either
            # way this is no longer a clear we are entitled to make.
            overtaken += 1
            continue
        kept.append(doc)

    if overtaken:
        logger.info("Dropped %d clears overtaken by a fresh mark during the poll", overtaken)
    return kept


async def build_poll_updates(unavailable_identifiers: list[str], index_current_as_of: int) -> list[dict]:
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

    # LAYER 2 of three. The index is late, so a mark made AFTER the moment the
    # index can speak to is a borrow the index has not seen yet -- its absence
    # from the unavailable set means "not yet known", not "returned". Clearing
    # it would publish a checked-out book as borrowable, which nothing undoes.
    #
    # This protects RECENT marks only, and that is the whole of what it does. A
    # book ten days into a fourteen-day loan has a mark far older than the
    # margin, so it is eligible to be cleared and this guard is silent about
    # it. Old marks are covered by the ground-truth confirmation below, which
    # is a different population and not a backup for this one.
    candidates = [doc for key, doc in marked.items() if key not in should_be_marked]
    # A mark with no stamp is not aged, it is UNKNOWN, and the gate refuses to
    # decide on unknown. Stamping it converts the unknown into a known and
    # deliberately conservative age -- the book is then protected for one
    # margin and judged normally after that, so the situation resolves itself
    # within a bounded time instead of being guessed at now.
    unstamped = [doc for doc in candidates if _marked_at(doc) is None]
    datable = [doc for doc in candidates if _marked_at(doc) is not None]
    to_clear = [doc for doc in datable if (_marked_at(doc) or 0) <= index_current_as_of]
    too_fresh = len(datable) - len(to_clear)

    # LAYER 3 of three, and the only one a sustained fault cannot walk past.
    # EVERY proposed clear is confirmed against ground truth, at any volume --
    # there is no threshold to stay underneath. :func:`confirm_clears` records
    # what the threshold version let through and why it is gone.
    #
    # Only the CLEAR set is ever held back. Marking needs no confirmation -- it
    # is the recoverable direction -- and dropping the marks alongside a held
    # clear would publish newly-borrowed books as available for as long as the
    # index stayed degraded: the same failure this exists to prevent, reached
    # from the other side.
    if to_clear:
        to_clear = await confirm_clears(to_clear, len(marked), len(unavailable_identifiers))

    # Marks the POLL makes are stamped now, not with the index's currency: this
    # book is unavailable as of this read, and the stamp is what protects it
    # from the next poll.
    now = int(time.time())
    # Last thing before the write: the feed may have marked one of these while
    # this poll was running. See drop_clears_overtaken_by_a_mark.
    to_clear = await drop_clears_overtaken_by_a_mark(to_clear, index_current_as_of)

    updates = [mark_update(info["key"], info["root"], now) for info in to_mark]
    updates += [stamp_unstamped(doc, now) for doc in unstamped]
    updates += [{"key": doc["key"], "_root_": doc["_root_"], "ebook_unavailable": {"set": EBOOK_AVAILABLE}} for doc in to_clear]

    # Counts, every cycle, so write volume is observable without a profiler --
    # the disk-growth investigation needs this and a rate is invisible in a
    # per-event log.
    logger.info(
        "Poll: index=%d resolved=%d marked=%d mark=%d clear=%d held_too_fresh=%d stamped_unknown=%d",
        len(unavailable_identifiers),
        len(should_be_marked),
        len(marked),
        len(to_mark),
        len(to_clear),
        too_fresh,
        len(unstamped),
    )
    return updates


async def count_marked_editions() -> int | None:
    """How many editions carry the mark, without fetching them.

    `rows=0` so Solr returns the count and no documents; the heartbeat wants a
    number, and the marked set is up to MARKED_SET_MAX documents to drag back
    for a `len()`.
    """
    try:
        result = await get_solr().select_async(query=f"type:edition AND ebook_unavailable:{EBOOK_UNAVAILABLE}", fields=["key"], rows=0)
        return result.num_found
    except Exception:
        # Deliberately broad. This was OSError/ValueError/KeyError/RuntimeError,
        # and httpx.HTTPError is NOT an OSError -- so a Solr timeout here
        # escaped into the poll loop's handler and was logged as "Poll failed;
        # prior state stands" AFTER a poll that had in fact succeeded and
        # written. A heartbeat must never stop the daemon, and must never
        # misreport one either.
        logger.debug("Heartbeat could not count marked editions", exc_info=True)
        return None


async def log_heartbeat() -> None:
    """Proof of life, because the absence of errors is also what a stall looks like.

    Deliberately a log line and not a metrics integration: the requirement is
    that the question be answerable from outside, not dashboarded.
    """
    logger.info("Heartbeat: editions_marked_unavailable=%s", await count_marked_editions())


async def bootstrap_feed_cursor(margin: int = ES_LAG_MARGIN) -> int:
    """Place the feed cursor at the index's currency, not at the feed's head.

    The follower exists to cover exactly one gap: borrows the index has not
    seen yet. So it must start where the index's knowledge ends -- roughly now
    minus the lag margin -- and replay forward from there. Starting at the head
    leaves the gap uncovered until the next borrow; starting at the beginning
    replays days of events to no purpose.

    Nothing records "the uid at time T", so this reads the feed's DEFAULT
    response -- no `after_uid`, which returns the most recent `limit` rows --
    and walks back to the first event at or before the target time.

    **This depends on an external petabox change.** The default-limit behaviour
    is Mek's changes-API PR; until that lands the feed may ignore a missing
    `after_uid`, and this falls back to the head, which degrades to "the gap is
    uncovered until the next borrow" rather than to anything unsafe. The PR is
    a real dependency of the shipping daemon, not an optimisation.
    """
    target = int(time.time()) - margin
    resp = await lending.get_loan_changes(limit=BATCH_SIZE)
    if resp.get("status") != "OK":
        # follow_feed_once checks this and the bootstrap did not, so a 200
        # carrying {"status": "ERROR"} fell into the no-rows branch below and
        # printed a confident, wrong "starting at the head 0".
        raise PollRefused(f"Feed returned status={resp.get('status')!r} to the cursor bootstrap")
    rows = resp.get("rows") or []
    head = resp.get("latest_uid") or 0

    if not rows:
        logger.warning("Feed returned no rows for the cursor bootstrap; starting at the head %d and leaving the lag gap uncovered until the next event", head)
        return head

    # Oldest first, so the first row at or before the target is the last event
    # the index can be assumed to know about.
    dated = sorted(
        ((event_epoch(r) or 0, r.get("uid")) for r in rows if isinstance(r.get("uid"), int)),
        key=lambda pair: pair[1],
    )
    at_or_before = [uid for when, uid in dated if when and when <= target]
    if at_or_before:
        cursor = max(at_or_before)
        logger.info("Feed cursor bootstrapped to uid %d (index currency ~%ds ago); replaying the lag gap", cursor, margin)
        return cursor

    # Every row in the window is NEWER than the index's currency, so the window
    # does not reach back far enough. Start at its oldest row: that covers as
    # much of the gap as the feed will show, and under-covering is visible in
    # the log rather than silent.
    oldest = min(uid for _, uid in dated)
    logger.warning(
        "Feed's %d-row window starts after the index's currency; bootstrapping at its oldest uid %d, so part of the lag gap is uncovered",
        len(dated),
        oldest,
    )
    return oldest


async def follow_feed_once(after_uid: int, dry_run: bool) -> int:
    """LAYER 1 of three: mark new borrows before the index knows about them.

    Marks only, never clears, and never consults availability. A borrow of one
    copy of a multi-copy item is marked unavailable here even though the book
    is free -- that over-mark is the recoverable error and the poll corrects
    it. Asking an availability service to avoid it is the per-item call this
    design exists to not make.
    """
    resp = await lending.get_loan_changes(after_uid=after_uid, limit=BATCH_SIZE)
    if resp.get("status") != "OK":
        logger.error("Loan changes API returned status=%r; cursor held at %d", resp.get("status"), after_uid)
        return after_uid

    rows = resp.get("rows") or []
    if not rows:
        return after_uid

    valid = [r["uid"] for r in rows if isinstance(r.get("uid"), int)]
    if not valid:
        logger.warning("Feed batch of %d rows carried no valid uid; cursor held at %d", len(rows), after_uid)
        return after_uid
    new_uid = max(valid)
    if new_uid <= after_uid:
        # Without this the cursor can move BACKWARDS and the loop spins with no
        # sleep -- measured at 201 API calls in 0.21s on an earlier revision.
        logger.warning("Feed returned %d rows but none past uid %d", len(rows), after_uid)
        return after_uid

    dirty = collect_dirty_identifiers(rows)
    id_to_edition = await resolve_edition_keys(list(dirty))
    updates = build_solr_updates(dirty, id_to_edition)
    if updates and not dry_run:
        await solr_update_in_place(updates, commit=False)
    logger.info("Feed: %d rows over %d ocaids, %d marks (uid %d->%d)", len(rows), len(dirty), len(updates), after_uid, new_uid)
    return new_uid


async def main(
    ol_config: str,
    poll_interval: int = POLL_INTERVAL,
    feed_interval: int = FEED_INTERVAL,
    es_lag_margin: int = ES_LAG_MARGIN,
    dry_run: bool = False,
):
    """Keep Solr current on borrowability from two sources, forever.

    Useful environment variables:
    - OL_SOLR_BASE_URL: Override the Solr base URL

    :param ol_config: Path to openlibrary.yml config file.
    :param poll_interval: Seconds between index polls (the clearing half).
    :param feed_interval: Seconds between loan-changes reads (the marking half).
    :param es_lag_margin: How far behind live the index is assumed to be.
    :param dry_run: Compute and log updates but do not write to Solr.

    THREE LAYERS, each covering a population the others do not:

    1. The FEED marks new borrows within `feed_interval`. It covers books the
       index has not heard about yet, which is the gap the poll-only design
       could not close and the reason this exists.
    2. The TIMESTAMP GUARD stops a lagged poll clearing a mark younger than the
       index's currency. It covers RECENT marks, and only those.
    3. GROUND-TRUTH CONFIRMATION of every clear stops a degraded index clearing
       OLD marks -- the population layer 2 is silent about, because their
       timestamps are long past the margin. Unconditional, at any volume: a
       threshold here was a complete bypass, since a sustained sub-threshold
       drop never tripped it. See :func:`confirm_clears`.

    Neither writer can undo the other's direction: the feed only marks, the
    poll only clears. That is v2's asymmetry, with the index poll standing in
    for the per-item ground truth that was too slow to call.

    What this does NOT do is eliminate staleness. A loan that EXPIRES is
    invisible to the feed -- that was v2's fatal flaw -- so the book stays
    marked until the index catches up, one lag window later. The hybrid BOUNDS
    staleness to that window and keeps it in the SAFE direction: a returned
    book stays hidden briefly, rather than a checked-out book being published
    as borrowable. The borrow click re-checks live, so the cost is a book
    temporarily absent from results, not a broken one.

    Every failure resolves the same way -- log, keep prior state, try again --
    because at these cadences an exception is a crash loop.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)-15s %(levelname)s %(message)s")
    logger.info(
        "BEGIN loan_availability_updater poll=%ds feed=%ds es_lag_margin=%ds dry_run=%s",
        poll_interval,
        feed_interval,
        es_lag_margin,
        dry_run,
    )

    load_config(ol_config)
    lending.setup(infogami.config)
    req_context.set(create_context_for_script())
    init_sentry(getattr(infogami.config, "sentry", {}))

    try:
        cursor = await bootstrap_feed_cursor(es_lag_margin)
    except Exception:
        # NOT 0. `after_uid=0` is itself an error on this API, so a zero cursor
        # makes every single feed read raise -- the marking half permanently
        # inert, the daemon silently degraded to the poll-only design this
        # exists to replace, and an exception every FEED_INTERVAL seconds into
        # logs and Sentry while the heartbeat still reports healthy because it
        # only counts marked editions.
        #
        # This is the expected state until the petabox changes-API default
        # behaviour ships, so it has to degrade well rather than loudly.
        logger.exception("Could not bootstrap the feed cursor; falling back to the feed head")
        cursor = await feed_head()

    if not cursor:
        logger.error(
            "No feed cursor could be established, so the marking half will not run and this is a POLL-ONLY daemon for now. "
            "Books borrowed since the index's last update stay unmarked until it catches up. Said once, here, rather than every cycle."
        )
        await _poll_loop(poll_interval, es_lag_margin, dry_run)
        return

    await asyncio.gather(
        _feed_loop(cursor, feed_interval, dry_run),
        _poll_loop(poll_interval, es_lag_margin, dry_run),
    )


async def feed_head() -> int:
    """The newest uid the feed will admit to, or 0 if it will not say.

    Asked with `after_uid=1` rather than with no parameter, because the
    no-parameter form is the thing that may not exist yet -- this is the
    fallback for when it does not.
    """
    try:
        resp = await lending.get_loan_changes(after_uid=1, limit=1)
        return resp.get("latest_uid") or 0
    except Exception:
        logger.exception("Could not read the feed head either")
        return 0


async def _feed_loop(cursor: int, feed_interval: int, dry_run: bool) -> None:
    while True:
        try:
            cursor = await follow_feed_once(cursor, dry_run)
        except Exception:
            logger.exception("Feed read failed; cursor held at %d", cursor)
        await asyncio.sleep(feed_interval)


async def _poll_loop(poll_interval: int, es_lag_margin: int, dry_run: bool) -> None:
    last_heartbeat = 0.0
    while True:
        try:
            # Taken BEFORE the request, not after: the index's answer describes
            # the world at some instant at or before this one, so the earlier
            # timestamp is the conservative one to measure currency from.
            poll_started_at = int(time.time())
            unavailable = await lending.get_checked_out_candidates_async()
            updates = await build_poll_updates(unavailable, poll_started_at - es_lag_margin)
            if updates and not dry_run:
                # Never a hard commit. One opens a new searcher and invalidates
                # every Solr cache on the instance serving openlibrary.org, and
                # at this cadence that is thousands a day. autoSoftCommit makes
                # the write visible within a second and autoCommit persists it.
                await solr_update_in_place(updates, commit=False)
            elif updates:
                logger.info("Dry run: %d updates not written", len(updates))

            now = time.monotonic()
            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                await log_heartbeat()
                last_heartbeat = now
        except lending.CheckedOutSeedIncomplete, PollRefused:
            logger.exception("Poll refused; prior state stands")
        except Exception:
            # EVERYTHING the cycle does is inside this try, the Solr write
            # included. A Solr error escaping here used to kill the process.
            logger.exception("Poll failed; prior state stands")

        await asyncio.sleep(poll_interval)


if __name__ == "__main__":
    from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

    FnToCLI(main).run()
