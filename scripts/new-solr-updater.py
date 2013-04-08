"""New script to handle solr updates.

Author: Anand Chitipothu

Changes:
2013-02-25: First version
"""

import _init_path

import yaml
import logging
import json
import urllib, urllib2
import argparse
import datetime
import time
import web
import sys
import re
import socket

from openlibrary.solr import update_work
from openlibrary import config

logger = logging.getLogger("solr-updater")

def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config')
    parser.add_argument('--state-file', default="solr-update.state")
    parser.add_argument('--ol-url', default="http://openlibrary.org/")
    parser.add_argument('--socket-timeout', type=int, default=10)
    return parser.parse_args()

def load_config(path):
    c = yaml.safe_load(open(path))

    # required for update_work module to work
    config.runtime_config = c
    return c

def read_state_file(path):
    try:
        return open(path).read()
    except IOError:
        logger.error("State file %s is not found. Reading log from the beginning of today", path)
        return datetime.date.today().isoformat() + ":0"

def get_default_offset():
    return datetime.date.today().isoformat() + ":0"


class InfobaseLog:
    def __init__(self, hostname):
        self.base_url = 'http://%s/openlibrary.org/log' % hostname
        self.offset = get_default_offset()

    def tell(self):
        return self.offset

    def seek(self, offset):
        self.offset = offset.strip()

    def read_records(self, max_fetches=10):
        """Reads all the available log records from the server.
        """
        for i in range(max_fetches):
            url = "%s/%s?limit=100" % (self.base_url, self.offset)
            logger.info("Reading log from %s", url)
            try:
                jsontext = urllib2.urlopen(url).read()
            except urllib2.URLError as e:
                logger.error("Failed to open URL %s", url, exc_info=True)
                if e.args and e.args[0].args == (111, 'Connection refused'):
                    logger.error('make sure infogami server is working, connection refused from %s', url)
                    sys.exit(1)
                raise

            try:
                d = json.loads(jsontext)
            except:
                logger.error("Bad JSON: %s", jsontext)
                raise
            data = d['data']
            # no more data is available
            if not data:
                logger.info("no more records found")
                return

            for record in data:
                yield record

            self.offset = d['offset']

def parse_log(records):
    for rec in records:
        action = rec.get('action')
        if action == 'save':
            key = rec['data'].get('key')
            if key:
                yield key
        elif action == 'save_many':
            changes = rec['data'].get('changeset', {}).get('changes', [])
            for c in changes:
                yield c['key']

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
            if data.get("type") == "ebook" and data.get("_key", "").startswith("ebooks/books/"):
                edition_key = data.get('book_key')
                if edition_key:
                    yield edition_key
            elif data.get("type") == "ia-scan" and data.get("_key", "").startswith("ia-scan/"):
                identifier = data.get('identifier')
                if identifier and is_allowed_itemid(identifier):
                    yield "/books/ia:" + identifier

def is_allowed_itemid(identifier):
    if not re.match("^[a-zA-Z0-9_.-]*$", identifier):
        return False

    # items starts with these prefixes are not books. Ignore them.
    ignore_prefixes = config.runtime_config.get("ia_ignore_prefixes", [])
    for prefix in ignore_prefixes:
        if identifier.startswith(prefix):
            return False
        
    return True            

def update_keys(keys):
    keys = (k for k in keys if k.count("/") == 2 and k.split("/")[1] in ["books", "authors", "works"])

    count = 0
    for chunk in web.group(keys, 100):
        chunk = list(chunk)
        count += len(chunk)
        update_work.update_keys(chunk, commit=False)

    if count:
        logger.info("updated %d documents", count)

    return count

class Solr:
    def __init__(self):
        self.reset()

    def reset(self):
        self.total_docs = 0
        self.t_start = time.time()

    def commit(self, ndocs):
        """Performs solr commit only if there are sufficient number
        of documents or enough time has been passed since last commit.
        """
        self.total_docs += ndocs

        # no documents to commit
        if not self.total_docs:
            return

        dt = time.time() - self.t_start
        if self.total_docs > 100 or dt > 60:
            logger.info("doing solr commit (%d docs updated, last commit was %0.1f seconds ago)", self.total_docs, dt)
            self._solr_commit()
            self.reset()
        else:
            logger.info("skipping solr commit (%d docs updated, last commit was %0.1f seconds ago)", self.total_docs, dt)

    def _solr_commit(self):
        logger.info("BEGIN commit")
        update_work.solr_update(['<commit/>'], index="works")
        logger.info("END commit")

def main():
    FORMAT = "%(asctime)-15s %(levelname)s %(message)s"
    logging.basicConfig(level=logging.INFO, format=FORMAT)

    logger.info("BEGIN new-solr-updater")

    args = parse_arguments()

    # Sometimes archive.org requests blocks forever. 
    # Setting a timeout will make the request fail instead of waiting forever. 
    socket.settimeout(args.socket_timeout)

    # set OL URL when running on a dev-instance
    if args.ol_url:
        host = web.lstrips(args.ol_url, "http://").strip("/")
        update_work.set_query_host(host)

    config = load_config(args.config)

    state_file = args.state_file
    offset = read_state_file(state_file)

    logfile = InfobaseLog(config['infobase_server'])
    logfile.seek(offset)

    solr = Solr()

    while True:
        records = logfile.read_records()
        keys = parse_log(records)
        count = update_keys(keys)

        offset = logfile.tell()
        logger.info("saving offset %s", offset)
        with open(state_file, "w") as f:
            f.write(offset)

        solr.commit(ndocs=count)

        # don't sleep after committing some records. 
        # While the commit was on, some more edits might have happened.
        if count == 0:
            logger.info("No more log records available, sleeping...")
            time.sleep(5)

if __name__ == "__main__":
    main()
