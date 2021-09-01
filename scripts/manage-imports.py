#!/usr/bin/env python3

import sys
import web
import json
import logging
import datetime
import time
import _init_path
from openlibrary.config import load_config
from openlibrary.api import OpenLibrary, OLError
from openlibrary.core.ia import get_candidate_ocaids
from openlibrary.core.imports import Batch, ImportItem

logger = logging.getLogger("openlibrary.importer")


@web.memoize
def get_ol(servername=None):
    ol = OpenLibrary(base_url=servername)
    ol.autologin()
    return ol


def ol_import_request(item, retries=5, servername=None, require_marc=True):
    """Requests OL to import an item and retries on server errors.
    """
    # logger uses batch_id:id for item.data identifier if no item.ia_id
    _id = item.ia_id or "%s:%s" % (item.batch_id, item.id)
    logger.info("importing %s", _id)
    for i in range(retries):
        if i != 0:
            logger.info("sleeping for 5 seconds before next attempt.")
            time.sleep(5)
        try:
            ol = get_ol(servername=servername)
            if item.ia_id:
                return ol.import_ocaid(item.ia_id, require_marc=require_marc)
            else:
                return ol.import_data(item.data)
        except IOError as e:
            logger.warning("Failed to contact OL server. error=%s", e)
        except OLError as e:
            if e.code < 500:
                return e.text
            logger.warning("Failed to contact OL server. error=%s", e)


def do_import(item, servername=None, require_marc=True):
    response = ol_import_request(item, servername=servername, require_marc=require_marc)
    if response and response.startswith('{'):
        d = json.loads(response)
        if d.get('success') and 'edition' in d:
            edition = d['edition']
            logger.info("success: %s %s", edition['status'], edition['key'])
            item.set_status(edition['status'], ol_key=edition['key'])
        else:
            error_code = d.get('error_code', 'unknown-error')
            logger.error("failed with error code: %s", error_code)
            item.set_status("failed", error=error_code)
    else:
        logger.error("failed with internal error: %s", response)
        item.set_status("failed", error='internal-error')


def add_items(args):
    batch_name = args[0]
    filename = args[1]
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
    servername = kwargs.get('servername', None)
    require_marc = not kwargs.get('no_marc', False)

    date = datetime.date.today()
    if not ocaids:
        raise ValueError("Must provide at least one ocaid")
    batch_name = "import-%s-%04d%02d" % (ocaids[0], date.year, date.month)
    try:
        batch = Batch.new(batch_name)
    except Exception as e:
        logger.info(str(e))
    try:
        batch.add_items(ocaids)
    except Exception:
        logger.info("skipping batch adding, already present")

    for ocaid in ocaids:
        item = ImportItem.find_by_identifier(ocaid)
        if item:
            do_import(item, servername=servername, require_marc=require_marc)
        else:
            logger.error("%s is not found in the import queue", ocaid)

def add_data(args, source="bwb"):
    # [-] Testing manual adding small batch
    items = [
        {"title": "Aulus Gellii Noctes Atticae Vol. II, Bks. 11-20 : Recognovit Brevique Adnotatione Critica Instruxit Tomus", "isbn_13": ["9780198146520"], "publish_date": "1990", "publishers": ["Oxford University Press"], "authors": [{"name": "Gellius, Aulus"}, {"name": "Marshall, P. K."}], "lc_classifications": [""], "number_of_pages": "336", "languages": ["eng"], "subjects": ["Latin literature, medieval and modern"], "source_records": ["bwb:9780198146520"]},
        {"title": "A. Gellii Noctes Atticae : Recognovit Brevique Adnotatione Critica Instruxit Tomus I - Libri I-X", "isbn_13": ["9780198146513"], "publish_date": "1968", "publishers": ["Oxford University Press"], "authors": [{"name": "Gellius, Aulus"}, {"name": "Marshall, P. K."}], "lc_classifications": [""], "number_of_pages": "376", "languages": ["eng"], "subjects": ["Latin literature, medieval and modern"], "source_records": ["bwb:9780198146513"]},
        {"title": "A. M. MacKay : Pioneer Missionary of the Church Missionary Society to Uganda", "isbn_13": ["9780714618746"], "publish_date": "1970", "publishers": ["Taylor & Francis Group"], "authors": [{"name": "Mackay, A. M."}], "lc_classifications": ["BV3625.U4M4"], "number_of_pages": "485", "languages": ["eng"], "subjects": ["Missionaries, british", "Missionaries, biography"], "source_records": ["bwb:9780714618746"]}
    ]
    date = datetime.date.today()
    batch_name = "%s-%04d%02d" % (source, date.year, date.month)
    batch = Batch.find(batch_name) or Batch.new(batch_name)
    batch.add_items(items, ia_items=False)

