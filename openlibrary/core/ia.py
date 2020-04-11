"""Library for interacting with archive.org.
"""

import logging
import requests
import simplejson
import six
import os
import web

from infogami import config
from infogami.utils import stats

from openlibrary.core import cache
from openlibrary.core import helpers as h
from openlibrary.utils.dateutil import date_n_days_ago
from six.moves.urllib.parse import urlencode


logger = logging.getLogger('openlibrary.ia')

IA_BASE_URL = config.get('ia_base_url')
VALID_READY_REPUB_STATES = ['4', '19', '20', '22']


class IAEditionSearch:
    """
    Enables one to query archive.org editions, and return OL editions w availability.
    """

    MAX_EDITIONS_LIMIT = 20
    AVAILABILITY_STATUS = 'loans__status__status'
    VALID_SORTS = [
        '__random', '__sort', 'addeddate', 'avg_rating',
        'call_number', 'createdate', 'creatorSorter',
        'creatorSorterRaw', 'date', 'downloads', 'foldoutcount',
        'headerImage', 'identifier', 'identifierSorter', 'imagecount',
        'indexdate', 'item_size', 'languageSorter', 'licenseurl',
        'mediatype', 'mediatypeSorter', 'month', 'nav_order',
        'num_reviews', 'programSorter', 'publicdate', 'reviewdate',
        'stars', 'titleSorter', 'titleSorterRaw', 'week', 'year',
        'loans__status__last_loan_date'
    ]

    PRESET_QUERIES = {
        'preset:thrillers': (
            'creator:('
            ' "Clancy, Tom" OR "King, Stephen" OR "Clive Cussler" OR '
            ' "Cussler, Clive" OR "Dean Koontz" OR "Koontz, Dean" OR '
            ' "Higgins, Jack"'
            ') AND '
            '!publisher:"Pleasantville, N.Y. : Reader\'s Digest Association" AND '
            'languageSorter:"English"'
        ),
        'preset:children': (
            'creator:('
            ' "parish, Peggy" OR "avi" OR "Dahl, Roald" OR "ahlberg, allan" OR '
            ' "Seuss, Dr" OR "Carle, Eric" OR "Pilkey, Dav"'
            ') OR title:"goosebumps"'
        ),
        'preset:comics': (
            'subject:"comics" OR '
            'creator:('
            ' "Gary Larson" OR "Larson, Gary" OR "Charles M Schulz" OR '
            ' "Schulz, Charles M" OR "Jim Davis" OR "Davis, Jim" OR '
            ' "Bill Watterson" OR "Watterson, Bill" OR "Lee, Stan"'
            ')'
        ),
        'preset:authorsalliance_mitpress': (
            '(!loans__status__status:UNAVAILABLE) AND ('
            ' openlibrary_subject:("authorsalliance" OR "mitpress") OR '
            ' collection:(mitpress) OR publisher:(MIT Press)'
            ')'
        )
    }

    @classmethod
    def get(cls, query='', sorts=None, page=1, limit=None):
        """This method allows Open Library to fetch editions from its catalog
        by using the Archive.org Advanced Search as the querying
        mechanism. This is advantageous because Archive.org has the
        latest book availability information.
        Retrieves a list of available editions (one per work) on Open
        Library using the archive.org advancedsearch API. Is used in such
        components as IABookCarousel to retrieve a list of unique
        available books.
        :param str query: an elasticsearch archive.org  advancedsearch query
        :param list sorts: a list of ES strs for sorting
        :param page int: which page to start on
        :param limit int: limit results per page (default cls.MAX_EDITIONS_LIMIT)
        :rtype: list of dict representation of editions
        """
        from openlibrary.core.models import Edition
        q = cls._expand_api_query(query)
        sorts = cls._normalize_sorts(sorts)
        params = cls._clean_params(q=q, sorts=sorts, page=page, limit=limit)
        url = cls._compose_advancedsearch_url(**params)
        response = cls._request(url)
        items = response.get('docs', [])
        item_index = cls._index_items_by_ocaid(items)
        editions = web.ctx.site.get_many([
            '/books/%s' % item['openlibrary_edition']
            for item in item_index.values()
        ])
        canonical_editions = [
            Edition.canonicalize(
                cls._add_availability_to_edition(edition, item_index)
            ).dict() for edition in editions
        ]

        return {
            'editions': canonical_editions,
            'advancedsearch_url': url,
            'browse_url': cls._compose_browsable_url(q, sorts),
            'params': params
        }

    @classmethod
    def _normalize_sorts(cls, sorts):
        """_request requires sorts to be a list of valid sort options.
        Discard invalid sorts and marshal to list.
        XXX broken for encoding of + -> %2B in +ASC, +DESC
        :rtype: list of str
        """
        if sorts:
            # If it's a string, split and turn to list
            if isinstance(sorts, six.string_types):
                sorts = sorts.split(',')
            if isinstance(sorts, list):
                # compare against field with +asc/desc suffix rm'd
                # e.g: date, not date+asc or date+desc
                return [
                    sort.replace('+', ' ') for sort in sorts
                    if sort.split('+')[0] in cls.VALID_SORTS
                ]

    @classmethod
    def _expand_api_query(cls, query):
        """Expands short / more easily cacheable preset queries
        and fixes query to ensure only text archive.org items
        are returned having openlibrary_work
        :param str query: preset query or regular IA query
        :rtype: str
        """
        # Expand preset queries
        if query in cls.PRESET_QUERIES:
            query = cls.PRESET_QUERIES[query]

        q = 'mediatype:texts AND !noindex:* AND openlibrary_work:(*)'
        # Add availability if none present (e.g. borrowable only)
        if cls.AVAILABILITY_STATUS not in query:
            q += ' AND %s:AVAILABLE' % cls.AVAILABILITY_STATUS
        return q if not query else q + " AND " + query

    @classmethod
    def _clean_params(cls, q='', sorts=None, page=1, limit=None):
        """
        Adds defaults and constructs params dict
        :param str q:
        :param Optional[List[str]]sorts:
        :param int page:
        :param int|None limit:
        :rtype: dict
        """
        _limit = limit or cls.MAX_EDITIONS_LIMIT
        return {
            'q': q,
            'page': page,
            'rows': min(_limit, cls.MAX_EDITIONS_LIMIT),
            'sort[]': sorts or '',
            'fl[]': [
                'identifier', cls.AVAILABILITY_STATUS, 'openlibrary_edition',
                'openlibrary_work'
            ],
            'output': 'json'
        }

    @classmethod
    def _compose_advancedsearch_url(cls, **params):
        # We need this to be http, so that we see the urls being called in the logs
        # internally for rate limiting
        return 'http://%s/advancedsearch.php?%s' % (
            h.bookreader_host() or 'archive.org', urlencode(params, doseq=True))

    @classmethod
    def _compose_browsable_url(cls, query, sorts=None):
        """If the client wants to explore this query in the browser, it will
        have to be converted to a human readable version of the advancedsearch API
        :param str query:
        :param list of str sorts:
        :rtype: str
        :return: a url for humans to view this query on archive.org
        """
        _sort = sorts[0] if sorts else ''
        if ' desc' in _sort:
            _sort = '-' + _sort.split(' ')[0]
        elif ' asc' in _sort:
            _sort = _sort.split(' ')[0]
        return '%s/search.php?%s' % (
            h.ia_domain(), urlencode({'query': query, 'sort': _sort}))

    @classmethod
    def _request(cls, url):
        """
        Hits archive.org advancedsearch.php API, returns matching items
        :param str url:
        :rtype: dict
        :return: the `response` content of the advancesearch
        """
        try:
            # TODO switch to requests
            request = six.moves.urllib.request.Request(url)
            # Internet Archive Elastic Search (which powers some of our
            # carousel queries) needs Open Library to forward user IPs so
            # we can attribute requests to end-users
            client_ip = web.ctx.env.get('HTTP_X_FORWARDED_FOR', 'ol-internal')
            request.add_header('x-client-id', client_ip)
            response = six.moves.urllib.request.urlopen(
                request, timeout=h.http_request_timeout()).read()
            return simplejson.loads(response).get('response', {})
        except Exception:  # TODO make more specific
            logger.error("IAEditionSearch._request error", exc_info=True)
            return []

    @classmethod
    def _add_availability_to_edition(cls, edition, item_index):
        """
        To avoid a 2nd network call to `lending.add_availability` reconstruct
        availability info ad-hoc from archive.org advancedsearch results
        :param Edition edition:
        :param dict item_index: mapping ocaid -> metadata item
        :rtype: Edition
        :return: edition, modified to include availability
        """
        item = item_index[edition.ocaid]
        availability_status = (
            ('borrow_%s' % item[cls.AVAILABILITY_STATUS].lower())
            if item.get(cls.AVAILABILITY_STATUS) else 'open')
        edition['availability'] = {
            'status': availability_status,
            'identifier': item.get('identifier', ''),
            'openlibrary_edition': item.get('openlibrary_edition', ''),
            'openlibrary_work': item.get('openlibrary_work', '')
        }
        return edition

    @staticmethod
    def _index_items_by_ocaid(items):
        return dict((item['identifier'], item) for item in items)



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
            logger.info('%s response received from %s' % (r.status_code, url))
    except Exception as e:
        logger.exception('Exception occurred accessing %s.' % url)
    stats.end()
    return api_response


