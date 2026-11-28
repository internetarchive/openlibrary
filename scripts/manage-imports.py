#!/usr/bin/env python

import datetime as dt
import functools
import json
import logging
import multiprocessing
import os
import sys
import time

from infogami import config
from openlibrary.api import OLError, OpenLibrary
from openlibrary.config import load_config
from openlibrary.core.env import get_ol_env
from openlibrary.core.ia import get_candidate_ocaids
from openlibrary.core.imports import Batch, ImportItem
from openlibrary.utils.retry import RetryStrategy
from openlibrary.utils.sentry import init_sentry

logger = logging.getLogger("openlibrary.importer")


# Set in import-all pool workers, which reuse the parent's session rather than
# all logging in at once: most of a burst of logins to one account fail.
_session_cookie: str | None = None


@functools.cache
def get_ol(servername: str) -> OpenLibrary:
    ol = OpenLibrary(servername)
    if _session_cookie:
        ol.cookie = _session_cookie
    elif get_ol_env().LOCAL_DEV:
        ol.login("openlibrary@example.com", "admin123")
    else:
        # Log in with RC file from OPENLIBRARY_RCFILE env var
        ol.autologin()
    # A failed login returns normally, just without a session. Raise so
    # functools.cache doesn't keep a client that gets a 403 on every import.
    if "session=" not in (ol.cookie or ""):
        raise RuntimeError("Open Library login returned no session cookie")
    return ol


def setup_sentry() -> None:
    # Errors still become events; Sentry Logs would also ship the per-item
    # INFO/WARNING chatter for every import.
    init_sentry(getattr(config, "sentry", {}) | {"enable_logs": False})


def init_import_worker(configfile: str, cookie: str) -> None:
    global _session_cookie
    load_config(configfile)
    # Pool workers are spawned fresh (forkserver), not forked, so they don't
    # inherit the parent's Sentry client.
    setup_sentry()
    _session_cookie = cookie


def ol_import_request(item, retries=5, servername=None, require_marc=True):
    """Requests OL to import an item and retries on server errors."""
    # logger uses batch_id:id for item.data identifier if no item.ia_id
    _id = item.ia_id or f"{item.batch_id}:{item.id}"
    logger.info(f"importing {_id}")
    for i in range(retries):
        if i != 0:
            logger.info("sleeping for 5 seconds before next attempt.")
            time.sleep(5)
        try:
            ol = get_ol(servername)
            if item.data:
                return ol.import_data(item.data)
            return ol.import_ocaid(item.ia_id, require_marc=require_marc)
        except OSError as e:
            logger.warning(f"Failed to contact OL server. error={e!r}")
        except OLError as e:
            logger.warning(f"OL import request failed. status={e.code} body={e.text[:500]!r}")
            if e.code < 500:
                return e.text


def do_import(item, servername=None, require_marc=True, only_pending=False):
    logger.info(f"do_import START (pid:{os.getpid()})")
    # import-all fetches items in bulk before importing them, so their batch may have been paused since.
    if only_pending and not item.is_pending():
        logger.info(f"skipping item {item.id}: no longer pending")
        return
    try:
        response = ol_import_request(item, servername=servername, require_marc=require_marc)
        if response and response.startswith("{"):
            d = json.loads(response)
            if d.get("success") and "edition" in d:
                edition = d["edition"]
                logger.info(f"success: {edition['status']} {edition['key']}")
                item.set_status(edition["status"], ol_key=edition["key"])
            else:
                error_code = d.get("error_code", "unknown-error")
                # Routine rejections (e.g. validation errors); not Sentry-worthy.
                logger.warning(f"failed with error code: {error_code}")
                item.set_status("failed", error=error_code)
        else:
            logger.error(f"failed with internal error: {response}")
            item.set_status("failed", error="internal-error")
    except Exception:
        # One bad item must not take down the whole import-all loop.
        logger.exception(f"failed with unexpected error importing item {item.id}")
        item.set_status("failed", error="internal-error")
    logger.info(f"do_import END (pid:{os.getpid()})")


def add_items(batch_name, filename):
    batch = Batch.find(batch_name) or Batch.new(batch_name)
    batch.load_items(filename)


