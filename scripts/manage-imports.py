#!/usr/bin/env python

import datetime
import json
import logging
import multiprocessing
import os
import sys
import time

import web

from openlibrary.api import OLError, OpenLibrary
from openlibrary.config import load_config
from openlibrary.core.ia import get_candidate_ocaids
from openlibrary.core.imports import Batch, ImportItem

logger = logging.getLogger("openlibrary.importer")


@web.memoize
def get_ol(servername=None):
    if os.getenv('LOCAL_DEV'):
        ol = OpenLibrary(base_url="http://localhost:8080")
        ol.login("admin", "admin123")
    else:
        ol = OpenLibrary(base_url=servername)
        ol.autologin()
    return ol


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
            ol = get_ol(servername=servername)
            if item.data:
                return ol.import_data(item.data)
            return ol.import_ocaid(item.ia_id, require_marc=require_marc)
        except OSError as e:
            logger.warning(f"Failed to contact OL server. error={e!r}")
        except OLError as e:
            logger.warning(f"Failed to contact OL server. error={e!r}")
            if e.code < 500:
                return e.text


def do_import(item, servername=None, require_marc=True):

    logger.info(f"do_import START (pid:{os.getpid()})")
    response = ol_import_request(item, servername=servername, require_marc=require_marc)
    if response and response.startswith('{'):
        d = json.loads(response)
        if d.get('success') and 'edition' in d:
            edition = d['edition']
            logger.info(f"success: {edition['status']} {edition['key']}")
            item.set_status(edition['status'], ol_key=edition['key'])
        else:
            error_code = d.get('error_code', 'unknown-error')
            logger.error(f"failed with error code: {error_code}")
            item.set_status("failed", error=error_code)
    else:
        logger.error(f"failed with internal error: {response}")
        item.set_status("failed", error='internal-error')
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
    servername = kwargs.get('servername')
    require_marc = not kwargs.get('no_marc', False)

    date = datetime.date.today()
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
        date = datetime.date(int(yyyy), int(mm), int(dd))
    else:
        # yesterday
        date = datetime.date.today() - datetime.timedelta(days=1)

    items = list(get_candidate_ocaids(date))
    batch_name = f"new-scans-{date.year:04}{date.month:02}"
    batch = Batch.find(batch_name) or Batch.new(batch_name)
    batch.add_items(items)


def import_batch(args, **kwargs):
    servername = kwargs.get('servername')
    require_marc = not kwargs.get('no_marc', False)
    batch_name = args[0]
    batch = Batch.find(batch_name)
    if not batch:
        print("Unknown batch", batch, file=sys.stderr)
        sys.exit(1)

    for item in batch.get_items():
        do_import(item, servername=servername, require_marc=require_marc)


def import_item(args, **kwargs):
    servername = kwargs.get('servername')
    require_marc = not kwargs.get('no_marc', False)
    ia_id = args[0]
    if item := ImportItem.find_by_identifier(ia_id):
        do_import(item, servername=servername, require_marc=require_marc)
    else:
        logger.error(f"{ia_id} is not found in the import queue")


def import_all(args, **kwargs):

    servername = kwargs.get('servername')
    require_marc = False

    # Use multiprocessing to call do_import on each item
    with multiprocessing.Pool(processes=8) as pool:
        while True:
            logger.info("find_pending START")
            items = ImportItem.find_pending()
            logger.info("find_pending END")

            if not items:
                logger.info("No pending items found. sleeping for a minute.")
                time.sleep(60)
                continue

            logger.info("starmap START")
            pool.starmap(
                do_import, ((item, servername, require_marc) for item in items)
            )
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
                'openlibrary',
                'conf',
                'openlibrary.yml',
            )
        )

    load_config(configfile)

    from infogami import config  # noqa: PLC0415

    cmd = sys.argv[1]
    args, flags = [], {
        'servername': config.get('servername', 'https://openlibrary.org')
    }
    for i in sys.argv[2:]:
        if i.startswith('--'):
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
