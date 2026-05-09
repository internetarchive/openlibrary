"""Near-realtime loan availability updater for Solr.

Polls IA's loan changes API (action=changes) and atomically updates two fields
on work documents in Solr:

  ebook_availability      "available" | "unavailable"
  ebook_becomes_available  ISO-8601 UTC timestamp (loan expiry), or null

Design goals
------------
* Simple: a single while-True loop, a state file, no scheduler.
* Self-healing: binary-searches for the ~14-day-old uid on first run (or when
  explicitly reset), so a full Solr re-index or a prolonged outage is handled
  automatically.
* Safe: processes events strictly in uid order; idempotent per-identifier
  because it keeps only the latest event per identifier per batch.

Startup / re-index recovery
----------------------------
On first run (state file absent or uid=0) the script binary-searches for the
uid that corresponds to approximately LOAN_MAX_AGE_DAYS ago.  Loans cannot be
older than that, so processing all events from that uid forward reconstructs
the complete picture of currently-active loans.

After catching up the loop sleeps POLL_INTERVAL seconds then fetches the next
batch.  If a full batch (=BATCH_SIZE) is returned the loop continues without
sleeping, burning through the backlog as fast as possible.

Eviction
--------
Once per cycle the script queries Solr for documents whose
ebook_becomes_available timestamp is already in the past and marks them
available.  This is the safety net for any return/expire events that were
missed.
"""

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

# Event types that indicate an item is actively loaned out
LOAN_ACTIVE_EVENTS = frozenset({"borrow", "browse", "renew_borrow", "renew_browse"})
# Event types that indicate an item has been returned or expired
LOAN_ENDED_EVENTS = frozenset({"return", "expire_borrow", "expire_browse"})

LOAN_MAX_AGE_DAYS = 14
BATCH_SIZE = 1000
POLL_INTERVAL = 30  # seconds between polls when caught up
BINARY_SEARCH_ITERS = 40  # max iterations for startup uid search


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------


def read_state(path: Path) -> int:
    """Return last processed uid, or 0 if the state file is absent/corrupt."""
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return 0


def write_state(path: Path, uid: int) -> None:
    path.write_text(str(uid))


# ---------------------------------------------------------------------------
# Startup recovery: binary-search for the right starting uid
# ---------------------------------------------------------------------------


def find_start_uid(target_age_days: int = LOAN_MAX_AGE_DAYS) -> int:
    """Binary-search for the uid whose next event is ~target_age_days old.

    Uses limit=1 probes to minimise API load.  Returns 0 if the API returns
    no history or if the entire history is within target_age_days.
    """
    # A single probe to learn the current latest_uid.
    resp = lending.get_loan_changes(after_uid=0, limit=1)
    if resp.get("status") != "OK":
        logger.warning("Loan changes API non-OK on startup probe; starting from uid 0")
        return 0

    latest_uid: int = resp.get("latest_uid") or 0
    if not latest_uid:
        return 0

    target_time = datetime.datetime.utcnow() - datetime.timedelta(days=target_age_days)
    low, high = 0, latest_uid

    for _ in range(BINARY_SEARCH_ITERS):
        if high - low <= 1000:
            break
        mid = (low + high) // 2
        probe = lending.get_loan_changes(after_uid=mid, limit=1)
        rows = probe.get("rows", [])
        if not rows:
            # No events above mid — mid is beyond all existing events; go lower.
            high = mid
            continue
        row_time = datetime.datetime.strptime(rows[0]["time"], "%Y-%m-%d %H:%M:%S")
        if row_time < target_time:
            low = mid  # too old, need a more-recent starting uid
        else:
            high = mid  # within window, see if we can start even earlier

    logger.info("find_start_uid: binary search complete, starting from uid %d", low)
    return low


# ---------------------------------------------------------------------------
# Core processing helpers (pure / easily testable)
# ---------------------------------------------------------------------------


