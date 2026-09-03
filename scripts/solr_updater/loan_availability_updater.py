"""Near-realtime loan availability updater for Solr.

New to this file? The 30-second version
---------------------------------------
This is a small standalone daemon -- not a cron, not part of the web app. It
runs as a backgrounded process inside the solr-updater container (launched by
docker/ol-solr-updater-start.sh, next to the main solr_updater). Every ~30s it:

  1. Asks IA's loan-changes API what changed since last time
     (lending.get_loan_changes -> GET services/loans/loan/?action=changes).
  2. Looks up the Solr EDITION document for each changed book (by ocaid).
  3. Marks that edition available (1) or unavailable (0) in place, so search
     can reflect borrowing status within ~a minute instead of Open Library
     calling archive.org's availability service on every page load.
  4. Saves a "uid" cursor to a state file so it resumes where it left off; on
     a cold start it rebuilds from the last ~14 days of loan changes.

Nothing reads these Solr fields yet -- wiring search/pages to them is a
follow-up. The rest of this docstring is the Solr-specific "why".

Polls IA's loan changes API and atomically updates ebook_availability and
ebook_becomes_available on EDITION documents (nested children of their work)
so search results reflect borrowing status within one poll interval at the
correct granularity -- a loan on one edition must not mark sibling editions
of the same work unavailable.

ebook_availability is 0/1 and ebook_becomes_available is epoch seconds, both
numeric so writes qualify for Solr's update.partial.requireInPlace: string
and pdate fields are rejected by Solr for in-place updates regardless of
docValues/stored/indexed config, and a *non*-in-place atomic update to a
nested child document reindexes the entire work + all its editions rather
than just the one document, which would defeat the point of a near-realtime
updater. Edition updates therefore always include "_root_" (the parent
work's key) -- Solr requires this to target a child document rather than
create/replace a root-level one.

Solr also rejects "set": null under requireInPlace -- a value can be set or
incremented in-place, but not cleared, even on a field with no prior value.
So a return/expire event never clears ebook_becomes_available; it's left at
its last (now stale) value. ebook_becomes_available is therefore only
meaningful when ebook_availability is EBOOK_UNAVAILABLE -- consumers (and
build_eviction_updates, below) must not read it otherwise.

On first run (or --reset), binary-searches for the uid ~14 days ago so that
all currently-active loans are reflected after a full Solr re-index or outage.
Once per cycle, expired loans are evicted via a Solr range query on
ebook_becomes_available as a safety net for missed return/expire events.

Reindex coordination (known limitation): a full Solr reindex of a work rebuilds
its edition children WITHOUT these loan fields -- the main indexer is unaware of
them -- so every reindex WIPES ebook_availability/loan_uid on the affected
editions. This updater does NOT auto-detect a reindex, and a *plain restart does
not recover*: the state file persists in the solr-updater-data volume, so on
restart it resumes from the surviving last_uid and skips reconstruction entirely.
Recovery requires --reset (or deleting the state file), which rebuilds the last
~14 days from the changes API; a reindexed borrowed book reads as available until
then. Stronger guarantees (indexer-side field preservation, a reindex-triggered
re-apply, or wipe auto-detection) are a maintainer follow-up, out of scope here.
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

LOAN_ACTIVE_EVENTS = frozenset({"borrow", "browse", "renew_borrow", "renew_browse"})
LOAN_ENDED_EVENTS = frozenset({"return", "expire_borrow", "expire_browse"})

EBOOK_UNAVAILABLE = 0
EBOOK_AVAILABLE = 1

LOAN_MAX_AGE_DAYS = 14
BATCH_SIZE = 1000
POLL_INTERVAL = 30  # seconds between polls when caught up


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


def process_changes(rows: list[dict]) -> dict[str, dict]:
    """Reduce a batch of rows to the latest event per identifier.

    Returns {identifier: {"event_type": str, "uid": int, "until": str|None}}
    where "until" is the loan-expiry string from 'extra', set only for active loans.
    """
    latest: dict[str, dict] = {}
    for row in rows:
        # Defensive: a single malformed row (missing identifier/uid/event_type, or a
        # non-int uid) must not crash the whole updater -- skip it and keep going.
        identifier = row.get("identifier")
        uid = row.get("uid")
        event_type = row.get("event_type")
        if not identifier or not isinstance(uid, int) or event_type is None:
            logger.warning("Skipping malformed loan-change row: %r", row)
            continue
        if identifier in latest and latest[identifier]["uid"] >= uid:
            continue
        until = None
        if event_type in LOAN_ACTIVE_EVENTS:
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                until = json.loads(row.get("extra") or "{}").get("until")
        latest[identifier] = {"event_type": event_type, "uid": uid, "until": until}
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

    quoted = " ".join(_phrase(id_) for id_ in identifiers)
    result = get_solr().select(
        query=f"type:edition AND ia:({quoted})",
        fields=["key", "ia", "_root_"],
        rows=len(identifiers) * 2,
    )
    id_set = set(identifiers)
    return {ia_id: {"key": doc["key"], "root": doc["_root_"]} for doc in result.docs for ia_id in doc.get("ia", []) if ia_id in id_set}


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


def build_solr_updates(id_state: dict[str, dict], id_to_edition: dict[str, dict]) -> list[dict]:
    """Build Solr atomic-update documents from the latest per-identifier loan state.

    On a return/expire event, ebook_becomes_available is intentionally left
    untouched rather than cleared: Solr's requireInPlace rejects "set": null
    even for a field that already has no value (verified directly -- it's not
    conditional on prior state). The stale timestamp is harmless because every
    consumer of ebook_becomes_available (including build_eviction_updates
    below) must treat it as meaningful only when ebook_availability is
    EBOOK_UNAVAILABLE.
    """
    updates = []
    for identifier, state in id_state.items():
        edition = id_to_edition.get(identifier)
        if not edition:
            # Edition not in Solr (new item, or its work is mid-reindex): no doc to
            # mark. The event is skipped and last_uid still advances, so this loan is
            # missed until the ocaid's next event or a --reset rebuild. Accepted as v1
            # (no dead-letter/retry) -- an unindexed book has no searchable doc anyway.
            continue
        if state["event_type"] in LOAN_ACTIVE_EVENTS:
            update: dict = {
                "key": edition["key"],
                "_root_": edition["root"],
                "ebook_availability": {"set": EBOOK_UNAVAILABLE},
                "loan_uid": {"set": state["uid"]},
            }
            # Always set an expiry so the eviction safety-net can eventually recover
            # this edition. If 'until' is missing/unparsable we fall back to the max
            # loan lifetime from now -- otherwise the doc would have no
            # ebook_becomes_available, a range query could never match it, and a
            # missed return/expire event would leave it stuck unavailable forever.
            becomes_available = ia_until_to_epoch(state["until"])
            if becomes_available is None:
                becomes_available = int(time.time()) + LOAN_MAX_AGE_DAYS * 86400
            update["ebook_becomes_available"] = {"set": becomes_available}
            updates.append(update)
        elif state["event_type"] in LOAN_ENDED_EVENTS:
            updates.append(
                {
                    "key": edition["key"],
                    "_root_": edition["root"],
                    "ebook_availability": {"set": EBOOK_AVAILABLE},
                    "loan_uid": {"set": state["uid"]},
                }
            )
    return updates


def build_eviction_updates() -> list[dict]:
    """Clear availability for editions whose loan expiry has already passed.

    Safety net for return/expire events missed during an outage. Scoped to
    currently-unavailable editions so a stale ebook_becomes_available left
    over from a prior return/expire (see build_solr_updates) can never match
    an edition that's already available -- it would otherwise be re-matched
    on every cycle forever, since that timestamp can't be cleared in-place.
    """
    now_epoch = int(time.time())
    result = get_solr().select(
        query=f"type:edition AND ebook_availability:{EBOOK_UNAVAILABLE} AND ebook_becomes_available:[* TO {now_epoch}]",
        fields=["key", "_root_"],
        rows=10000,
    )
    return [
        {
            "key": doc["key"],
            "_root_": doc["_root_"],
            "ebook_availability": {"set": EBOOK_AVAILABLE},
        }
        for doc in result.docs
    ]


def main(  # noqa: PLR0915, PLR0912
    ol_config: str,
    state_file: str = "loan-availability-update.state",
    poll_interval: int = POLL_INTERVAL,
    dry_run: bool = False,
    reset: bool = False,
):
    """Poll IA loan changes and update Solr ebook_availability fields.

    Useful environment variables:
    - OL_SOLR_BASE_URL: Override the Solr base URL

    :param ol_config: Path to openlibrary.yml config file.
    :param state_file: Path to state file storing last processed uid (integer).
    :param poll_interval: Seconds to sleep when caught up with the event stream.
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

    if last_uid == 0:
        # --reset forces a rebuild from the changes API; a stale loan_uid still in
        # Solr must not short-circuit that (else reset never goes back ~14 days).
        if not reset:
            last_uid = query_solr_uid()
        if last_uid:
            logger.info("Resuming from Solr loan_uid=%d", last_uid)
        else:
            logger.info("No Solr uid; binary-searching for uid ~%d days ago", LOAN_MAX_AGE_DAYS)
            last_uid = find_start_uid()
        if not dry_run:
            try:
                write_state(state_path, last_uid)
            except OSError:
                logger.exception("Failed to write initial state file %s", state_path)

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

        if rows:
            # Advance the cursor using only rows with a valid int uid, so one malformed
            # row can neither crash here nor stall the cursor (process_changes skips it too).
            valid_uids = [r["uid"] for r in rows if isinstance(r.get("uid"), int)]
            if not valid_uids:
                logger.warning("Batch of %d rows had no valid uid; sleeping", len(rows))
                time.sleep(poll_interval)
                continue
            new_uid = max(valid_uids)
            id_state = process_changes(rows)
            try:
                id_to_edition = resolve_edition_keys(list(id_state.keys()))
            except Exception:
                logger.exception("Failed to resolve edition keys; skipping batch")
                time.sleep(poll_interval)
                continue

            updates = build_solr_updates(id_state, id_to_edition)
            if updates:
                logger.info(
                    "%d Solr updates from %d loan events (uid %d→%d)",
                    len(updates),
                    len(rows),
                    last_uid,
                    new_uid,
                )
                if not dry_run:
                    try:
                        solr_update_in_place(updates, commit=False)
                    except Exception:
                        logger.exception("Solr update failed; state not advanced")
                        time.sleep(poll_interval)
                        continue
                did_updates = True

            last_uid = new_uid

        try:
            evictions = build_eviction_updates()
        except Exception:
            logger.exception("Failed to build eviction updates")
            evictions = []

        if evictions:
            logger.info("Evicting %d expired loans from Solr", len(evictions))
            if not dry_run:
                try:
                    solr_update_in_place(evictions, commit=False)
                except Exception:
                    logger.exception("Solr eviction update failed; evictions skipped this cycle")
                    evictions = []
            did_updates = True

        if did_updates and not dry_run:
            # Deliberate hard commit per cycle: the state file is advanced only after a
            # durable commit, so a crash never leaves state ahead of committed docs.
            # On a shared Solr this is the conservative choice; tuning commit frequency
            # (softCommit / leaning on Solr autoCommit) is a maintainer perf follow-up.
            try:
                solr_update_in_place([], commit=True)
            except Exception:
                logger.exception("Solr commit failed; state not advanced")
                time.sleep(poll_interval)
                continue
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
