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
docker/ol-solr-updater-start.sh, next to the main solr_updater). Every
POLL_INTERVAL seconds it:

  1. Asks archive.org's search index which books are lendable but currently
     neither borrowable nor browsable -- i.e. who is checked out right now
     (lending.get_checked_out_candidates_async -> GET advancedsearch.php).
  2. Looks up the Solr EDITION document for each of those identifiers (by
     ocaid), and reads back which editions Solr currently has marked.
  3. Issues ONE bulk in-place update: `ebook_unavailable` set to 1 on the
     newly-unavailable, 0 on the ones that have been returned or expired.

That is the whole loop. There is no cursor, no state file and no --reset,
because each poll is a complete statement of what should be marked rather than
an increment on top of what came before.

Nothing reads this Solr field yet -- wiring search/pages to it is a follow-up.

Why there is no cold start
--------------------------
The first poll after any start IS the cold start, and it costs exactly what
every other poll costs. A restart needs no catch-up, a lost state file is not a
concept, and a reindex that wipes the field self-heals on the next cycle. The
operator step that used to exist is deleted rather than automated: nothing can
be forgotten if there is nothing to remember.

The asymmetry that shapes everything here
-----------------------------------------
Marking a book unavailable when it is not is RECOVERABLE -- the book is hidden
until the next poll corrects it. Clearing a book that is actually out is NOT:
it is published as borrowable while someone has it, and nothing revisits it.

Every guard in this file follows from that. The mark direction is unguarded on
purpose; the clear direction is the one that refuses, holds and asks for a
second opinion. See CLEAR_BREAKER_FRACTION and :func:`confirm_mass_clear`.

It is also why the index is read as a candidate set and never written through
verbatim. The index is a lagged view, and a sibling lending field was measured
disagreeing with live availability in both directions -- so where a dangerous
clear is at stake, the availability service decides, per edition.

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
rather than by removing the field, and why there is no field here holding a
timestamp -- there would be no way to clear one when it went stale.

One field, deliberately
-----------------------
Two others were carried through earlier revisions and are gone. `loan_uid` was
the changes-feed cursor, and there is no feed and no cursor. `ebook_becomes_available`
held "available in N days", which the poll cannot know -- the index exposes no
due date (probed with controls: every plausible date field returns 0 documents,
and the one that exists, `loans__status__last_loan_date`, carries 2020 values
on 4% of the unavailable set) -- and which could not be kept honest anyway,
because a renewal moves the date with no event to observe and `"set": null`
cannot clear a stale one.

Recovering from drift
---------------------
Nothing here infers availability from events, so there is no class of change
the daemon can miss by not seeing one. A lending policy change, copies added or
removed, an item going dark, a hold being fulfilled -- each simply changes
whether the index returns that identifier, and the next poll reflects it. The
previous design needed a separate re-check loop as a partial safety net for
exactly these; the poll has no blind spot for it to cover.

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

**The one real cost of a large margin**, so it is not a surprise: a mark cannot
be cleared until it is older than the margin, so a loan SHORTER than the margin
is over-held by up to (margin - loan duration). Ordinary multi-day loans pay
nothing -- by the time the index reflects their return, the mark is days old --
so this falls entirely on short loans, it is bounded by the margin, and it is
in the safe direction: the book is briefly hidden from search while the borrow
click still works.
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


