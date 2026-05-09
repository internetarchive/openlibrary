"""Near-realtime loan availability updater for Solr.

Polls IA's loan changes API and atomically updates ebook_availability and
ebook_becomes_available on work documents so search results reflect borrowing
status within one poll interval.

On first run (or --reset), binary-searches for the uid ~14 days ago so that
all currently-active loans are reflected after a full Solr re-index or outage.
Once per cycle, expired loans are evicted via a Solr range query on
ebook_becomes_available as a safety net for missed return/expire events.
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

LOAN_MAX_AGE_DAYS = 14
BATCH_SIZE = 1000
POLL_INTERVAL = 30  # seconds between polls when caught up


def read_state(path: Path) -> int:
    """Return last processed uid, or 0 if the state file is absent/corrupt."""
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
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

    target_time = datetime.datetime.utcnow() - datetime.timedelta(days=target_age_days)
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
        row_time = datetime.datetime.strptime(rows[0]["time"], "%Y-%m-%d %H:%M:%S")
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
        identifier = row["identifier"]
        uid = row["uid"]
        if identifier in latest and latest[identifier]["uid"] >= uid:
            continue
        until = None
        if row["event_type"] in LOAN_ACTIVE_EVENTS:
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                until = json.loads(row.get("extra") or "{}").get("until")
        latest[identifier] = {"event_type": row["event_type"], "uid": uid, "until": until}
    return latest


def ia_until_to_solr_date(until: str | None) -> str | None:
    """Convert IA 'until' string ("2026-05-01 15:42:43") to Solr pdate format."""
    if not until:
        return None
    try:
        return datetime.datetime.strptime(until, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        logger.debug("Could not parse 'until' value: %r", until)
        return None


def resolve_work_keys(identifiers: list[str]) -> dict[str, str]:
    """Batch-resolve IA identifiers to Solr work keys via the ia field."""
    if not identifiers:
        return {}
    # Quote each term so identifiers with special characters are treated literally
    quoted = " ".join(f'"{id_}"' for id_ in identifiers)
    result = get_solr().select(
        query=f"ia:({quoted})",
        fields=["key", "ia"],
        rows=len(identifiers) * 2,
    )
    id_set = set(identifiers)
    return {ia_id: doc["key"] for doc in result.docs for ia_id in doc.get("ia", []) if ia_id in id_set}


def build_solr_updates(id_state: dict[str, dict], id_to_work: dict[str, str]) -> list[dict]:
    """Build Solr atomic-update documents from the latest per-identifier loan state."""
    updates = []
    for identifier, state in id_state.items():
        work_key = id_to_work.get(identifier)
        if not work_key:
            continue
        if state["event_type"] in LOAN_ACTIVE_EVENTS:
            update: dict = {"key": work_key, "ebook_availability": {"set": "unavailable"}}
            solr_until = ia_until_to_solr_date(state["until"])
            if solr_until is not None:
                update["ebook_becomes_available"] = {"set": solr_until}
            updates.append(update)
        elif state["event_type"] in LOAN_ENDED_EVENTS:
            updates.append(
                {
                    "key": work_key,
                    "ebook_availability": {"set": "available"},
                    "ebook_becomes_available": {"set": None},
                }
            )
    return updates


def build_eviction_updates() -> list[dict]:
    """Clear availability for works whose loan expiry has already passed.

    Safety net for return/expire events missed during an outage.
    """
    result = get_solr().select(
        query="ebook_becomes_available:[* TO NOW]",
        fields=["key"],
        rows=10000,
    )
    return [
        {
            "key": doc["key"],
            "ebook_availability": {"set": "available"},
            "ebook_becomes_available": {"set": None},
        }
        for doc in result.docs
    ]


def main(
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
        logger.info("No prior state; binary-searching for uid ~%d days ago", LOAN_MAX_AGE_DAYS)
        last_uid = find_start_uid()
        if not dry_run:
            write_state(state_path, last_uid)
        logger.info("Starting from uid %d", last_uid)

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
            new_uid = max(r["uid"] for r in rows)
            id_state = process_changes(rows)
            try:
                id_to_work = resolve_work_keys(list(id_state.keys()))
            except Exception:
                logger.exception("Failed to resolve work keys; skipping batch")
                time.sleep(poll_interval)
                continue

            updates = build_solr_updates(id_state, id_to_work)
            if updates:
                logger.info(
                    "%d Solr updates from %d loan events (uid %d→%d)",
                    len(updates),
                    len(rows),
                    last_uid,
                    new_uid,
                )
                if not dry_run:
                    get_solr().update_in_place(updates, commit=False)
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
                get_solr().update_in_place(evictions, commit=False)
            did_updates = True

        if did_updates and not dry_run:
            try:
                get_solr().update_in_place([], commit=True)
            except Exception:
                logger.exception("Solr commit failed; state not advanced")
                time.sleep(poll_interval)
                continue
        if not dry_run:
            write_state(state_path, last_uid)

        if len(rows) >= BATCH_SIZE:
            continue

        logger.debug("Caught up at uid=%d; sleeping %ds", last_uid, poll_interval)
        time.sleep(poll_interval)


if __name__ == "__main__":
    from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

    FnToCLI(main).run()
