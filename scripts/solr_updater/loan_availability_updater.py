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
rather than by removing the field.

Two fields, and why not three
-----------------------------
`ebook_unavailable` is the answer. `ebook_unavailable_ts` records when the
current run of unavailability began; nothing here reads it, and it ships so the
feed/poll hybrid is a code-only change rather than a second schema deploy. See
:func:`mark_update` for its exact semantics, which are narrower than the name
suggests.

The un-clearable-field constraint above is why a THIRD field was dropped rather
than a reason there can only be one. `ebook_becomes_available` held "available
in N days", which the poll cannot know -- the index exposes no due date (probed
with controls: every plausible date field matches 0 documents, and the one that
exists, `loans__status__last_loan_date`, carries 2020 values on 4% of the
unavailable set) -- and which could not be kept honest anyway, because a
renewal moves the date with no event to observe.

The distinction that lets `ebook_unavailable_ts` survive the same objection: a
stale MARK TIME is inert, because nothing reads it unless the book is marked
and a re-mark overwrites it. A stale EXPIRY time was shown to patrons.

`loan_uid` was the changes-feed cursor, and there is no feed and no cursor.

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

    Returns {identifier: {"key": "/books/OL1M", "root": "/works/OL1W", "ocaid": identifier}}.

    The ocaid is carried in the value as well as the key because callers re-key
    this by edition and would otherwise lose the identifier -- and the
    identifier is what the index's loan-event time is keyed by.

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
        # The SAME guard fetch_marked_editions uses, and for the same reason:
        # this is the other half of the comparison that turns absence into a
        # clear. An identifier that fails to RESOLVE is indistinguishable from
        # one the index no longer calls unavailable, so a truncated or
        # timeAllowed-cut read here silently clears checked-out books -- under
        # the breaker's threshold, with nothing above INFO in the log.
        #
        # It does not fire on the ordinary case of an identifier having no OL
        # edition: `num_found` counts MATCHING documents, so 3 matches out of
        # 500 requested ids is 3 found and 3 returned, which is complete. What
        # it catches is Solr matching more than it handed back.
        refuse_if_incomplete(result, len(result.docs), "edition resolve")
        for doc in result.docs:
            for ia_id in doc.get("ia", []):
                if ia_id in id_set:
                    resolved[ia_id] = {"key": doc["key"], "root": doc["_root_"], "ocaid": ia_id}
    return resolved


class SolrWriteFailed(RuntimeError):
    """The batch did not land. Distinct from a bad READ (PollRefused) because
    the operator response differs: a refused read is usually transient index
    churn, a refused write is usually this batch being unacceptable to Solr.

    Subclasses RuntimeError deliberately: this narrowed what used to be a bare
    RuntimeError, and anything that caught that -- including the supervising
    loop -- keeps working unchanged. The new type adds a handle for callers
    that want to distinguish, it does not take one away."""


def _describe(request: list[dict]) -> str:
    """What a batch contains, in one line, for a log that has to be actionable.

    A `requireInPlace` rejection names no document -- Solr answers 400 for the
    whole request -- so without this the operator gets "update failed" and a
    count. The sample keys are what make it diagnosable: they can be fetched
    from Solr and compared against the schema by hand.
    """
    marks = [d["key"] for d in request if d.get("ebook_unavailable") == {"set": EBOOK_UNAVAILABLE}]
    clears = [d["key"] for d in request if d.get("ebook_unavailable") == {"set": EBOOK_AVAILABLE}]
    fields = sorted({field for d in request for field in d if field not in ("key", "_root_")})
    sample = (marks + clears)[:5]
    return f"{len(request)} docs ({len(marks)} mark, {len(clears)} clear), fields={fields}, first keys={sample}"


