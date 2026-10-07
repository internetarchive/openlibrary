"""Near-realtime loan availability for Solr.

A standalone daemon -- not a cron, not part of the web app -- backgrounded
inside the solr-updater container by docker/ol-solr-updater-start.sh. Every
POLL_INTERVAL seconds it:

  1. asks ES (archive.org's AdvancedSearch) which books are lendable but currently
     neither borrowable nor browsable (lending.get_checked_out_candidates_async);
  2. resolves those identifiers to Solr EDITION documents and reads back which
     editions Solr currently has unavailable;
  3. writes one batched in-place update: `ebook_unavailable` 1 on the newly
     unavailable, 0 on the returned.

Each poll is a complete statement of what should be unavailable, not an increment,
so the first poll after any start IS the cold start and a reindex that wipes
the field self-heals on the next cycle. There is no cursor, no state file and
nothing to re-run by hand.

Nothing reads the field yet; wiring search to it is a follow-up.

THE ASYMMETRY THAT SHAPES EVERYTHING HERE
-----------------------------------------
Marking a book unavailable when it is not is RECOVERABLE -- it is hidden until
the next poll corrects it. Clearing a book that is actually out is NOT: it is
published as borrowable while someone has it, and nothing revisits it.

So the mark direction is unguarded on purpose and the clear direction refuses,
holds, and asks for a second opinion. In order: the clear-gate
(older_than_es) drops anything ES is too stale to
contradict. Sets are written before unsets, so a partially-landed batch errs
toward hiding.

THERE IS NO GUARD AGAINST A SHORT ES ANSWER, deliberately. If ES returns fewer
identifiers than it should, the books missing from its answer are unset and
show as borrowable for one cycle, then the next poll re-sets them. That is a
30-second error that fixes itself. The guard that used to sit here -- confirming
large unsets per-edition against services/availability -- made the opposite,
permanent mistake: it could not tell a degraded ES from a legitimate reconcile,
so it blocked the reconcile and left Solr holding stale marks indefinitely.
Transient over-clearing beats permanent pollution.

NOTHING HERE CALLS THE AVAILABILITY SERVICE. AdvancedSearch is the only
external source.

THE TRAPS, so they are not re-introduced
----------------------------------------
* Both fields are numeric and docValues-only because `requireInPlace` demands
  it; `pdate` is rejected outright. The schema deploy must carry BOTH, or Solr
  rejects every document, forever, while the container looks healthy.
* `requireInPlace` cannot set a field to null, so "available" is written as 0
  and a clear leaves `ebook_unavailable_ts` behind. The timestamp is meaningful
  only while `ebook_unavailable` is 1.
* Edition updates must carry `_root_`; Solr needs it to target a child
  document rather than create a root-level one.
* A truncated read is a mass-clear by another route -- absent-from-a-short-read
  is indistinguishable from absent-from-Solr -- so reads refuse rather
  than return what arrived. See refuse_if_incomplete.

Design history, the measurements behind these numbers, and the deploy
procedure are in docs/search/index.md; they are not repeated here.
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
count out loud on an interval rather than only when something breaks.
"""


async def resolve_edition_keys(identifiers: list[str]) -> dict[str, dict]:
    """Batch-resolve IA identifiers to Solr edition keys + parent work key via the ia field.

    Returns {identifier: {"key": "/books/OL1M", "root": "/works/OL1W", "ocaid": identifier}}.

    The ocaid is carried in the value as well as the key because callers re-key
    this by edition and would otherwise lose the identifier -- and the
    identifier is what ES's loan-event time is keyed by.

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
        # The SAME guard fetch_solr_unavailable uses, and for the same reason:
        # this is the other half of the comparison that turns absence into a
        # clear. An identifier that fails to RESOLVE is indistinguishable from
        # one ES no longer calls unavailable, so a truncated or
        # timeAllowed-cut read here silently clears checked-out books -- under
        # nothing above INFO in the log.
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
    the operator response differs: a refused read is usually transient Solr
    churn, a refused write is usually this batch being unacceptable to Solr.

    Subclasses RuntimeError deliberately: this narrowed what used to be a bare
    RuntimeError, and anything that caught that -- including the supervising
    loop -- keeps working unchanged. The new type adds a handle for callers
    that want to distinguish, it does not take one away."""


