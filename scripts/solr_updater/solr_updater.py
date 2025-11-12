"""New script to handle solr updates.

Author: Anand Chitipothu

Changes:
2013-02-25: First version
2018-02-11: Use newer config method
"""

import asyncio
import datetime
import json
import logging
import re
import socket
import sys
from collections.abc import Iterator
from pathlib import Path

import aiofiles
import requests
import web

import infogami
from infogami import config
from openlibrary.config import load_config
from openlibrary.solr import update
from openlibrary.utils.open_syllabus_project import set_osp_dump_location
from openlibrary.utils.sentry import init_sentry
from openlibrary.utils.shutdown import setup_graceful_shutdown

logger = logging.getLogger("openlibrary.solr-updater")
# FIXME: Some kind of hack introduced to work around DB connectivity issue
args: dict = {}
setup_graceful_shutdown()


def read_state_file(path, initial_state: str | None = None):
    try:
        return open(path).read()
    except OSError:
        logger.error(
            "State file %s is not found. Reading log from the beginning of today", path
        )
        return initial_state or f"{datetime.date.today().isoformat()}:0"


def get_default_offset():
    return datetime.date.today().isoformat() + ":0"


class InfobaseLog:
    def __init__(self, hostname: str, exclude: str | None = None):
        """
        :param str hostname:
        :param str|None exclude: if specified, excludes records that include the string
        """
        self.base_url = 'http://%s/openlibrary.org/log' % hostname
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
                if e.args and e.args[0].args == (111, 'Connection refused'):
                    logger.error(
                        'make sure infogami server is working, connection refused from %s',
                        url,
                    )
                    sys.exit(1)
                raise

            try:
                d = resp.json()
            except:
                logger.error("Bad JSON: %s", resp.text)
                raise
            data = d['data']
            # no more data is available
            if not data:
                logger.debug("no more records found")
                # There's an infobase bug where we'll sometimes get 0 items, but the
                # binary offset will have incremented...?
                if 'offset' in d:
                    # There's _another_ infobase bug where if you query a future date,
                    # it'll return back 2020-12-01. To avoid solrupdater getting stuck
                    # in a loop, only update the offset if it's newer than the current
                    old_day, old_boffset = self.offset.split(':')
                    old_boffset = int(old_boffset)
                    new_day, new_boffset = d['offset'].split(':')
                    new_boffset = int(new_boffset)
                    if new_day >= old_day and new_boffset >= old_boffset:
                        self.offset = d['offset']
                return

            for record in data:
                if self.exclude and self.exclude in json.dumps(record):
                    continue
                yield record

            self.offset = d['offset']


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
        if 'key' in d:
            yield d['key']
        for val in d.values():
            yield from find_keys(val)
    elif isinstance(d, list):
        for val in d:
            yield from find_keys(val)
    else:
        # All other types are not recursed
        return


def parse_log(records, load_ia_scans: bool):
    for rec in records:
        action = rec.get('action')

        if action in ('save', 'save_many'):
            changeset = rec['data'].get('changeset', {})
            old_docs = changeset.get('old_docs', [])
            new_docs = changeset.get('docs', [])
            for before, after in zip(old_docs, new_docs):
                yield after['key']
                # before is None if the item is new
                if before:
                    before_keys = set(find_keys(before))
                    after_keys = set(find_keys(after))
                    # If a key was changed or was removed, the previous keys
                    # also need to be updated
                    yield from before_keys - after_keys

        elif action == 'store.put':
            # A sample record looks like this:
            # {
            #   "action": "store.put",
            #   "timestamp": "2011-12-01T00:00:44.241604",
            #   "data": {
            #       "data": {"borrowed": "false", "_key": "ebooks/books/OL5854888M", "_rev": "975708", "type": "ebook", "book_key": "/books/OL5854888M"},
            #       "key": "ebooks/books/OL5854888M"
            #   },
            #   "site": "openlibrary.org"
            # }
            data = rec.get('data', {}).get("data", {})
            key = data.get("_key", "")
            if data.get("type") == "ebook" and key.startswith("ebooks/books/"):
                edition_key = data.get('book_key')
                if edition_key:
                    yield edition_key
            elif (
                load_ia_scans
                and data.get("type") == "ia-scan"
                and key.startswith("ia-scan/")
            ):
                identifier = data.get('identifier')
                if identifier and is_allowed_itemid(identifier):
                    yield "/books/ia:" + identifier

            # Hack to force updating something from admin interface
            # The admin interface writes the keys to update to a document named
            # 'solr-force-update' in the store and whatever keys are written to that
            # are picked by this script
            elif key == 'solr-force-update':
                keys = data.get('keys')
                yield from keys

        elif action == 'store.delete':
            key = rec.get("data", {}).get("key")
            # An ia-scan key is deleted when that book is deleted/darked from IA.
            # Delete it from OL solr by updating that key
            if key.startswith("ia-scan/"):
                ol_key = "/works/ia:" + key.split("/")[-1]
                yield ol_key


