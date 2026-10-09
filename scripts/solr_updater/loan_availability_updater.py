"""Near-realtime loan availability for Solr.

A daemon run alongside the solr updater (see docker/ol-solr-updater-start.sh).
Every POLL_INTERVAL seconds it asks archive.org's AdvancedSearch which lendable
books are checked out, and writes the difference against Solr as in-place
updates: `ebook_unavailable` 1 on newly checked-out editions, 0 on returned ones.

Each poll restates the whole set, so there is no cursor or state file: the first
poll is the cold start, and a reindex that wipes the field heals on the next.
It polls the index rather than following the loans feed, which doesn't report
expiry.

Consumers must treat an absent `ebook_unavailable` as available, and read
`ebook_unavailable_ts` only while `ebook_unavailable` is 1: `requireInPlace`
can't null a field, so an unset leaves the timestamp behind. Both fields must be
numeric and docValues-only for `requireInPlace`, and updates must carry `_root_`
to target the nested edition document.

Wrongly marking a book only hides it until the next poll; wrongly unsetting one
publishes a checked-out book as borrowable. So incomplete Solr reads are
refused, sets are written before unsets, and marks newer than ES's latest event
are kept (see older_than_es). A short AdvancedSearch answer is not guarded
against: the books it misses are re-marked on the next poll.
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
"""Identifiers per `ia:(...)` query; one clause each, well under Solr's maxBooleanClauses (30000)."""
HEARTBEAT_INTERVAL = 300
"""Seconds between proof-of-life log lines, since from outside a stall looks like no errors."""


async def resolve_edition_keys(identifiers: list[str]) -> dict[str, dict]:
    """Resolve IA identifiers to their Solr editions.

    Returns {identifier: {"key": "/books/OL1M", "root": "/works/OL1W", "ocaid": identifier}}.
    `root` is the parent work's `_root_`, which in-place updates to a nested
    edition must carry; `ocaid` is repeated for callers that re-key by edition.
    """
    if not identifiers:
        return {}

    # Quoted and escaped so a stray quote or backslash in an ocaid can't break the query.
    def _phrase(id_: str) -> str:
        return '"' + id_.replace("\\", "\\\\").replace('"', '\\"') + '"'

    id_set = set(identifiers)
    resolved: dict[str, dict] = {}
    for chunk in itertools.batched(identifiers, SOLR_QUERY_CHUNK, strict=False):
        quoted = " ".join(_phrase(id_) for id_ in chunk)
        result = await get_solr().select_async(
            query=f"type:edition AND ia:({quoted})",
            fields=["key", "ia", "_root_"],
            rows=len(chunk) * 2,
        )
        # An identifier that fails to resolve looks like one ES no longer reports,
        # so a truncated read here would unset checked-out books. Identifiers
        # with no OL edition don't trip it: num_found counts only matches.
        refuse_if_incomplete(result, len(result.docs), "edition resolve")
        for doc in result.docs:
            for ia_id in doc.get("ia", []):
                if ia_id in id_set:
                    resolved[ia_id] = {"key": doc["key"], "root": doc["_root_"], "ocaid": ia_id}
    return resolved


class SolrWriteFailed(RuntimeError):
    """A Solr write did not land, as opposed to a refused read (PollRefused)."""


def _batch_summary(request: list[dict]) -> str:
    """A one-line description of a batch for logs.

    Solr rejects a whole request without naming the offending document, so this
    includes sample keys to check by hand.
    """
    marks = [d["key"] for d in request if d.get("ebook_unavailable") == {"set": EBOOK_UNAVAILABLE}]
    clears = [d["key"] for d in request if d.get("ebook_unavailable") == {"set": EBOOK_AVAILABLE}]
    fields = sorted({field for d in request for field in d if field not in ("key", "_root_")})
    sample = (marks + clears)[:5]
    return f"{len(request)} docs ({len(marks)} mark, {len(clears)} clear), fields={fields}, first keys={sample}"


async def solr_update_in_place(request: list[dict], commit: bool = False) -> None:
    """Write the updates in batches, or raise saying which batch failed.

    Batches go in order, not concurrently, so a partial write has landed its
    sets before its unsets: books are left hidden rather than wrongly published.
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
    """One update request; raises SolrWriteFailed if Solr is unreachable or refuses it.

    A refusal usually means the main solr_updater rewrote an edition mid-poll.
    `update_in_place_async` doesn't check the response status, so it's checked here.
    """
    described = _batch_summary(request)
    try:
        resp = await get_solr().update_in_place_async(request, commit=commit, _timeout=SOLR_WRITE_TIMEOUT)
    except Exception as exc:
        logger.error("Solr write failed with no response -- %s -- %s: %s", described, type(exc).__name__, exc)
        raise SolrWriteFailed(f"Solr unreachable or the request never completed: {described}") from exc

    header = resp.get("responseHeader") or {}
    if header.get("status") != 0:
        # The rest of the envelope mostly echoes the request.
        error = resp.get("error") or resp
        logger.error("Solr REFUSED the write (status=%s) -- %s -- %s", header.get("status"), described, error)
        raise SolrWriteFailed(f"Solr rejected the in-place update (status={header.get('status')}): {described}")

    logger.debug("Solr batch OK: %s in %sms", described, header.get("QTime", "?"))


POLL_INTERVAL = 30
"""Seconds between polls; the checked-out set changes on the order of minutes."""

SOLR_WRITE_BATCH = 100
"""Updates per Solr request. In-place updates are costly per document, and a
whole cold start (hundreds) in one request times out."""

SOLR_WRITE_TIMEOUT = 60
"""Seconds to wait for Solr to accept a batch; generous because writes compete with the main solr_updater."""

SOLR_UNAVAILABLE_MAX = 50_000
"""Read cap for Solr's unavailable set, far above its real size (hundreds).
Hitting it refuses the poll, since editions past a truncated read would be unset."""


class PollRefused(Exception):
    """This poll's inputs can't be trusted; skip it and keep Solr's current state."""


