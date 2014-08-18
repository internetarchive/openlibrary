#! /usr/bin/env python
import sys
import _init_path
from openlibrary.config import load_config
from openlibrary.api import OpenLibrary, OLError
from openlibrary.solr.process_stats import get_ia_db
from openlibrary.core.imports import Batch, ImportItem
import web
import json
import logging
import datetime
import time

logger = logging.getLogger("openlibrary.importer")

@web.memoize
def get_ol():
    ol = OpenLibrary("https://anand.openlibrary.org")
    ol.autologin()
    return ol

def ol_import_request(item, retries=5):
    """Requests OL to import an item and retries on server errors.
    """
    logger.info("importing %s", item.ia_id)    
    for i in range(retries):
        if i != 0:
            logger.info("sleeping for 5 seconds before next attempt.")
            time.sleep(5)
        try:
            ol = get_ol()
            return ol._request('/api/import/ia', method='POST', data='identifier=' + item.ia_id).read()
        except (IOError, OLError), e:
            logger.warn("Failed to contact OL server. error=%s", e)


def do_import(item):
    response = ol_import_request(item)

    if response and response.startswith("{"):
        d = json.loads(response)
        if d.get("success") and 'edition' in d:
            edition = d['edition']
            logger.info("success: %s %s", edition['status'], edition['key'])
            item.set_status(edition['status'], ol_key=edition['key'])
        else:
            error_code = d.get('error_code', 'unknown-error')
            logger.error("failed with error code: %s", error_code)
            item.set_status("failed", error=error_code)
    else:
        logger.error("failed with internal error")
        item.set_status("failed", error='internal-error')

def add_items(args):
    batch_name = args[0]
    filename = args[1]

    batch = Batch.find(batch_name) or Batch.new(batch_name)
    batch.load_items(filename)

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

    c1 = '%opensource%'
    c2 = '%additional_collections%'

    # Find all scans which are updated/added on the given date 
    # and have been scanned at most 2 months ago
    q = ("SELECT identifier FROM metadata" +
        " WHERE repub_state=4" +
        "   AND mediatype='texts'" +
        "   AND scancenter IS NOT NULL" +
        "   AND collection NOT LIKE $c1" +
        "   AND collection NOT LIKE $c2" + 
        "   AND (curatestate IS NULL OR curatestate != 'dark')" +
        "   AND lower(format) LIKE '%%pdf%%' AND lower(format) LIKE '%%marc%%'" +
        "   AND scandate is NOT NULL AND scandate > $min_scandate" +
        "   AND updated > $date AND updated < ($date::date + INTERVAL '1' DAY)")

    min_scandate = date - datetime.timedelta(60) # 2 months ago
    result = get_ia_db().query(q, vars=dict(
        c1=c1, 
        c2=c2, 
        date=date.isoformat(),
        min_scandate=min_scandate.strftime("%Y%m%d")))
    items = [row.identifier for row in result]    
    batch_name = "new-scans-%04d%02d" % (date.year, date.month)
    batch = Batch.find(batch_name) or Batch.new(batch_name)
    batch.add_items(items)

def import_batch(args):
    batch_name = args[0]
    batch = Batch.find(batch_name)
    if not batch:
        print >> sys.syderr, "Unknown batch", batch
        sys.exit(1)

    for item in batch.get_items():
        do_import(item)

def import_item(args):
    ia_id = args[0]
    item = ImportItem.find_by_identifier(ia_id)
    if item:
        do_import(item)
    else:
        logger.error("%s is not found in the import queue", ia_id)

def import_all(args):
    while True:
        items = ImportItem.find_pending()
        if not items:
            logger.info("No pending items found. sleeping for a minute.")
            time.sleep(60)

        for item in items:
            do_import(item)

def main():
    if "--config" in sys.argv:
        index = sys.argv.index("--config")
        configfile = sys.argv[index+1]
        del sys.argv[index:index+2]
    else:
        configfile = "openlibrary.yml"
    load_config(configfile)

    cmd = sys.argv[1]
    args = sys.argv[2:]
    if cmd == "add-items":
        return add_items(args)
    elif cmd == "add-new-scans":
        return add_new_scans(args)
    elif cmd == "import-batch":
        return import_batch(args)
    elif cmd == "import-all":
        return import_all(args)
    elif cmd == "import-item":
        return import_item(args)
    else:
        logger.error("Unknown command: %s", cmd)

if __name__ == "__main__":
    main()