def refuse_if_incomplete(result, returned: int, what: str) -> None:
    """Raise unless a Solr read returned everything it was asked for.

    Two ways a select comes back short with HTTP 200 and no error: more
    documents matched than `rows` asked for, and `timeAllowed` (10s by default
    in :meth:`Solr.select_async`) tripping mid-query, which sets
    `responseHeader.partialResults`. Both are invisible unless looked for.

    This matters because the reconcile turns ABSENCE into a clear. An edition
    missing from a truncated read is indistinguishable from one the index no
    longer calls unavailable, so a short read is a mass-clear by another route
    -- and, unlike the breaker's case, a quiet one that stays under the
    threshold.
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
        fields=["key", "ia", "_root_", "ebook_unavailable_at"],
        rows=MARKED_SET_MAX,
    )
    docs = result.docs
    if len(docs) >= MARKED_SET_MAX:
        raise PollRefused(f"Marked set reached the {MARKED_SET_MAX}-edition read cap; cannot tell a complete read from a truncated one")
    refuse_if_incomplete(result, len(docs), "marked-set read")
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
        logger.error("Clear breaker: %d editions would clear but none carry an ocaid; holding every clear this cycle", len(to_clear))
        return []

    availability = await lending.get_availability_async("identifier", identifiers, use_cache=False)

    def is_free(ia_id: str) -> bool:
        answer = availability.get(ia_id)
        # No answer is not an answer: an edition the service skipped keeps its
        # mark, because the clear direction is the unrecoverable one.
        return answer is not None and lending.is_available_for_loan(answer)

    confirmed = [doc for doc in to_clear if any(is_free(ia) for ia in (doc.get("ia") or []))]

    if not confirmed:
        # Every answer disagreed with the index, or the service gave none, so
        # the index is what is wrong. Hold every CLEAR -- and let the marks
        # through: an index that has stopped listing returned books is still
        # listing borrowed ones, and refusing to mark those would publish
        # checked-out books as borrowable for the length of the outage.
        logger.error(
            "Clear breaker: ground truth confirmed 0 of %d editions as available, so the index is wrong "
            "rather than the collection freeing; holding every clear this cycle",
            len(to_clear),
        )
        return []

    logger.warning(
        "Clear breaker: ground truth confirmed %d of %d editions as genuinely available; clearing those and holding the rest.",
        len(confirmed),
        len(to_clear),
    )
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
        return int(datetime.datetime.fromisoformat(raw.replace("Z", "+00:00").replace(" ", "T")).timestamp())
    except ValueError:
        return None


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
    """
    return {
        "key": key,
        "_root_": root,
        "ebook_unavailable": {"set": EBOOK_UNAVAILABLE},
        "ebook_unavailable_at": {"set": at},
    }


def _marked_at(doc: dict) -> int:
    """When this edition was marked, or 0 if the field is missing.

    0 means "clearable", which is deliberate and is the safe default HERE: a
    doc with no stamp predates this daemon or survived a reindex, so the index
    is the better authority on it. Fresh marks always carry a stamp because
    :func:`mark_update` is the only way one is written.
    """
    value = doc.get("ebook_unavailable_at")
    return value if isinstance(value, int) else 0


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
    # it. Old marks are covered by the breaker below, which is a different
    # population and not a backup for this one.
    candidates = [doc for key, doc in marked.items() if key not in should_be_marked]
    to_clear = [doc for doc in candidates if _marked_at(doc) <= index_current_as_of]
    too_fresh = len(candidates) - len(to_clear)

    allowed = max(CLEAR_BREAKER_FLOOR, int(len(marked) * CLEAR_BREAKER_FRACTION))
    if len(to_clear) > allowed:
        # Only the CLEAR set is ever held back. Marking needs no confirmation --
        # it is the recoverable direction -- and dropping the marks alongside a
        # refused clear would publish newly-borrowed books as available for as
        # long as the index stayed degraded: the same failure this guard
        # exists to prevent, reached from the other side.
        to_clear = await confirm_mass_clear(to_clear, allowed, len(marked), len(unavailable_identifiers))

    # Marks the POLL makes are stamped now, not with the index's currency: this
    # book is unavailable as of this read, and the stamp is what protects it
    # from the next poll.
    updates = [mark_update(info["key"], info["root"], int(time.time())) for info in to_mark]
    updates += [{"key": doc["key"], "_root_": doc["_root_"], "ebook_unavailable": {"set": EBOOK_AVAILABLE}} for doc in to_clear]

    # Counts, every cycle, so write volume is observable without a profiler --
    # the disk-growth investigation needs this and a rate is invisible in a
    # per-event log.
    logger.info(
        "Poll: index=%d resolved=%d marked=%d mark=%d clear=%d held_too_fresh=%d",
        len(unavailable_identifiers),
        len(should_be_marked),
        len(marked),
        len(to_mark),
        len(to_clear),
        too_fresh,
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
    except OSError, ValueError, KeyError, RuntimeError:
        # A heartbeat must never be the thing that stops the daemon.
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
    3. The BREAKER plus its ground-truth confirmation stops a degraded index
       mass-clearing OLD marks -- the population layer 2 is silent about,
       because their timestamps are long past the margin.

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
        logger.exception("Could not bootstrap the feed cursor; the marking half starts at 0 and the poll still runs")
        cursor = 0

    await asyncio.gather(
        _feed_loop(cursor, feed_interval, dry_run),
        _poll_loop(poll_interval, es_lag_margin, dry_run),
    )


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