async def solr_update_in_place(request: list[dict], commit: bool = False) -> None:
    """Write the updates in batches, or raise with enough detail to act on.

    **Batched because one request for the whole cycle reliably timed out, even
    at a 60s limit.** A cold start marks the entire unavailable set in one go,
    and an atomic in-place update is not free per document: Solr reads, merges
    and re-writes each one. The request size, not the daemon, was the problem.

    MARKS ARE WRITTEN BEFORE CLEARS, and that ordering is the safety property
    once writes can partially land. If the run stops halfway, having marked and
    not yet cleared leaves books hidden -- recoverable, and the next poll
    clears them. The reverse would publish checked-out books as borrowable.
    `build_poll_updates` already emits marks first; this preserves that order
    rather than re-deriving it, and the batches are written in sequence rather
    than concurrently for the same reason.

    A failure raises, but says how many batches had already landed, because
    "nothing was written" and "most of it was written" need different
    responses from whoever reads the log.
    """
    if not request:
        return
    batches = list(itertools.batched(request, SOLR_WRITE_BATCH, strict=False))
    for number, batch in enumerate(batches, start=1):
        try:
            await _write_one_batch(list(batch), commit=commit)
        except SolrWriteFailed as exc:
            raise SolrWriteFailed(f"batch {number} of {len(batches)} failed after {number - 1} had already been written -- {exc}") from exc
    if len(batches) > 1:
        logger.info("Solr write OK: %d updates across %d batches", len(request), len(batches))


async def _write_one_batch(request: list[dict], commit: bool = False) -> None:
    """One request. See solr_update_in_place for why there is more than one.

    update_in_place_async returns the parsed response without checking status
    -- other callers (trending_updater_daily/hourly) rely on that and just log
    it, so the check is done here rather than changing the shared method.

    Both failure shapes are caught and described, because they have different
    causes and a bare traceback distinguishes them poorly:

    * **No response at all** -- Solr unreachable, connection reset, timeout.
      Infrastructure; the batch is untouched and the next poll rebuilds it.
    * **A response carrying a non-zero status** -- Solr understood and refused.
      Under `update.partial.requireInPlace` the usual cause is a document that
      no longer satisfies in-place rules, typically because the main
      solr_updater rewrote that edition between this poll's read and its
      write. The whole batch is rejected over one such document, so the field
      list and sample keys are how the offending one gets found.
    """
    described = _describe(request)
    try:
        resp = await get_solr().update_in_place_async(request, commit=commit, _timeout=SOLR_WRITE_TIMEOUT)
    except Exception as exc:
        logger.error("Solr write failed with no response -- %s -- %s: %s", described, type(exc).__name__, exc)
        raise SolrWriteFailed(f"Solr unreachable or the request never completed: {described}") from exc

    header = resp.get("responseHeader") or {}
    if header.get("status") != 0:
        # Solr puts the useful part under "error"; log that rather than the
        # whole envelope, which is mostly echo of the request.
        error = resp.get("error") or resp
        logger.error("Solr REFUSED the write (status=%s) -- %s -- %s", header.get("status"), described, error)
        raise SolrWriteFailed(f"Solr rejected the in-place update (status={header.get('status')}): {described}")

    logger.debug("Solr batch OK: %s in %sms", described, header.get("QTime", "?"))


POLL_INTERVAL = 30
"""Seconds between polls of the index's unavailable set.

Measured 2026-10-05 against live archive.org: the set moved by 4 books across
several minutes, so it changes per-minute rather than per-second. At two pages
per poll, 10s is ~17,000 requests/day and 30s is ~5,700, for no freshness any
measurement here could distinguish -- so this is sized to the rate the data
actually changes, not to the smallest interval the daemon could sustain.
"""

SOLR_WRITE_BATCH = 100
"""Updates per Solr request.

One request for the whole cycle reliably timed out even at SOLR_WRITE_TIMEOUT,
and a cold start marks the entire unavailable set -- ~860 documents -- at once.
An atomic in-place update costs real work per document (Solr reads, merges and
re-writes each), so the fix is fewer documents per request rather than a longer
wait for the same request.

Small enough that a batch finishes well inside the timeout, large enough that
a cold start is ~9 requests rather than hundreds.
"""

