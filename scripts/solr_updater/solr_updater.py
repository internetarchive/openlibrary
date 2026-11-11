"""New script to handle solr updates.

Author: Anand Chitipothu

Changes:
2013-02-25: First version
2018-02-11: Use newer config method
"""

import asyncio
import datetime as dt
import itertools
import json
import logging
import re
import socket
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Literal, TypedDict, cast

import aiofiles
import requests

import infogami
from infogami import config
from openlibrary.config import load_config
from openlibrary.solr import update
from openlibrary.utils.open_syllabus_project import set_osp_dump_location
from openlibrary.utils.sentry import init_sentry
from openlibrary.utils.shutdown import setup_graceful_shutdown
from scripts.solr_updater.transaction_log import (
    ForceUpdates,
    TransactionLog,
    TransactionsOffset,
    find_force_update_seq_at,
    find_keys,
    find_transaction_id_at,
    get_transaction_created_at,
)

logger = logging.getLogger("openlibrary.solr-updater")
# FIXME: Some kind of hack introduced to work around DB connectivity issue
args: dict = {}
setup_graceful_shutdown()


def read_state_file(path, initial_state: str | None = None):
    try:
        return open(path).read()
    except OSError:
        logger.error("State file %s is not found. Reading log from the beginning of today", path)
        return initial_state or f"{dt.date.today().isoformat()}:0"


def get_default_offset():
    return dt.date.today().isoformat() + ":0"


class InfobaseLogRecord(TypedDict):
    action: str
    timestamp: str
    data: dict
    site: str


class InfobaseLogResponse(TypedDict):
    data: list[InfobaseLogRecord]
    offset: str
    """E.g. '2023-02-11:0'"""


class InfobaseLog:
    def __init__(self, hostname: str, exclude: str | None = None):
        """
        :param str hostname:
        :param str|None exclude: if specified, excludes records that include the string
        """
        self.base_url = "http://%s/openlibrary.org/log" % hostname
        self.offset = get_default_offset()
        self.exclude = exclude

    def tell(self):
        return self.offset

    def seek(self, offset):
        self.offset = offset.strip()

    def read_records(self, max_fetches=10):
        """Reads all the available log records from the server."""
        for i in range(max_fetches):
            url = f"{self.base_url}/{self.offset}?limit=100"
            logger.debug("Reading log from %s", url)
            try:
                resp = requests.get(url)
                resp.raise_for_status()
            except requests.exceptions.HTTPError as e:
                logger.error("Failed to open URL %s", url, exc_info=True)
                if e.args and e.args[0].args == (111, "Connection refused"):
                    logger.error(
                        "make sure infogami server is working, connection refused from %s",
                        url,
                    )
                    sys.exit(1)
                raise

            try:
                d: InfobaseLogResponse = resp.json()
            except:
                logger.error("Bad JSON: %s", resp.text)
                raise
            data = d["data"]
            # no more data is available
            if not data:
                logger.debug("no more records found")
                # There's an infobase bug where we'll sometimes get 0 items, but the
                # binary offset will have incremented...?
                if "offset" in d:
                    # There's _another_ infobase bug where if you query a future date,
                    # it'll return back 2020-12-01. To avoid solrupdater getting stuck
                    # in a loop, only update the offset if it's newer than the current
                    old_day, old_boffset = self.offset.split(":")
                    old_boffset = int(old_boffset)
                    new_day, new_boffset = d["offset"].split(":")
                    new_boffset = int(new_boffset)
                    if new_day >= old_day and new_boffset >= old_boffset:
                        self.offset = d["offset"]
                return

            for record in data:
                if self.exclude and self.exclude in json.dumps(record):
                    continue
                yield record

            self.offset = d["offset"]


def parse_log(records: Iterable[InfobaseLogRecord]):
    for rec in records:
        action = rec.get("action")

        if action in ("save", "save_many"):
            changeset = rec["data"].get("changeset", {})
            old_docs = changeset.get("old_docs", [])
            new_docs = changeset.get("docs", [])
            for before, after in zip(old_docs, new_docs):
                yield cast(str, after["key"])
                # before is None if the item is new
                if before:
                    before_keys = set(find_keys(before))
                    after_keys = set(find_keys(after))
                    # If a key was changed or was removed, the previous keys
                    # also need to be updated
                    yield from before_keys - after_keys

        elif action == "store.put":
            # Record shape: {"action": "store.put", "data": {"key": <key>, "data": <store doc>}, ...}
            data = rec.get("data", {}).get("data", {})
            key = data.get("_key", "")
            # Hack to force updating something from admin interface
            # The admin interface writes the keys to update to a document named
            # 'solr-force-update' in the store and whatever keys are written to that
            # are picked by this script
            if key == "solr-force-update":
                keys = cast(list[str], data.get("keys", []))
                yield from keys