def get_metadata_direct(itemid, only_metadata=True, cache=True):
    """
    Fetches metadata by querying the archive.org metadata API, without local cacheing.
    :param str itemid:
    :param bool cache: if false, requests uncached metadata from archive.org
    :param bool only_metadata: whether to get the metadata without any processing
    :rtype: dict
    """
    url = '%s/metadata/%s' % (IA_BASE_URL, web.safestr(itemid.strip()))
    params = {}
    if cache:
        params['dontcache'] = 1
    full_json = get_api_response(url, params)
    return extract_item_metadata(full_json) if only_metadata else full_json

get_metadata = cache.memcache_memoize(get_metadata_direct, key_prefix='ia.get_metadata', timeout=5 * cache.MINUTE_SECS)


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
    multivalued = set(['collection', 'external-identifier', 'isbn', 'subject', 'oclc-id'])
    def process_item(k, v):
        if k in multivalued and not isinstance(v, list):
            v = [v]
        elif k not in multivalued and isinstance(v, list):
            v = v[0]
        return (k, v)
    return dict(process_item(k, v) for k, v in metadata.items() if v)


def locate_item(itemid):
    """Returns (hostname, path) for the item.
    """
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
    """Gets the URL of the archive.org item's title (or cover) page.
    """
    base_url = '{0}/download/{1}/page/'.format(IA_BASE_URL, item_id)
    title_response = requests.head(base_url + 'title.jpg', allow_redirects=True)
    if title_response.status_code == 404:
        return base_url + 'cover.jpg'
    return base_url + 'title.jpg'


def get_item_manifest(item_id, item_server, item_path):
    url = 'https://%s/BookReader/BookReaderJSON.php' % item_server
    url += '?itemPath=%s&itemId=%s&server=%s' % (item_path, item_id, item_server)
    return get_api_response(url)


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
