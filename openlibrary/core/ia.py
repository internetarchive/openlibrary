"""Library for interacting with archive.org."""

import datetime
import logging
from urllib.parse import urlencode

import requests
import web

from infogami import config
from infogami.utils import stats
from openlibrary.core import cache

logger = logging.getLogger('openlibrary.ia')

# FIXME: We can't reference `config` in module scope like this; it will always be undefined!
# See lending.py for an example of how to do it correctly.
IA_BASE_URL = config.get('ia_base_url', 'https://archive.org')
VALID_READY_REPUB_STATES = ['4', '19', '20', '22']


def get_api_response(url: str, params: dict | None = None) -> dict:
    """
    Makes an API GET request to archive.org, collects stats
    Returns a JSON dict.
    :param dict params: url parameters
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
        logger.exception(f'Exception occurred accessing {url}.')
    stats.end()
    return api_response


def get_metadata_direct(
    itemid: str, only_metadata: bool = True, cache: bool = True
) -> dict:
    """
    Fetches metadata by querying the archive.org metadata API, without local caching.
    :param bool cache: if false, requests uncached metadata from archive.org
    :param bool only_metadata: whether to get the metadata without any processing
    """
    url = f'{IA_BASE_URL}/metadata/{web.safestr(itemid.strip())}'
    params = {}
    if cache is False:
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
    url = f'https://{item_server}/BookReader/BookReaderJSON.php'
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
        if value := metadata.get('key'):
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
        if value := metadata.get('key'):
            if not isinstance(value, list):
                value = [value]
            self[key2] = value

    def add_isbns(self):
        isbn_10 = []
        isbn_13 = []
        if isbns := self.metadata.get('isbn'):
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


def get_candidates_url(
    day: datetime.date,
    marcs: bool = True,
) -> str:
    DAY = datetime.timedelta(days=1)
    hard_requirements = ' AND '.join(
        [
            "mediatype:texts",
            f'indexdate:{day}*',
            '!collection:litigationworks',
            '!is_dark:true',
            # Fetch back to items added before the day of interest, since items
            # sometimes take a few days to process into the collection.
            f'addeddate:[{day - 60 * DAY} TO {day + 1 * DAY}]',
        ]
    )
    repub_states = ' OR '.join(
        f'repub_state:{state}' for state in VALID_READY_REPUB_STATES
    )
    soft_requirements = ' AND '.join(
        [
            f'({repub_states})',
            'scanningcenter:*',
            'scanner:*',
            'scandate:*',
            'format:pdf',
            # TODO: format:marc seems to be getting more records than expected
            *(['format:marc'] if marcs else []),
            '!collection:opensource',
            '!collection:additional_collections',
            '!noindex:true',
        ]
    )
    exempt_collections = ' OR '.join(  # noqa: FLY002
        ["collection:thoth-archiving-network"]
    )
    params = {
        'q': f'({hard_requirements}) AND (({soft_requirements}) OR ({exempt_collections}))',
        'fl': 'identifier,format',
        'service': 'metadata__unlimited',
        'rows': '100000',  # This is the max, I believe
        'output': 'json',
    }

    return f'{IA_BASE_URL}/advancedsearch.php?' + urlencode(params)


def get_candidate_ocaids(
    day: datetime.date,
    marcs: bool = True,
):
    """
    Returns a list of identifiers that were finalized on the provided
    day, which may need to be imported into Open Library.

    :param day: only find items modified on this given day
    :param marcs: require MARCs present?
    """
    url = get_candidates_url(day, marcs=marcs)
    results = requests.get(url).json()['response']['docs']
    assert len(results) < 100_000, f'100,000 results returned for {day}'

    for row in results:
        if marcs:
            # Exclude MARC Source since this doesn't contain the actual MARC data
            formats = {fmt.lower() for fmt in row.get('format', [])}
            if not formats & {'marc', 'marc binary'}:
                continue
        yield row['identifier']