async def update_keys(keys: Iterable[str]):
    # FIXME: Some kind of hack introduced to work around DB connectivity issue
    logger.debug("Args: %s" % str(args))
    update.load_configs(args["ol_url"], args["ol_config"], "default")

    keys = [k for k in keys if update.can_update_key(k)]
    if not keys:
        return 0

    count = 0
    for chunk in itertools.batched(keys, 100, strict=False):
        count += len(chunk)
        await update.update_keys(list(chunk), commit=False)

        # Caches should not persist between different calls to update_keys!
        update.data_provider.clear_cache()

    if count:
        logger.info("updated %d documents", count)

    return count


async def main(
    ol_config: str,
    osp_dump: Path | None = None,
    debugger: bool = False,
    state_file: str = "solr-update.state",
    exclude_edits_containing: str | None = None,
    ol_url="http://openlibrary.org/",  # Has side effects, is read globally
    socket_timeout: int = 10,
    initial_state: str | None = None,
    source: Literal["database", "infobase"] = "infobase",
):
    """
    Useful environment variables:
    - OL_SOLR_BASE_URL: Override the Solr base URL
    - OL_SOLR_NEXT: Set to true if running with next version of Solr/schema

    :param debugger: Wait for a debugger to attach before beginning
    :param exclude_edits_containing: Don't index matching edits (Infobase source only)
    :param solr_url: If wanting to override what's in the config file
    :param initial_state: Where to start if there's no saved state: an Infobase offset (``2026-11-03:1234``),
        or with ``--source database`` also a UTC date or datetime. Defaults to the beginning of today.
    :param source: Where edits are read from: the Infobase HTTP write log (default) or the ``transaction``
        table (``database``). Each keeps its own offset file; switching either way replays from the beginning
        of the day the other one had reached.
    """
    FORMAT = "%(asctime)-15s %(levelname)s %(message)s"
    logging.basicConfig(level=logging.INFO, format=FORMAT)
    logger.info("BEGIN solr_updater")

    if source == "database" and exclude_edits_containing:
        raise ValueError("--exclude-edits-containing is supported only with --source infobase")

    if debugger:
        import debugpy  # noqa: T100

        logger.info("Enabling debugger attachment (attach if it hangs here)")
        debugpy.listen(address=("0.0.0.0", 3000))  # noqa: T100
        logger.info("Waiting for debugger to attach...")
        debugpy.wait_for_client()  # noqa: T100
        logger.info("Debugger attached to port 3000")

    # Sometimes archive.org requests blocks forever.
    # Setting a timeout will make the request fail instead of waiting forever.
    socket.setdefaulttimeout(socket_timeout)

    set_osp_dump_location(osp_dump)

    logger.info("loading config from %s", ol_config)
    load_config(ol_config)
    init_sentry(getattr(infogami.config, "sentry", {}))

    if source == "database":
        await run_from_transactions(state_file, initial_state)
    else:
        await run_from_infobase_log(state_file, initial_state, exclude_edits_containing)


async def write_state(path: str | Path, value: str) -> None:
    async with aiofiles.open(path, "w") as f:
        await f.write(value)


def get_transactions_offset_file(log_offset_file: Path) -> Path:
    """Get the transactions source's offset file, kept next to the Infobase log's, e.g. ``solr-update.transactions-offset.json``."""
    return log_offset_file.with_name(f"{log_offset_file.stem}.transactions-offset.json")


def read_transactions_offset(path: Path) -> TransactionsOffset:
    return TransactionsOffset.model_validate_json(path.read_text())


async def save_transactions_offset(path: Path, offset: TransactionsOffset) -> None:
    await write_state(path, offset.model_dump_json())


def was_written_after(path: Path, other: Path) -> bool:
    """Check whether ``path`` exists and was written after ``other`` (or ``other`` doesn't exist)."""
    return path.exists() and (not other.exists() or path.stat().st_mtime > other.stat().st_mtime)


