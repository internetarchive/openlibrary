"""Library for interacting wih archive.org.
"""
from __future__ import print_function
import os
import urllib2
import datetime
from xml.dom import minidom
import simplejson
import web
import logging
from infogami import config
from infogami.utils import stats
import cache
from openlibrary.utils.dateutil import date_n_days_ago

import six


logger = logging.getLogger("openlibrary.ia")

VALID_READY_REPUB_STATES = ["4", "19", "20", "22"]

def get_item_json(itemid):
    itemid = web.safestr(itemid.strip())
    url = 'http://archive.org/metadata/%s' % itemid
    try:
        stats.begin("archive.org", url=url)
        metadata_json = urllib2.urlopen(url).read()
        stats.end()
        return simplejson.loads(metadata_json)
    except IOError:
        stats.end()
        return {}

def extract_item_metadata(item_json):
    metadata = process_metadata_dict(item_json.get("metadata", {}))
    if metadata:
        # if any of the files is access restricted, consider it as
        # an access-restricted item.
        files = item_json.get('files', [])
        metadata['access-restricted'] = any(f.get("private") == "true" for f in files)

        # remember the filenames to construct download links
        metadata['_filenames'] = [f['name'] for f in files]
    return metadata

def get_metadata(itemid):
    item_json = get_item_json(itemid)
    return extract_item_metadata(item_json)

get_metadata = cache.memcache_memoize(get_metadata, key_prefix="ia.get_metadata", timeout=5*60)

def process_metadata_dict(metadata):
    """Process metadata dict to make sure multi-valued fields like
    collection and external-identifier are always lists.

    The metadata API returns a list only if a field has more than one value
    in _meta.xml. This puts burden on the application to handle both list and
    non-list cases. This function makes sure the known multi-valued fields are
    always lists.
    """
    mutlivalued = set(["collection", "external-identifier"])
    def process_item(k, v):
        if k in mutlivalued and not isinstance(v, list):
            v = [v]
        elif k not in mutlivalued and isinstance(v, list):
            v = v[0]
        return (k, v)
    return dict(process_item(k, v) for k, v in metadata.items() if v)

def _old_get_meta_xml(itemid):
    """Returns the contents of meta_xml as JSON.
    """
    itemid = web.safestr(itemid.strip())
    url = 'http://www.archive.org/download/%s/%s_meta.xml' % (itemid, itemid)
    try:
        stats.begin("archive.org", url=url)
        metaxml = urllib2.urlopen(url).read()
        stats.end()
    except IOError:
        logger.error("Failed to download _meta.xml for %s", itemid, exc_info=True)
        stats.end()
        return web.storage()

    # archive.org returns html on internal errors.
    # Checking for valid xml before trying to parse it.
    if not metaxml.strip().startswith("<?xml"):
        return web.storage()

    try:
        defaults = {"collection": [], "external-identifier": []}
        return web.storage(xml2dict(metaxml, **defaults))
    except Exception as e:
        logger.error("Failed to parse metaxml for %s", itemid, exc_info=True)
        return web.storage()

def get_meta_xml(itemid):
    # use metadata API instead of parsing meta xml manually
    return get_metadata(itemid)

def xml2dict(xml, **defaults):
    """Converts xml to python dictionary assuming that the xml is not nested.

    To get some tag as a list/set, pass a keyword argument with list/set as value.

        >>> xml2dict('<doc><x>1</x><x>2</x></doc>')
        {'x': 2}
        >>> xml2dict('<doc><x>1</x><x>2</x></doc>', x=[])
        {'x': [1, 2]}
    """
    d = defaults
    dom = minidom.parseString(xml)

    for node in dom.documentElement.childNodes:
        if node.nodeType == node.TEXT_NODE or len(node.childNodes) == 0:
            continue
        else:
            key = node.tagName
            value = node.childNodes[0].data

            if key in d and isinstance(d[key], list):
                d[key].append(value)
            elif key in d and isinstance(d[key], set):
                d[key].add(value)
            else:
                d[key] = value

    return d