def process_changes(rows: list[dict]) -> dict[str, dict]:
    """Reduce a batch of rows to the latest event per identifier.

    Returns {identifier: {"event_type": str, "uid": int, "until": str|None}}
    where "until" is the loan-expiry datetime string from the 'extra' field
    (only set for LOAN_ACTIVE_EVENTS).
    """
    latest: dict[str, dict] = {}
    for row in rows:
        identifier = row["identifier"]
        uid = row["uid"]
        if identifier in latest and latest[identifier]["uid"] >= uid:
            continue
        until = None
        if row["event_type"] in LOAN_ACTIVE_EVENTS:
            try:
                extra = json.loads(row.get("extra") or "{}")
                until = extra.get("until")
            except (json.JSONDecodeError, TypeError):
                pass
        latest[identifier] = {
            "event_type": row["event_type"],
            "uid": uid,
            "until": until,
        }
    return latest


def ia_until_to_solr_date(until: str | None) -> str | None:
    """Convert IA 'until' string ("2026-05-01 15:42:43") to Solr pdate format."""
    if not until:
        return None
    try:
        dt = datetime.datetime.strptime(until, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        logger.debug("Could not parse 'until' value: %r", until)
        return None


def resolve_work_keys(identifiers: list[str]) -> dict[str, str]:
    """Batch-resolve IA identifiers → Solr work keys.

    Queries Solr using the ia field.  Returns {ia_identifier: work_key}.
    Identifiers with no matching work are omitted from the result.
    """
    if not identifiers:
        return {}
    # Solr `ia:(a b c)` is an implicit OR across values
    ia_filter = " ".join(identifiers)
    result_obj = get_solr().select(
        query=f"ia:({ia_filter})",
        fields=["key", "ia"],
        rows=len(identifiers) * 2,
    )
    id_to_work: dict[str, str] = {}
    id_set = set(identifiers)
    for doc in result_obj.docs:
        work_key = doc["key"]
        for ia_id in doc.get("ia", []):
            if ia_id in id_set:
                id_to_work[ia_id] = work_key
    return id_to_work


def build_solr_updates(
    id_state: dict[str, dict],
    id_to_work: dict[str, str],
) -> list[dict]:
    """Produce a list of Solr atomic-update documents from the latest per-identifier state."""
    updates = []
    for identifier, state in id_state.items():
        work_key = id_to_work.get(identifier)
        if not work_key:
            continue
        if state["event_type"] in LOAN_ACTIVE_EVENTS:
            updates.append(
                {
                    "key": work_key,
                    "ebook_availability": {"set": "unavailable"},
                    "ebook_becomes_available": {"set": ia_until_to_solr_date(state["until"])},
                }
            )
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
    """Query Solr for loans whose expiry has passed; return clear-availability docs.

    Safety net for missed return/expire events (e.g. during an outage).
    """
    result_obj = get_solr().select(
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
        for doc in result_obj.docs
    ]


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


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
    :param reset: Ignore existing state file and binary-search for the start uid.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)-15s %(levelname)s %(message)s",
    )
    logger.info("BEGIN loan_availability_updater dry_run=%s reset=%s", dry_run, reset)

    load_config(ol_config)
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
        # ---- Fetch next batch of changes ----
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

        rows: list[dict] = resp.get("rows", [])
        did_updates = False

        # ---- Apply loan events ----
        if rows:
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
                    max(r["uid"] for r in rows),
                )
                if not dry_run:
                    get_solr().update_in_place(updates, commit=False)
                did_updates = True

            new_uid = max(r["uid"] for r in rows)
            last_uid = new_uid
            if not dry_run:
                write_state(state_path, last_uid)

        # ---- Evict expired loans ----
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

        # ---- Commit once per cycle ----
        if did_updates and not dry_run:
            get_solr().update_in_place([], commit=True)

        # ---- Sleep only when fully caught up ----
        if len(rows) >= BATCH_SIZE:
            logger.debug("Full batch received (uid=%d); continuing without sleep", last_uid)
            continue

        logger.debug("Caught up at uid=%d; sleeping %ds", last_uid, poll_interval)
        time.sleep(poll_interval)


if __name__ == "__main__":
    from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

    FnToCLI(main).run()
