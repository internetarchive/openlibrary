"""Library for interacting with archive.org.
"""

import logging
import os
import requests
import web

from infogami import config
from infogami.utils import stats

from openlibrary.core import cache
from openlibrary.utils.dateutil import date_n_days_ago

logger = logging.getLogger('openlibrary.ia')

# FIXME: We can't reference `config` in module scope like this; it will always be undefined!
# See lending.py for an example of how to do it correctly.
IA_BASE_URL = config.get('ia_base_url', 'https://archive.org')
VALID_READY_REPUB_STATES = ['4', '19', '20', '22']


def get_api_response(url, params=None):
    """
    Makes an API GET request to archive.org, collects stats
    Returns a JSON dict.
    :param str url:
    :param dict params: url parameters
    :rtype: dict
    """
    api_response = {}
    stats.begin('archive.org', url=url)
    try:
        r = requests.get(url, params=params)
        if r.status_code == requests.codes.ok:
            api_response = r.json()
        else:
            logger.info(f'{r.status_code} response received from {url}')
    except Exception as e:
        logger.exception('Exception occurred accessing %s.' % url)
    stats.end()
    return api_response


def get_metadata_direct(itemid, only_metadata=True, cache=True):
    """
    Fetches metadata by querying the archive.org metadata API, without local caching.
    :param str itemid:
    :param bool cache: if false, requests uncached metadata from archive.org
    :param bool only_metadata: whether to get the metadata without any processing
    :rtype: dict
    """
    url = f'{IA_BASE_URL}/metadata/{web.safestr(itemid.strip())}'
    params = {}
    if cache:
        params['dontcache'] = 1
    full_json = get_api_response(url, params)
    return extract_item_metadata(full_json) if only_metadata else full_json


get_metadata = cache.memcache_memoize(
    get_metadata_direct, key_prefix='ia.get_metadata', timeout=5 * cache.MINUTE_SECS
)


def extract_item_metadata(item_json):
    metadata = process_metadata_dict(item_json.get('metadata', {}))
    if metadata:
        # if any of the files is access restricted, consider it as
        # an access-restricted item.
        files = item_json.get('files', [])
        metadata['access-restricted'] = any(f.get('private') == 'true' for f in files)

        # remember the filenames to construct download links
        metadata['_filenames'] = [f['name'] for f in files]
    return metadata


def process_metadata_dict(metadata):
    """Process metadata dict to make sure multi-valued fields like
    collection and external-identifier are always lists.

    The metadata API returns a list only if a field has more than one value
    in _meta.xml. This puts burden on the application to handle both list and
    non-list cases. This function makes sure the known multi-valued fields are
    always lists.
    """
    multivalued = {'collection', 'external-identifier', 'isbn', 'subject', 'oclc-id'}

    def process_item(k, v):
        if k in multivalued and not isinstance(v, list):
            v = [v]
        elif k not in multivalued and isinstance(v, list):
            v = v[0]
        return (k, v)

    return dict(process_item(k, v) for k, v in metadata.items() if v)


def locate_item(itemid):
    """Returns (hostname, path) for the item."""
    d = get_metadata_direct(itemid, only_metadata=False)
    return d.get('server'), d.get('dir')


def edition_from_item_metadata(itemid, metadata):
    """Converts the item metadata into a form suitable to be used as edition
    in Open Library.

    This is used to show fake editon pages like '/books/ia:foo00bar' when
    that item is not yet imported into Open Library.
    """
    if ItemEdition.is_valid_item(itemid, metadata):
        e = ItemEdition(itemid)
        e.add_metadata(metadata)
        return e


def get_cover_url(item_id):
    """Gets the URL of the archive.org item's title (or cover) page."""
    base_url = f'{IA_BASE_URL}/download/{item_id}/page/'
    title_response = requests.head(base_url + 'title.jpg', allow_redirects=True)
    if title_response.status_code == 404:
        return base_url + 'cover.jpg'
    return base_url + 'title.jpg'