SOLR_WRITE_TIMEOUT = 60
"""Seconds to wait for Solr to accept a batch.

Six times the shared client default, on purpose. This is one bulk in-place
update carrying the whole cycle's marks and clears, and it contends with the
main solr_updater on the same cores -- so the tail is the interesting case
here, not the median. Timing out mid-write costs the entire batch and the next
poll has to rebuild it; waiting is the cheaper failure.

Comfortably inside POLL_INTERVAL * 2, so a slow write cannot stack cycles up
behind it.
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
        fields=["key", "ia", "_root_", "ebook_unavailable_ts"],
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


def mark_update(key: str, root: str, at: int) -> dict:
    """One edition marked unavailable, and when that mark began.

    `ebook_unavailable_ts` is written here and read by nothing in this daemon:
    the poll restates the whole set every cycle, so it needs no history of its
    own marks. It ships because a schema change is a special deploy and a code
    change is not -- carrying the field now makes the feed/poll hybrid that
    follows a CODE-ONLY change rather than a second deploy with its own date.

    **Read the semantics precisely, because the obvious paraphrase is a trap.**
    This is *when the current unbroken run of unavailability began*, not "when
    the mark was last re-asserted". The poll skips editions already in the
    marked set, so a book's ts is frozen for the whole life of its mark and is
    refreshed only when it is cleared and marked again.

    That is the behaviour the hybrid's gate needs, and the paraphrase is the
    thing that breaks it: re-stamping every marked edition each cycle would put
    `ts` at roughly `now` forever, so `ts > index_currency` would always hold,
    no clear would ever proceed, and availability would freeze permanently.
    If you are tempted to "fix" the skip, that is the bug you are adding.

    Two consequences worth knowing before building on it:

    * An edition already marked when this code first deploys never acquires a
      ts -- it is not in `to_mark` -- until it is cleared and re-marked or a
      reindex wipes it. A consumer must treat ABSENT as "unknown", not as a
      low timestamp. Solr omits an unset docValues field from the response
      entirely rather than returning 0, so the value a reader sees is `None`.
    * A book returned and re-borrowed BETWEEN two polls never leaves the marked
      set, so it keeps the earlier loan's ts. In the hybrid the changes feed
      marks that re-borrow and refreshes the stamp -- which is why the feed's
      mark path must NOT inherit this skip.

    The timestamp is the daemon host's wall clock. It will be compared against
    a currency derived from archive.org's index, so the two are the same UNIT
    but not the same CLOCK; a consumer should reserve a skew allowance rather
    than assume they agree to the second.
    """
    return {
        "key": key,
        "_root_": root,
        "ebook_unavailable": {"set": EBOOK_UNAVAILABLE},
        "ebook_unavailable_ts": {"set": at},
    }


def gate_clears_on_index_currency(absent: list[dict], newest: int | None) -> tuple[list[dict], list[dict]]:
    """Absence from the index means "returned" only for marks OLDER than the index.

    The index's snapshot is current only up to its newest loan event. A mark
    newer than that is absent from the result set because the index has not
    caught up, NOT because the book came back -- so clearing it publishes a
    checked-out book as borrowable, and nothing revisits it.

    So `newest` is the horizon: a marked edition absent from the result set may
    be cleared only if its stamp is STRICTLY older. Returns (clearable, held).

    Three edges, each decided rather than inherited:

    * **Strict `<`.** A mark exactly at the horizon is held. The index is
      current *up to and including* that instant, so a mark at the same second
      is precisely the ambiguous case, and ambiguity resolves toward holding.
    * **No horizon at all** -- an empty result set, or one where no record
      carries an event time. Nothing can be judged against nothing, so NOTHING
      is cleared this cycle. This is also what makes a collapsed index safe:
      the set going empty reads as "no information", never as "everything was
      returned".
    * **A mark with no stamp of its own** is treated as very old, so it
      clears. Reachable only for a mark written between the schema deploy and
      this code shipping -- a reindex that wipes the stamp wipes
      `ebook_unavailable` with it, so such a document leaves the marked set
      entirely rather than lingering without a stamp. Those marks really are
      from before the field existed, and holding them forever would be the
      worse failure.

    On this branch the gate is near-inert: every clear candidate was marked by
    an earlier poll and is older than the current horizon. It earns its place
    because the feed-plus-poll design that follows marks books the index has
    not seen yet, which is exactly the case this refuses to clear.

    THE SEAM for that follower: `newest` is an optimistic horizon, since index
    shards lag non-uniformly. The follower subtracts a safety margin here
    rather than restructuring the gate.
    """
    if newest is None:
        if absent:
            logger.warning(
                "Index gave no loan-event time to judge against, so none of the %d absent marks can be "
                "cleared this cycle; absence is being read as no information rather than as returned",
                len(absent),
            )
        return [], absent

    clearable: list[dict] = []
    held: list[dict] = []
    for doc in absent:
        stamp = doc.get("ebook_unavailable_ts")
        stamp = stamp if isinstance(stamp, int) else 0
        (clearable if stamp < newest else held).append(doc)
    if held:
        logger.info(
            "Gate: holding %d of %d absent marks newer than the index's currency (%d); they are lag, not returns",
            len(held),
            len(absent),
            newest,
        )
    return clearable, held


def stamp_for(ocaid: str, unavailable: dict[str, int | None], newest: int | None) -> int:
    """When to say this book's unavailability began.

    THE LOAN EVENT, not the daemon's clock. `ebook_unavailable_ts` answers
    "when did this book become unavailable", and the daemon noticing is a
    different fact -- minutes later in a steady state, arbitrarily later after
    a restart. Stamping the read time makes every mark look as fresh as the
    poll that saw it, which is backwards for a field whose whole job is to
    tell a recent mark from an old one.

    The index does not know for about a third of the set
    (CHECKED_OUT_INDEX_EVENT_FIELDS), and those fall back to `newest` -- the
    latest loan event anywhere in this poll's result set. Deliberately the
    LATEST in range rather than the earliest:

    * It is the conservative end. An over-estimate hides a book briefly and
      corrects itself; an under-estimate makes a checked-out book clearable,
      and nothing revisits it.
    * It corrects quickly. Measured 2026-10-07, the newest event in the live
      unavailable set was 90 seconds old with twelve in the preceding seven
      minutes, so this horizon advances every half-minute or so.
    * It stays inside the batch's own range, so it can never claim a book was
      borrowed later than anything the index actually reports.

    When the index gives no event time ANYWHERE in the set, `newest` is None
    and there is nothing better than the clock. The caller logs that.
    """
    return unavailable.get(ocaid) or newest or int(time.time())


async def build_poll_updates(unavailable: dict[str, int | None]) -> list[dict]:
    """Reconcile Solr's marked set to the index's unavailable set, in one pass.

    This is the whole daemon. `unavailable` is what the index says is checked
    out right now, mapped to when each loan began; everything Solr has marked
    that is not in it has been returned or expired. One bulk in-place update
    carries both directions.

    It replaces a cold start, a follower, a repairer, a cursor and an overlap
    replay, because every one of those existed to approximate a snapshot the
    index already publishes. A first poll is a cold start. A reindex wipe
    self-heals on the next poll, with nothing to re-run by hand.
    """
    unavailable_identifiers = list(unavailable)
    resolved = await resolve_edition_keys(unavailable_identifiers)
    should_be_marked = {info["key"]: info for info in resolved.values()}
    marked = await fetch_marked_editions()

    # THE INDEX'S CURRENCY. The newest loan event it reported anywhere in this
    # result set, and therefore the instant up to which its snapshot can be
    # trusted. Two things read it: the gate below, and the fallback stamp for
    # books the index gave no event time for. Computed once, here, because the
    # gate needs it before any clear is decided.
    dated = [epoch for epoch in unavailable.values() if epoch is not None]
    newest = max(dated) if dated else None

    to_mark = [info for key, info in should_be_marked.items() if key not in marked]
    absent = [doc for key, doc in marked.items() if key not in should_be_marked]
    # LAYER 1 of two on the clear path, and it runs FIRST so the breaker below
    # sizes itself against the gated set rather than the raw one.
    to_clear, held = gate_clears_on_index_currency(absent, newest)

    allowed = max(CLEAR_BREAKER_FLOOR, int(len(marked) * CLEAR_BREAKER_FRACTION))
    if len(to_clear) > allowed:
        # Only the CLEAR set is ever held back. Marking needs no confirmation --
        # it is the recoverable direction -- and dropping the marks alongside a
        # refused clear would publish newly-borrowed books as available for as
        # long as the index stayed degraded: the same failure this guard
        # exists to prevent, reached from the other side.
        to_clear = await confirm_mass_clear(to_clear, allowed, len(marked), len(unavailable_identifiers))

    if newest is None and to_mark:
        logger.warning(
            "Checked-out index returned no loan-event time for any of its %d identifiers; "
            "stamping this cycle's %d marks with the daemon clock instead, which dates them to "
            "when the daemon looked rather than when the loans began",
            len(unavailable),
            len(to_mark),
        )
    updates = [mark_update(info["key"], info["root"], stamp_for(info["ocaid"], unavailable, newest)) for info in to_mark]
    updates += [{"key": doc["key"], "_root_": doc["_root_"], "ebook_unavailable": {"set": EBOOK_AVAILABLE}} for doc in to_clear]

    # Counts, every cycle, so write volume is observable without a profiler --
    # the disk-growth investigation needs this and a rate is invisible in a
    # per-event log.
    logger.info(
        "Poll: index=%d resolved=%d marked=%d mark=%d clear=%d held_newer_than_index=%d",
        len(unavailable_identifiers),
        len(should_be_marked),
        len(marked),
        len(to_mark),
        len(to_clear),
        len(held),
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
            if updates and not dry_run:
                # Never a hard commit. One opens a new searcher and invalidates
                # every Solr cache on the instance serving openlibrary.org, and
                # at this cadence that is thousands a day. autoSoftCommit makes
                # the write visible within a second and autoCommit persists it;
                # neither needs asking. The small write set is not the reason --
                # commit cost tracks searcher churn, not document count.
                await solr_update_in_place(updates, commit=False)
            elif updates:
                logger.info("Dry run: %d updates not written", len(updates))

            now = time.monotonic()
            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                await log_heartbeat()
                last_heartbeat = now
        except SolrWriteFailed:
            # Already logged with the batch's shape and Solr's own words. This
            # exists so a write failure is not reported as "poll failed", which
            # points an operator at the READ path -- the index, the network,
            # the query -- when the read in fact succeeded and the daemon has
            # an answer it simply could not store.
            logger.exception("Solr write failed; prior state stands and the next poll rebuilds this batch")
        except lending.CheckedOutSeedIncomplete, PollRefused:
            # Both mean "this cycle's inputs are not trustworthy". Prior state
            # stands, which is the safe direction: an over-held book is hidden
            # for one cycle, an under-held one is published as borrowable while
            # it is out and nothing revisits it.
            logger.exception("Poll refused; prior state stands")
        except Exception:
            # EVERYTHING the cycle does is inside this try, the Solr write
            # included. A Solr error used to escape and kill the process: the
            # main solr_updater can rewrite an edition between this poll's read
            # and its write, which makes the in-place update 400 under
            # `requireInPlace` -- and at OL's merge rate that is a recurring
            # 60-second outage, not a one-off, with the whole batch's other
            # marks and clears discarded alongside it.
            logger.exception("Poll failed; prior state stands")

        await asyncio.sleep(poll_interval)


if __name__ == "__main__":
    from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

    FnToCLI(main).run()