def refuse_if_incomplete(result, returned: int, what: str) -> None:
    """Raise PollRefused if a Solr read came back short.

    A select can truncate without an error: more matches than `rows`, or
    `timeAllowed` tripping mid-query (`partialResults`). Since an edition missing
    from the read gets unset, a short read would unset books that are out.
    """
    num_found = getattr(result, "num_found", None)
    if isinstance(num_found, int) and num_found > returned:
        raise PollRefused(f"{what}: Solr matched {num_found} documents but returned {returned}; refusing to treat a truncated read as the set")
    header = getattr(result, "response_header", None) or {}
    if isinstance(header, dict) and header.get("partialResults"):
        raise PollRefused(f"{what}: Solr reported partialResults, so the read timed out mid-query; refusing to treat it as the set")


async def fetch_solr_unavailable() -> dict[str, dict]:
    """Every edition Solr has marked unavailable; raises PollRefused rather than return a truncated set."""
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
    """An in-place update marking an edition unavailable since `started`.

    Both fields go in one update so the timestamp older_than_es reads always
    belongs to the current mark.
    """
    return {
        "key": key,
        "_root_": root,
        "ebook_unavailable": {"set": EBOOK_UNAVAILABLE},
        "ebook_unavailable_ts": {"set": started},
    }


def older_than_es(marks: list[dict], newest_es_event: int | None) -> tuple[list[dict], list[dict]]:
    """Split marks absent from ES into (older, newer) than ES's latest event.

    A mark newer than that is absent because ES hasn't caught up, not because
    the book was returned, so it's kept. Marks with no timestamp count as older;
    with no ES event at all, none do.
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
    """When the loan began, per ES. Without one, ES's newest event: erring late
    only keeps a book hidden longer, while erring early could let it be unset."""
    return es_unavailable.get(ocaid) or newest_es_event or int(time.time())


async def build_poll_updates(es_unavailable: dict[str, int | None]) -> list[dict]:
    """The updates that bring Solr in line with `es_unavailable` (checked-out ocaid -> loan start)."""
    es_identifiers = list(es_unavailable)
    es_editions = {info["key"]: info for info in (await resolve_edition_keys(es_identifiers)).values()}
    solr_unavailable = await fetch_solr_unavailable()

    # How current ES is; also the loan start for books ES gave no event time for.
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

    logger.info(
        # The same set/unset counts can repeat for a poll or two: writes aren't
        # visible to the next read until Solr soft-commits, and re-issuing is idempotent.
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
    """How many editions are marked unavailable, counted without fetching them."""
    try:
        result = await get_solr().select_async(query=f"type:edition AND ebook_unavailable:{EBOOK_UNAVAILABLE}", fields=["key"], rows=0)
        return result.num_found
    except Exception:
        # Broad on purpose: a failed count mustn't be reported as a failed poll.
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

    A failed poll is logged and skipped, keeping Solr's current state: raising
    would crash-loop, and the previous poll's marks beat none.
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
                # No hard commit: each opens a new searcher and drops every cache on the
                # Solr serving openlibrary.org. autoSoftCommit/autoCommit cover visibility and durability.
                await solr_update_in_place(updates, commit=False)
            elif updates:
                logger.info("Dry run: %d updates not written", len(updates))

            now = time.monotonic()
            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                await log_heartbeat()
                last_heartbeat = now
        except SolrWriteFailed:
            # Reported apart from a failed poll, which would point at the read path.
            logger.exception("Solr write failed; prior state stands and the next poll rebuilds this batch")
        except lending.CheckedOutSeedIncomplete, PollRefused:
            # Untrustworthy inputs. Keeping prior state at worst hides a book for another poll.
            logger.exception("Poll refused; prior state stands")
        except Exception:
            # Catch-all so no single poll, write included, can kill the daemon.
            logger.exception("Poll failed; prior state stands")

        await asyncio.sleep(poll_interval)


if __name__ == "__main__":
    from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

    FnToCLI(main).run()