def _batch_summary(request: list[dict]) -> str:
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
    """Write the updates in batches, or raise saying which batch failed.

    Sets before unsets, in sequence rather than concurrently: once a write can
    partially land, stopping halfway must leave books hidden (recoverable)
    rather than published (not).
    """
    if not request:
        return
    batches = list(itertools.batched(request, SOLR_WRITE_BATCH, strict=False))
    for number, batch in enumerate(batches, start=1):
        try:
            await _write_one_batch(list(batch), commit=commit)
        except SolrWriteFailed as exc:
            raise SolrWriteFailed(f"batch {number} of {len(batches)} failed after {number - 1} had already been written -- {exc}") from exc
    logger.info("Solr write OK: %d updates in %d batch(es)", len(request), len(batches))


async def _write_one_batch(request: list[dict], commit: bool = False) -> None:
    """One request, with the two failure shapes logged differently.

    Unreachable is infrastructure and the next poll rebuilds the batch;
    a non-zero status means Solr refused THIS batch -- usually one document the
    main solr_updater rewrote mid-poll, and Solr names none of them, which is
    why the log carries the field list and sample keys.

    `update_in_place_async` returns the body without checking status, and other
    callers rely on that, so the check lives here.
    """
    described = _batch_summary(request)
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
"""Seconds between polls.

Measured: the set moved by 4 books across several minutes, so it changes
per-minute. Sized to that, not to the shortest interval we could sustain.
"""

SOLR_WRITE_BATCH = 100
"""Updates per Solr request.

One request for the whole cycle reliably timed out even at 60s: an in-place
update costs real work per document, and a cold start writes ~860. Fewer
documents per request, not a longer wait for the same one.
"""

SOLR_WRITE_TIMEOUT = 60
"""Seconds to wait for Solr to accept a batch.

Six times the shared default: this contends with the main solr_updater, so the
tail matters more than the median, and a timeout costs the whole batch.
"""

SOLR_UNAVAILABLE_MAX = 50_000
"""Ceiling on the unavailable set read back from Solr.

Not a working limit -- the live unavailable set measured 766 on 2026-10-05 --
but the read must be COMPLETE or the reconcile is wrong in the dangerous
direction: an edition outside a capped window is indistinguishable from one the
ES no longer calls unavailable, and would be unset.
"""


class PollRefused(Exception):
    """This cycle's inputs were not trustworthy, so prior state stands.

    Every untrustworthy-input case resolves the same way -- skip the cycle,
    keep what Solr already has, alarm -- because at poll cadence the
    alternative is a crash loop during routine churn. Raising was right
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
    missing from a truncated Solr read is indistinguishable from one ES no
    longer calls unavailable, so a short read is a mass-clear by another route
    -- a quiet one.
    """
    num_found = getattr(result, "num_found", None)
    if isinstance(num_found, int) and num_found > returned:
        raise PollRefused(f"{what}: Solr matched {num_found} documents but returned {returned}; refusing to treat a truncated read as the set")
    header = getattr(result, "response_header", None) or {}
    if isinstance(header, dict) and header.get("partialResults"):
        raise PollRefused(f"{what}: Solr reported partialResults, so the read timed out mid-query; refusing to treat it as the set")


async def fetch_solr_unavailable() -> dict[str, dict]:
    """Every edition Solr currently has flagged unavailable, or refuse.

    Complete or raises, for the reason in SOLR_UNAVAILABLE_MAX: a truncated read
    makes absent-from-the-window look identical to absent-from-ES, and
    the reconcile clears on absence.
    """
    result = await get_solr().select_async(
        query=f"type:edition AND ebook_unavailable:{EBOOK_UNAVAILABLE}",
        fields=["key", "ia", "_root_", "ebook_unavailable_ts"],
        rows=SOLR_UNAVAILABLE_MAX,
    )
    docs = result.docs
    if len(docs) >= SOLR_UNAVAILABLE_MAX:
        raise PollRefused(f"Solr unavailable set reached the {SOLR_UNAVAILABLE_MAX}-edition read cap; cannot tell a complete read from a truncated one")
    refuse_if_incomplete(result, len(docs), "Solr unavailable-set read")
    return {doc["key"]: doc for doc in docs}


def set_unavailable(key: str, root: str, started: int) -> dict:
    """One atomic update: the flag, and when the loan began.

    Both fields in one write, not two. Separately they can interleave with an
    unset and leave a flag whose timestamp came from a different write -- and
    older_than_es decides from that timestamp.
    """
    return {
        "key": key,
        "_root_": root,
        "ebook_unavailable": {"set": EBOOK_UNAVAILABLE},
        "ebook_unavailable_ts": {"set": started},
    }