def is_allowed_itemid(identifier):
    if not re.match("^[a-zA-Z0-9_.-]*$", identifier):
        return False

    # items starts with these prefixes are not books. Ignore them.
    ignore_prefixes = config.get("ia_ignore_prefixes", [])
    return all(not identifier.startswith(prefix) for prefix in ignore_prefixes)


async def update_keys(keys):
    if not keys:
        return 0

    # FIXME: Some kind of hack introduced to work around DB connectivity issue
    logger.debug("Args: %s" % str(args))
    update.load_configs(args['ol_url'], args['ol_config'], 'default')

    keys = [k for k in keys if update.can_update_key(k)]

    count = 0
    for chunk in web.group(keys, 100):
        chunk = list(chunk)
        count += len(chunk)
        await update.do_updates(chunk)

        # Caches should not persist between different calls to update_keys!
        update.data_provider.clear_cache()

    if count:
        logger.info("updated %d documents", count)

    return count


async def main(
    ol_config: str,
    osp_dump: Path | None = None,
    debugger: bool = False,
    state_file: str = 'solr-update.state',
    exclude_edits_containing: str | None = None,
    ol_url='http://openlibrary.org/',
    socket_timeout: int = 10,
    load_ia_scans: bool = False,
    initial_state: str | None = None,
):
    """
    Useful environment variables:
    - OL_SOLR_BASE_URL: Override the Solr base URL
    - OL_SOLR_NEXT: Set to true if running with next version of Solr/schema

    :param debugger: Wait for a debugger to attach before beginning
    :param exclude_edits_containing: Don't index matching edits
    :param solr_url: If wanting to override what's in the config file
    :param initial_state: State to use if state file doesn't exist. Defaults to today.
    """
    FORMAT = "%(asctime)-15s %(levelname)s %(message)s"
    logging.basicConfig(level=logging.INFO, format=FORMAT)
    logger.info("BEGIN solr_updater")

    if debugger:
        import debugpy  # noqa: PLC0415, T100

        logger.info("Enabling debugger attachment (attach if it hangs here)")
        debugpy.listen(address=('0.0.0.0', 3000))  # noqa: T100
        logger.info("Waiting for debugger to attach...")
        debugpy.wait_for_client()  # noqa: T100
        logger.info("Debugger attached to port 3000")

    # Sometimes archive.org requests blocks forever.
    # Setting a timeout will make the request fail instead of waiting forever.
    socket.setdefaulttimeout(socket_timeout)

    # set OL URL when running on a dev-instance
    if ol_url:
        host = web.lstrips(ol_url, "http://").strip("/")
        update.set_query_host(host)

    set_osp_dump_location(osp_dump)

    logger.info("loading config from %s", ol_config)
    load_config(ol_config)
    init_sentry(getattr(infogami.config, 'sentry', {}))

    offset = read_state_file(state_file, initial_state)

    logfile = InfobaseLog(
        config.get('infobase_server'), exclude=exclude_edits_containing
    )
    logfile.seek(offset)

    while True:
        records = logfile.read_records()
        keys = parse_log(records, load_ia_scans)
        count = await update_keys(keys)

        if logfile.tell() != offset:
            offset = logfile.tell()
            logger.info("saving offset %s", offset)
            async with aiofiles.open(state_file, "w") as f:
                await f.write(offset)

        # don't sleep after committing some records.
        # While the commit was on, some more edits might have happened.
        if count == 0:
            logger.debug("No more log records available, sleeping...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

    cli = FnToCLI(main)
    args = cli.args_dict()
    cli.run()
