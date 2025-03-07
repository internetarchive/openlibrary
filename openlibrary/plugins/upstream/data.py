"""Code for handling /data/*.txt.gz URLs."""

import requests
import web

from infogami import config
from infogami.utils import delegate
from infogami.utils.view import public  # noqa: F401 side effects may be needed

IA_BASE_URL = config.get('ia_base_url')


def get_ol_dumps():
    """Get list of all archive.org items in the ol_exports collection uploaded by archive.org staff."""
    url = (
        IA_BASE_URL
        + '/advancedsearch.php?q=collection:ol_exports+AND+(ol_dump+OR+ol_cdump)&fl[]=identifier&output=json&rows=1000'
    )
    docs = requests.get(url).json()['response']['docs']
    return sorted(doc['identifier'] for doc in docs)


# cache the result for half an hour
get_ol_dumps = web.memoize(get_ol_dumps, 30 * 60, background=True)
# public(get_ol_dumps)


def download_url(item, filename):
    return f"{IA_BASE_URL}/download/{item}/{filename}"


# Should include openlibrary/data/dump.py split_dump's types at least
DUMP_PREFIXES = (
    '',
    '_authors',
    '_covers_metadata',
    '_editions',
    '_works',
    '_redirects',
    '_deletes',
    '_lists',
    '_other',
    '_deworks',
    '_ratings',
    '_reading-log',
)


class ol_dump_latest(delegate.page):
    path = f"/data/ol_dump({'|'.join(DUMP_PREFIXES)})_latest.txt.gz"

    def GET(self, prefix):
        items = [item for item in get_ol_dumps() if item.startswith("ol_dump")]
        if not items:
            raise web.notfound()

        item = items[-1]
        filename = item.replace("dump", "dump" + prefix) + ".txt.gz"
        raise web.found(download_url(item, filename))


class ol_cdump_latest(delegate.page):
    path = "/data/ol_cdump_latest.txt.gz"

    def GET(self):
        items = [item for item in get_ol_dumps() if item.startswith("ol_cdump")]
        if not items:
            raise web.notfound()

        item = items[-1]
        raise web.found(download_url(item, item + ".txt.gz"))


class ol_dumps(delegate.page):
    path = rf"/data/ol_dump({'|'.join(DUMP_PREFIXES)})_(\d\d\d\d-\d\d-\d\d).txt.gz"

    def GET(self, prefix, date):
        item = "ol_dump_" + date
        if item not in get_ol_dumps():
            raise web.notfound()
        else:
            filename = "ol_dump" + prefix + "_" + date + ".txt.gz"
            raise web.found(download_url(item, filename))


class ol_cdumps(delegate.page):
    path = r"/data/ol_cdump_(\d\d\d\d-\d\d-\d\d).txt.gz"

    def GET(self, date):
        item = "ol_cdump_" + date
        if item not in get_ol_dumps():
            raise web.notfound()
        else:
            raise web.found(download_url(item, item + ".txt.gz"))


def setup():
    pass