def older_than_es(marks: list[dict], newest_es_event: int | None) -> tuple[list[dict], list[dict]]:
    """Split marks into (older than ES, newer than ES).

    A mark newer than ES's own latest event is missing from ES's answer
    because ES has not caught up, not because the book came back. A mark with
    no timestamp counts as older, which is how pre-timestamp cruft is cleaned
    up. With no ES event at all, nothing counts as older.
    """
    if newest_es_event is None:
        if marks:
            logger.warning("ES reported no loan-event times, so none of the %d absent marks can be unset this cycle", len(marks))
        return [], marks

    older: list[dict] = []
    newer: list[dict] = []
    for doc in marks:
        started = doc.get("ebook_unavailable_ts")
        started = started if isinstance(started, int) else 0
        (older if started < newest_es_event else newer).append(doc)
    if newer:
        logger.info("Keeping %d of %d absent marks that are newer than ES (%d) -- ES lag, not returns", len(newer), len(marks), newest_es_event)
    return older, newer


def loan_started_at(ocaid: str, es_unavailable: dict[str, int | None], newest_es_event: int | None) -> int:
    """The loan event, not the clock. No event time -> the batch's latest,
    since over-estimating hides a book for a cycle and under-estimating makes
    a checked-out one eligible to be unset."""
    return es_unavailable.get(ocaid) or newest_es_event or int(time.time())


async def build_poll_updates(es_unavailable: dict[str, int | None]) -> list[dict]:
    """Diff what ES says is unavailable against what Solr has, and write it.

    `es_unavailable` maps each checked-out ocaid to when its loan began. Every
    poll states the whole answer, so the first poll after any start is also the
    cold start and a reindex wipe self-heals on the next one.
    """
    es_identifiers = list(es_unavailable)
    es_editions = {info["key"]: info for info in (await resolve_edition_keys(es_identifiers)).values()}
    solr_unavailable = await fetch_solr_unavailable()

    # How current ES is: the newest loan event anywhere in its answer. Read by
    # older_than_es below, and used as the fallback for books ES gave no event
    # time for.
    dated = [epoch for epoch in es_unavailable.values() if epoch is not None]
    newest_es_event = max(dated) if dated else None

    to_set = [info for key, info in es_editions.items() if key not in solr_unavailable]
    gone_from_es = [doc for key, doc in solr_unavailable.items() if key not in es_editions]
    to_unset, newer_than_es = older_than_es(gone_from_es, newest_es_event)

    if newest_es_event is None and to_set:
        logger.warning(
            "ES returned no loan-event time for any of its %d identifiers; dating this cycle's %d "
            "updates from the daemon clock instead, which says when we looked, not when the loans began",
            len(es_unavailable),
            len(to_set),
        )
    updates = [set_unavailable(info["key"], info["root"], loan_started_at(info["ocaid"], es_unavailable, newest_es_event)) for info in to_set]
    updates += [{"key": doc["key"], "_root_": doc["_root_"], "ebook_unavailable": {"set": EBOOK_AVAILABLE}} for doc in to_unset]

    # Counts, every cycle, so write volume is observable without a profiler --
    # the disk-growth investigation needs this and a rate is invisible in a
    # per-event log.
    logger.info(
        # The same set= / unset= counts repeating across polls is expected, not
        # a stall: writes are not visible to this query until Solr soft-commits
        # (60s in dev), so a change is re-issued a couple of times before the
        # next read reflects it. Harmless; the write is idempotent.
        "Poll: es=%d resolved=%d solr=%d set=%d unset=%d kept_newer_than_es=%d",
        len(es_identifiers),
        len(es_editions),
        len(solr_unavailable),
        len(to_set),
        len(to_unset),
        len(newer_than_es),
    )
    return updates


async def count_solr_unavailable() -> int | None:
    """How many editions carry the mark, without fetching them.

    `rows=0` so Solr returns the count and no documents; the heartbeat wants a
    number, and the set is up to SOLR_UNAVAILABLE_MAX documents to drag back
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
        logger.debug("Heartbeat could not count unavailable editions", exc_info=True)
        return None


async def log_heartbeat() -> None:
    """Proof of life -- no errors looks the same as a stall from outside."""
    logger.info("Heartbeat: solr_unavailable=%s", await count_solr_unavailable())


async def main(
    ol_config: str,
    poll_interval: int = POLL_INTERVAL,
    dry_run: bool = False,
):
    """Mirror ES's unavailable set into Solr, forever.

    Useful environment variables:
    - OL_SOLR_BASE_URL: Override the Solr base URL

    :param ol_config: Path to openlibrary.yml config file.
    :param poll_interval: Seconds between polls.
    :param dry_run: Compute and log updates but do not write to Solr.

    There is no cursor, no state file and no --reset. Each poll is a complete
    statement of what should be unavailable, so the first after any start IS the
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
            es_unavailable = await lending.get_checked_out_candidates_async()
            updates = await build_poll_updates(es_unavailable)
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
            # points an operator at the READ path -- ES, the network,
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