def get_item_manifest(item_id, item_server, item_path):
    url = 'https://%s/BookReader/BookReaderJSON.php' % item_server
    url += f'?itemPath={item_path}&itemId={item_id}&server={item_server}'
    return get_api_response(url)


def get_item_status(itemid, metadata, **server):
    item_server = server.pop('item_server', None)
    item_path = server.pop('item_path', None)
    return ItemEdition.get_item_status(
        itemid, metadata, item_server=item_server, item_path=item_path
    )


class ItemEdition(dict):
    """Class to convert item metadata into edition dict."""

    def __init__(self, itemid):
        dict.__init__(self)
        self.itemid = itemid

        timestamp = {"type": "/type/datetime", "value": "2010-01-01T00:00:00"}

        self.update(
            {
                "key": "/books/ia:" + itemid,
                "type": {"key": "/type/edition"},
                "title": itemid,
                "ocaid": itemid,
                "revision": 1,
                "created": timestamp,
                "last_modified": timestamp,
            }
        )

    @classmethod
    def get_item_status(cls, itemid, metadata, item_server=None, item_path=None):
        """Returns the status of the item related to importing it in OL.

        Possible return values are:

        * ok
        * not-texts-item
        * bad-repub-state
        * no-imagecount
        * prefix-blacklisted
        * noindex-true
        * no-ol-import
        """
        # Not a book, or scan not complete or no images uploaded
        if metadata.get("mediatype") != "texts":
            return "not-texts-item"

        if metadata.get("repub_state", "4") not in VALID_READY_REPUB_STATES:
            return "bad-repub-state"

        if "imagecount" not in metadata:
            if not (item_server and item_path):
                return "no-imagecount"
            else:
                manifest = get_item_manifest(itemid, item_server, item_path)
                if not manifest.get('numPages'):
                    return "no-imagecount"

        # items start with these prefixes are not books
        ignore_prefixes = config.get("ia_ignore_prefixes", [])
        for prefix in ignore_prefixes:
            # ignore all JSTOR items
            if itemid.startswith(prefix):
                return "prefix-blacklisted"

        # Anand - Oct 2013
        # If an item is with noindex=true and it is not marked as
        # lending or printdisabled, ignore it.  It would have been
        # marked as noindex=true for some reason.
        collections = metadata.get("collection", [])
        if not isinstance(collections, list):
            collections = [collections]
        if (
            metadata.get("noindex") == "true"
            and "printdisabled" not in collections
            and "inlibrary" not in collections
            and "lendinglibrary" not in collections
        ):
            return "noindex-true"
        # Gio - April 2016
        # items with metadata no_ol_import=true will be not imported
        if metadata.get("no_ol_import", '').lower() == 'true':
            return "no-ol-import"
        return "ok"

    @classmethod
    def is_valid_item(cls, itemid, metadata):
        """Returns True if the item with metadata can be usable as edition
        in Open Library.

        Items that are not book scans, darked or with noindex=true etc. are
        not eligible to be shown in Open Library.
        """
        return cls.get_item_status(itemid, metadata) == 'ok'

    def add_metadata(self, metadata):
        self.metadata = metadata
        self.add('title')
        self.add('description', 'description')
        self.add_list('publisher', 'publishers')
        self.add_list('creator', 'author_names')
        self.add('date', 'publish_date')
        self.add_isbns()

    def add(self, key, key2=None):
        metadata = self.metadata

        key2 = key2 or key
        if key in metadata and metadata[key]:
            value = metadata[key]
            if isinstance(value, list):
                value = [v for v in value if v != {}]
                if value:
                    if isinstance(value[0], str):
                        value = "\n\n".join(value)
                    else:
                        value = value[0]
                else:
                    # empty list. Ignore.
                    return

            self[key2] = value

    def add_list(self, key, key2):
        metadata = self.metadata

        key2 = key2 or key
        if key in metadata and metadata[key]:
            value = metadata[key]
            if not isinstance(value, list):
                value = [value]
            self[key2] = value

    def add_isbns(self):
        isbns = self.metadata.get('isbn')
        isbn_10 = []
        isbn_13 = []
        if isbns:
            for isbn in isbns:
                isbn = isbn.replace("-", "").strip()
                if len(isbn) == 13:
                    isbn_13.append(isbn)
                elif len(isbn) == 10:
                    isbn_10.append(isbn)
        if isbn_10:
            self["isbn_10"] = isbn_10
        if isbn_13:
            self["isbn_13"] = isbn_13