def import_ocaids(*ocaids, **kwargs):
    """This method is mostly for testing. It allows you to import one more
    archive.org items into Open Library by ocaid

    Usage:
        $ sudo -u openlibrary \
            HOME=/home/openlibrary OPENLIBRARY_RCFILE=/olsystem/etc/olrc-importbot \
            python scripts/manage-imports.py \
                --config /olsystem/etc/openlibrary.yml \
                import-all
    """
    servername = kwargs.get("servername")
    require_marc = not kwargs.get("no_marc", False)

    date = dt.date.today()
    if not ocaids:
        raise ValueError("Must provide at least one ocaid")
    batch_name = f"import-{ocaids[0]}-{date.year:04}{date.month:02}"
    try:
        batch = Batch.new(batch_name)
    except Exception as e:
        logger.info(repr(e))
    try:
        batch.add_items(ocaids)
    except Exception:
        logger.info("skipping batch adding, already present")

    for ocaid in ocaids:
        item = ImportItem.find_by_identifier(ocaid)
        if item:
            do_import(item, servername=servername, require_marc=require_marc)
        else:
            logger.error(f"{ocaid} is not found in the import queue")


def add_new_scans(args):
    """Adds new scans from yesterday."""
    if args:
        datestr = args[0]
        yyyy, mm, dd = datestr.split("-")
        date = dt.date(int(yyyy), int(mm), int(dd))
    else:
        # yesterday
        date = dt.date.today() - dt.timedelta(days=1)

    items = list(get_candidate_ocaids(date))
    batch_name = f"new-scans-{date.year:04}{date.month:02}"
    batch = Batch.find(batch_name) or Batch.new(batch_name)
    batch.add_items(items)


def import_batch(args, **kwargs):
    servername = kwargs.get("servername")
    require_marc = not kwargs.get("no_marc", False)
    batch_name = args[0]
    batch = Batch.find(batch_name)
    if not batch:
        print("Unknown batch", batch, file=sys.stderr)
        sys.exit(1)

    for item in batch.get_items():
        do_import(item, servername=servername, require_marc=require_marc)


def import_item(args, **kwargs):
    servername = kwargs.get("servername")
    require_marc = not kwargs.get("no_marc", False)
    ia_id = args[0]
    if item := ImportItem.find_by_identifier(ia_id):
        do_import(item, servername=servername, require_marc=require_marc)
    else:
        logger.error(f"{ia_id} is not found in the import queue")


def import_all(args, **kwargs):

    servername = kwargs.get("servername")
    require_marc = False
    configfile = kwargs.get("configfile")
    sleep = int(os.getenv("OL_IMPORT_ALL_SLEEP", "60"))
    processes = int(os.getenv("OL_IMPORT_ALL_PROCESSES", "8"))

    ol = RetryStrategy([RuntimeError, OSError], max_retries=5, delay=5)(lambda: get_ol(servername))

    # Use multiprocessing to call do_import on each item
    with multiprocessing.Pool(
        processes=processes,
        initializer=init_import_worker,
        initargs=(configfile, ol.cookie),
    ) as pool:
        while True:
            logger.info("find_pending START")
            items = ImportItem.find_pending()
            logger.info("find_pending END")

            if not items:
                logger.info(f"No pending items found. sleeping for {sleep} seconds before next attempt.")
                time.sleep(sleep)
                continue

            logger.info("starmap START")
            pool.starmap(do_import, ((item, servername, require_marc, True) for item in items))
            logger.info("starmap END")


def main():
    if "--config" in sys.argv:
        index = sys.argv.index("--config")
        configfile = sys.argv[index + 1]
        del sys.argv[index : index + 2]
    else:
        configfile = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                os.pardir,
                os.pardir,
                "openlibrary",
                "conf",
                "openlibrary.yml",
            )
        )

    load_config(configfile)
    setup_sentry()

    cmd = sys.argv[1]
    args, flags = [], {"servername": config.get("servername", "https://openlibrary.org"), "configfile": configfile}
    for i in sys.argv[2:]:
        if i.startswith("--"):
            flags[i[2:]] = True
        else:
            args.append(i)

    if cmd == "import-ocaids":
        return import_ocaids(*args, **flags)
    if cmd == "add-items":
        return add_items(*args)
    elif cmd == "add-new-scans":
        return add_new_scans(args)
    elif cmd == "import-batch":
        return import_batch(args, **flags)
    elif cmd == "import-all":
        return import_all(args, **flags)
    elif cmd == "import-item":
        return import_item(args, **flags)
    else:
        logger.error(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
