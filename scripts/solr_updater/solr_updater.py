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
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
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
from scripts.solr_updater.transaction_log import ForceUpdates, TransactionLog, force_update_seq_at, position_status, transaction_id_at

logger = logging.getLogger("openlibrary.solr-updater")
# How far before the first unprocessed Infobase log edit the transaction source starts when switching over.
SWITCH_OVERLAP = dt.timedelta(minutes=1)
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


def find_keys(d: dict | list) -> Iterator[str]:
    """
    Find any keys in the given dict or list.

    >>> list(find_keys({'key': 'foo'}))
    ['foo']
    >>> list(find_keys([{}, {'key': 'bar'}]))
    ['bar']
    >>> list(find_keys([{'key': 'blue'}, {'key': 'bar'}]))
    ['blue', 'bar']
    >>> list(find_keys({'title': 'foo'}))
    []
    >>> list(find_keys({ 'works': [ {'key': 'foo'} ] }))
    ['foo']
    >>> list(find_keys({ 'authors': [ { 'author': {'key': 'foo'} } ] }))
    ['foo']
    """
    if isinstance(d, dict):
        if "key" in d:
            yield d["key"]
        for val in d.values():
            yield from find_keys(val)
    elif isinstance(d, list):
        for val in d:
            yield from find_keys(val)
    else:
        # All other types are not recursed
        return


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
        table (``database``). Each keeps its own position; switching either way picks up where the other stopped.
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


def is_newer(path: Path, other: Path) -> bool:
    """Whether ``path`` exists and was written after ``other`` (or ``other`` doesn't exist)."""
    return path.exists() and (not other.exists() or path.stat().st_mtime > other.stat().st_mtime)


def parse_initial_state(initial_state: str) -> dt.datetime:
    """A point in time (UTC) from ``2026-11-03``, ``2026-11-03T10:00``, or an Infobase offset ``2026-11-03:1234``."""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}:\d+", initial_state):
        initial_state = initial_state.split(":", maxsplit=1)[0]
    return dt.datetime.fromisoformat(initial_state)


def infobase_offset_time(offset: str) -> dt.datetime | None:
    """When the first edit after an Infobase log offset was made, or None if the log has nothing after it."""
    try:
        resp = requests.get(f"http://{config.get('infobase_server')}/openlibrary.org/log/{offset}?limit=1", timeout=30)
        resp.raise_for_status()
    except requests.RequestException:
        logger.warning("Infobase log unavailable at offset %s", offset, exc_info=True)
        return None
    if records := resp.json()["data"]:
        return dt.datetime.fromisoformat(records[0]["timestamp"])
    return None


@dataclass
class Position:
    """Where the transaction source has got to, saved as JSON in ``<state-file>.txid``."""

    transaction: int
    force_update: int

    def dumps(self) -> str:
        return json.dumps(asdict(self))


def transaction_start(position_file: Path, offset_file: Path, initial_state: str | None) -> Position | dt.datetime:
    """Where the transaction source starts: its saved position, or a point in time (UTC).

    1. Its own position file, unless the Infobase source ran after it.
    2. The Infobase source's offset (switching over): one minute before the first edit it hasn't
       processed, or before it last saved its offset, whichever is earlier.
    3. ``initial_state``: a date, a datetime (UTC) or an Infobase offset.
    4. The beginning of today (UTC), like the Infobase source.
    """
    if position_file.exists() and not is_newer(offset_file, position_file):
        return Position(**json.loads(position_file.read_text()))
    if offset_file.exists():
        offset = offset_file.read_text().strip()
        # The offset file is rewritten whenever the Infobase source makes progress, so
        # its mtime is a safe bound even when the log has nothing after the offset.
        last_saved = dt.datetime.fromtimestamp(offset_file.stat().st_mtime, dt.UTC).replace(tzinfo=None)
        next_edit = infobase_offset_time(offset)
        logger.info("Switching from the Infobase log at offset %s (saved %s, next edit %s)", offset, last_saved, next_edit)
        return min(next_edit or last_saved, last_saved) - SWITCH_OVERLAP
    if initial_state:
        return parse_initial_state(initial_state)
    logger.error("State file %s is not found. Reading transactions from the beginning of today", position_file)
    return dt.datetime.combine(dt.datetime.now(dt.UTC).date(), dt.time())


async def resolve_transaction_position(position_file: Path, offset_file: Path, initial_state: str | None) -> Position:
    start = await asyncio.to_thread(transaction_start, position_file, offset_file, initial_state)
    if isinstance(start, Position):
        return start
    return Position(transaction=await transaction_id_at(start), force_update=await force_update_seq_at(start))


async def run_from_transactions(state_file: str, initial_state: str | None) -> None:
    """Index keys from the ``transaction`` table, forever. Its position is saved next to the Infobase offset file."""
    offset_file = Path(state_file)
    position_file = offset_file.with_suffix(".txid")
    position = await resolve_transaction_position(position_file, offset_file, initial_state)
    created, behind = await position_status(position.transaction)
    logger.info("Reading transactions after id %s (created %s); %s transactions to catch up", position.transaction, created, behind)
    await write_state(position_file, position.dumps())

    log = TransactionLog(position.transaction)
    force_updates = ForceUpdates(position.force_update)
    while True:
        forced = await force_updates.read()
        batch = await log.read()
        await update_keys([*forced, *batch.keys])

        saved = Position(transaction=log.commit(), force_update=force_updates.commit())
        if saved != position:
            position = saved
            await write_state(position_file, position.dumps())
        if batch.transaction_count:
            lag = dt.datetime.now(dt.UTC).replace(tzinfo=None) - batch.last_created if batch.last_created else None
            logger.info("Indexed %d transactions, %s behind; position %s, waiting on %s", batch.transaction_count, lag, position.transaction, log.pending_gaps)

        # Keep going while there's a backlog; otherwise wait for more edits.
        if batch.transaction_count < log.batch_size and not forced:
            await asyncio.sleep(5)


async def run_from_infobase_log(
    state_file: str,
    initial_state: str | None,
    exclude_edits_containing: str | None,
) -> None:
    """Index keys from the Infobase HTTP write log, forever."""
    offset_file = Path(state_file)
    position_file = offset_file.with_suffix(".txid")
    if is_newer(position_file, offset_file):
        # Switching back from the transaction source. The log can only be addressed by
        # day, so start from the beginning of the day of its last position.
        saved = Position(**json.loads(await asyncio.to_thread(position_file.read_text)))
        created, _ = await position_status(saved.transaction)
        day = (created or dt.datetime.now(dt.UTC)).date().isoformat()
        logger.info("Switching from the transaction source; replaying the Infobase log from %s", day)
        offset = f"{day}:0"
        await write_state(offset_file, offset)
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
            await write_state(offset_file, offset)

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