_ia_db = None


def get_ia_db(configfile=None):
    """Metadata API is slow.

    Talk to archive.org database directly if it is specified in the
    global configuration or if a configfile is provided.
    """
    if configfile:
        from openlibrary.config import load_config

        load_config(configfile)

    if not config.get("ia_db"):
        return None
    global _ia_db
    if not _ia_db:
        settings = config.ia_db
        host = settings['host']
        db = settings['db']
        user = settings['user']
        pw = os.popen(settings['pw_file']).read().strip()
        _ia_db = web.database(dbn="postgres", host=host, db=db, user=user, pw=pw)
    return _ia_db


def get_candidate_ocaids(
    since_days=None,
    since_date=None,
    scanned_within_days=60,
    repub_states=None,
    marcs=True,
    custom=None,
    lazy=False,
    count=False,
    db=None,
):
    """Returns a list of identifiers which match the specified criteria
    and are candidates for ImportBot.

    If since_days and since_date are None, no date restrictions are
    applied besides `scanned_within_days` (which may also be None)

    Args:
        since_days (int) - number of days to look back for item updates
        since_date (Datetime) - only completed after since_date
                                (default: if None, since_days used)
        scanned_within_days (int) - only consider items `scanned_within_days`
                                    of `since_date` (default 60 days; 2 months)
        marcs (bool) - require MARCs present?
        lazy (bool) - if True, returns query as iterator, otherwise,
                      returns identifiers list
        count (bool) - if count, return (long) number of matching identifiers
        db (web.db) - A web.py database object with an active
                      connection (optional)

    Usage:
        >>> from openlibrary.core.ia import get_ia_db, get_candidate_ocaids
        >>> candidates = get_candidate_ocaids(
        ...    since_days=1, db=get_ia_db('openlibrary/config/openlibrary.yml'))

    Returns:
        A list of identifiers which are candidates for ImportBot, or
        (if count=True) the number of candidates which would be returned.

    """
    db = db or get_ia_db()
    date = since_date or date_n_days_ago(n=since_days)
    min_scandate = date_n_days_ago(start=date, n=scanned_within_days)
    repub_states = repub_states or VALID_READY_REPUB_STATES

    qvars = {
        'c1': '%opensource%',
        'c2': '%additional_collections%',
        'c3': '%litigationworks%',
    }

    _valid_repub_states_sql = "(%s)" % (', '.join(str(i) for i in repub_states))
    q = (
        "SELECT "
        + ("count(identifier)" if count else "identifier")
        + " FROM metadata"
        + " WHERE repub_state IN "
        + _valid_repub_states_sql
        + "   AND mediatype='texts'"
        + "   AND (noindex IS NULL)"
        + "   AND scancenter IS NOT NULL"
        + "   AND scanner IS NOT NULL"
        + "   AND collection NOT LIKE $c1"
        + "   AND collection NOT LIKE $c2"
        + "   AND collection NOT LIKE $c3"
        + "   AND (curatestate IS NULL OR curatestate NOT IN ('freeze', 'dark'))"
        + "   AND scandate is NOT NULL"
        + "   AND lower(format) LIKE '%%pdf%%'"
    )

    if custom:
        q += custom

    if marcs:
        q += " AND (lower(format) LIKE '%%marc;%%' OR lower(format) LIKE '%%marc')"

    if min_scandate:
        qvars['min_scandate'] = min_scandate.strftime("%Y%m%d")
        q += " AND scandate > $min_scandate"

    if date:
        qvars['date'] = date.isoformat()
        q += " AND updated > $date AND updated < ($date::date + INTERVAL '1' DAY)"

    results = db.query(q, vars=qvars)
    if count:
        return results if lazy else results.list()[0].count
    return results if lazy else [row.identifier for row in results]