def parse_initial_state(initial_state: str) -> dt.datetime:
    """Parse a point in time (UTC) from ``2026-11-03``, ``2026-11-03T10:00``, or an Infobase log offset ``2026-11-03:1234``."""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}:\d+", initial_state):
        initial_state = initial_state.split(":", maxsplit=1)[0]
    return dt.datetime.fromisoformat(initial_state)


def find_transactions_start(transactions_offset_file: Path, log_offset_file: Path, initial_state: str | None) -> TransactionsOffset | dt.datetime:
    """Find where the transactions source starts: a saved offset, or a point in time (UTC) to look one up.

    In order: its own saved offset, unless the Infobase log source ran after it;
    the beginning of the day the Infobase log source had reached (switching over);
    ``initial_state``; or the beginning of today.
    """
    if transactions_offset_file.exists() and not was_written_after(log_offset_file, transactions_offset_file):
        return read_transactions_offset(transactions_offset_file)
    if log_offset_file.exists():
        logger.info("Switching from the Infobase log; replaying from the beginning of its offset's day")
        return parse_initial_state(log_offset_file.read_text().strip())
    if initial_state:
        return parse_initial_state(initial_state)
    logger.error("State file %s is not found. Reading transactions from the beginning of today", transactions_offset_file)
    return dt.datetime.combine(dt.datetime.now(dt.UTC).date(), dt.time())


async def run_from_transactions(state_file: str, initial_state: str | None) -> None:
    """Index keys from the ``transaction`` table, forever, saving the offset next to the Infobase log's."""
    log_offset_file = Path(state_file)
    transactions_offset_file = get_transactions_offset_file(log_offset_file)
    start = find_transactions_start(transactions_offset_file, log_offset_file, initial_state)
    if isinstance(start, dt.datetime):
        start = TransactionsOffset(transaction=await find_transaction_id_at(start), force_update=await find_force_update_seq_at(start))
    logger.info("Reading transactions after id %s and admin force-updates after %s", start.transaction, start.force_update)

    log = TransactionLog(start.transaction)
    force_updates = ForceUpdates(start.force_update)
    while True:
        forced = await force_updates.read()
        keys, count = await log.read()
        await update_keys([*forced, *keys])
        await save_transactions_offset(transactions_offset_file, TransactionsOffset(transaction=log.offset, force_update=force_updates.last_seq))

        if count:
            lag = dt.datetime.now(dt.UTC).replace(tzinfo=None) - log.last_created_at if log.last_created_at else None
            logger.info("Indexed %d transactions, %s behind; offset %s, waiting on %s", count, lag, log.offset, sorted(log.missing_ids))
        # Keep going while there's a backlog; otherwise wait for more edits.
        if count < log.batch_size and not forced:
            await asyncio.sleep(5)


async def run_from_infobase_log(
    state_file: str,
    initial_state: str | None,
    exclude_edits_containing: str | None,
) -> None:
    """Index keys from the Infobase HTTP write log, forever."""
    log_offset_file = Path(state_file)
    transactions_offset_file = get_transactions_offset_file(log_offset_file)
    if was_written_after(transactions_offset_file, log_offset_file):
        # Switching back from the transactions source. The log can only be addressed by
        # day, so start from the beginning of the day that source had reached.
        created_at = await get_transaction_created_at(read_transactions_offset(transactions_offset_file).transaction)
        day = (created_at or dt.datetime.now(dt.UTC)).date().isoformat()
        logger.info("Switching from the transactions source; replaying the Infobase log from %s", day)
        offset = f"{day}:0"
        await write_state(log_offset_file, offset)
    else:
        offset = read_state_file(state_file, initial_state)

    logger.info("Reading the Infobase HTTP log from %s", offset)
    logfile = InfobaseLog(config.get("infobase_server"), exclude=exclude_edits_containing)
    logfile.seek(offset)

    while True:
        records = logfile.read_records()
        keys = parse_log(records)
        count = await update_keys(keys)

        if logfile.tell() != offset:
            offset = logfile.tell()
            logger.info("saving offset %s", offset)
            await write_state(log_offset_file, offset)

        # Don't sleep after committing some records. While the commit was on,
        # some more edits might have happened.
        if count == 0:
            logger.debug("No more log records available, sleeping...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

    cli = FnToCLI(main)
    args = cli.args_dict()
    cli.run()