def _get_metadata(itemid):
    """Returns metadata by querying the archive.org metadata API.
    """
    print("_get_metadata", itemid, file=web.debug)
    url = "http://www.archive.org/metadata/%s" % itemid
    try:
        stats.begin("archive.org", url=url)
        text = urllib2.urlopen(url).read()
        stats.end()
        return simplejson.loads(text)
    except (IOError, ValueError):
        return None

# cache the results in memcache for a minute
_get_metadata = web.memoize(_get_metadata, expires=60)

def locate_item(itemid):
    """Returns (hostname, path) for the item.
    """
    d = _get_metadata(itemid)
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

def get_item_manifest(item_id, item_server, item_path):
    url = 'https://%s/BookReader/BookReaderJSON.php' % item_server
    url += "?itemPath=%s&itemId=%s&server=%s" % (item_path, item_id, item_server)
    try:
        stats.begin("archive.org", url=url)
        manifest_json = urllib2.urlopen(url).read()
        stats.end()
        return simplejson.loads(manifest_json)
    except IOError:
        stats.end()
        return {}

def get_item_status(itemid, metadata, **server):
    item_server = server.pop('item_server', None)
    item_path = server.pop('item_path', None)
    return ItemEdition.get_item_status(itemid, metadata, item_server=item_server,
                                       item_path=item_path)

class ItemEdition(dict):
    """Class to convert item metadata into edition dict.
    """
    def __init__(self, itemid):
        dict.__init__(self)
        self.itemid = itemid

        timestamp = {"type": "/type/datetime", "value": "2010-01-01T00:00:00"}
        # if not self._is_valid_item(itemid, metadata):
        #     return None

        self.update({
            "key": "/books/ia:" + itemid,
            "type": {"key": "/type/edition"},
            "title": itemid,
            "ocaid": itemid,
            "revision": 1,
            "created": timestamp,
            "last_modified": timestamp
        })

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
        if metadata.get("noindex") == "true" \
            and "printdisabled" not in collections \
            and "inlibrary" not in collections \
            and "lendinglibrary" not in collections:
            return "noindex-true"
        # Gio - April 2016
        # items with metadata no_ol_import=true will be not imported
        if metadata.get("no_ol_import", '').lower() == 'true':
            return "no-ol-import"

        return "ok"

    @classmethod
    def is_valid_item(cls, itemid, metadata):
        """Returns True if the item with metadata can be useable as edition
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
        self.add_list("creator", "author_names")
        self.add('date', 'publish_date')

        self.add_isbns()
        self.add_subjects()

    def add(self, key, key2=None):
        metadata = self.metadata

        key2 = key2 or key
        # sometimes the empty values are represneted as {} in metadata API. Avoid them.
        if key in metadata and metadata[key] != {}:
            value = metadata[key]
            if isinstance(value, list):
                value = [v for v in value if v != {}]
                if value:
                    if isinstance(value[0], six.string_types):
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
        # sometimes the empty values are represneted as {} in metadata API. Avoid them.
        if key in metadata and metadata[key] != {}:
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

    def add_subjects(self):
        collections = self.metadata.get("collection", [])
        mapping = {
            "inlibrary": "In library",
            "lendinglibrary": "Lending library"
        }
        subjects = [subject for c, subject in mapping.items() if c in collections]
        if subjects:
            self['subjects'] = subjects

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


def get_candidate_ocaids(since_days=None, since_date=None,
                         scanned_within_days=60, repub_states=None,
                         marcs=True, custom=None, lazy=False,
                         count=False, db=None):
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
        'c3': '%printdisabled%'
    }

    _valid_repub_states_sql = "(%s)" % (', '.join(str(i) for i in repub_states))
    q = (
        "SELECT " + ("count(identifier)" if count else "identifier") + " FROM metadata" +
        " WHERE repub_state IN " + _valid_repub_states_sql +
        "   AND mediatype='texts'" +
        "   AND (noindex IS NULL OR collection LIKE $c3)" +
        "   AND scancenter IS NOT NULL" +
        "   AND scanner IS NOT NULL" +
        "   AND collection NOT LIKE $c1" +
        "   AND collection NOT LIKE $c2" +
        "   AND (curatestate IS NULL OR curatestate NOT IN ('freeze', 'dark'))" +
        "   AND scandate is NOT NULL" +
        "   AND lower(format) LIKE '%%pdf%%'"
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