def import_data(args):
    # [x] Testing imports work to new ol.import_data json data api
    data = args[0]
    ol = get_ol()
    r = ol.import_data(data)
    print(r)
    return r


def add_new_scans(args):
    """Adds new scans from yesterday.
    """
    if args:
        datestr = args[0]
        yyyy, mm, dd = datestr.split("-")
        date = datetime.date(int(yyyy), int(mm), int(dd))
    else:
        # yesterday
        date = datetime.date.today() - datetime.timedelta(days=1)

    items = get_candidate_ocaids(since_date=date)
    batch_name = "new-scans-%04d%02d" % (date.year, date.month)
    batch = Batch.find(batch_name) or Batch.new(batch_name)
    batch.add_items(items)


def import_batch(args, **kwargs):
    servername = kwargs.get('servername', None)
    require_marc = not kwargs.get('no_marc', False)
    batch_name = args[0]
    batch = Batch.find(batch_name)
    if not batch:
        print("Unknown batch", batch, file=sys.stderr)
        sys.exit(1)

    for item in batch.get_items():
        do_import(item, servername=servername, require_marc=require_marc)


def import_item(args, **kwargs):
    servername = kwargs.get('servername', None)
    require_marc = not kwargs.get('no_marc', False)
    ia_id = args[0]
    item = ImportItem.find_by_identifier(ia_id)
    if item:
        do_import(item, servername=servername, require_marc=require_marc)
    else:
        logger.error("%s is not found in the import queue", ia_id)


def import_all(args, **kwargs):
    servername = kwargs.get('servername', None)
    require_marc = not kwargs.get('no_marc', False)
    while True:
        items = ImportItem.find_pending()
        if not items:
            logger.info("No pending items found. sleeping for a minute.")
            time.sleep(60)

        for item in items:
            do_import(item, servername=servername, require_marc=require_marc)

def retroactive_import(start=None, stop=None, servername=None):
    """Retroactively searches and imports all previously missed books
    (through all time) in the Archive.org database which were
    created after scribe3 was released (when we switched repub states
    from 4 to [19, 20, 22]).
    """
    scribe3_repub_states = [19, 20, 22]
    items = get_candidate_ocaids(
        scanned_within_days=None, repub_states=scribe3_repub_states)[start:stop]
    date = datetime.date.today()
    batch_name = "new-scans-%04d%02d" % (date.year, date.month)
    batch = Batch.find(batch_name) or Batch.new(batch_name)
    batch.add_items(items)
    for item in batch.get_items():
        do_import(item, servername=servername)


def main():
    if "--config" in sys.argv:
        index = sys.argv.index("--config")
        configfile = sys.argv[index+1]
        del sys.argv[index:index+2]
    else:
        import os
        configfile = os.path.abspath(os.path.join(
            os.path.dirname(__file__), os.pardir, os.pardir,
            'openlibrary', 'conf', 'openlibrary.yml'))

    load_config(configfile)

    from infogami import config

    cmd = sys.argv[1]
    args, flags = [], {'servername': config.get('servername', 'https://openlibrary.org')}
    for i in sys.argv[2:]:
        if i.startswith('--'):
            flags[i[2:]] = True
        else:
            args.append(i)

    if cmd == "import-retro":
        start, stop = (int(a) for a in args) if \
                      (args and len(args) == 2) else (None, None)
        return retroactive_import(start=start, stop=stop, servername=flags['servername'])
    if cmd == "import-ocaids":
        return import_ocaids(*args, **flags)
    if cmd == "add-items":
        return add_items(args)
    elif cmd == "add-new-scans":
        return add_new_scans(args)
    elif cmd == "add-data":
        return add_data(args)
    elif cmd == "import-data":
        return import_data(args)
    elif cmd == "import-batch":
        return import_batch(args, **flags)
    elif cmd == "import-all":
        return import_all(args, **flags)
    elif cmd == "import-item":
        return import_item(args, **flags)
    else:
        logger.error("Unknown command: %s", cmd)


if __name__ == "__main__":
    main()
