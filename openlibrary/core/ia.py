"""Library for interacting wih archive.org.
"""
import urllib2
from xml.dom import minidom
import simplejson
import web
import logging
from infogami import config
from infogami.utils import stats
import cache

logger = logging.getLogger("openlibrary.ia")

def get_metadata(itemid):
    itemid = web.safestr(itemid.strip())
    url = 'http://archive.org/metadata/%s' % itemid
    try:
        stats.begin("archive.org", url=url)
        metadata_json = urllib2.urlopen(url).read()
        stats.end()
        d = simplejson.loads(metadata_json)
        metadata = process_metadata_dict(d.get("metadata", {}))

        if metadata:
            # if any of the files is access restricted, consider it as an access-restricted item.
            files = d.get('files', [])
            metadata['access-restricted'] = any(f.get("private") == "true" for f in files)

            # remember the filenames to construct download links
            metadata['_filenames'] = [f['name'] for f in files]
        return metadata
    except IOError:
        stats.end()
        return {}

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
    except Exception, e:
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
    print >> web.debug, "_get_metadata", itemid
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

def get_item_status(itemid, metadata):
    return ItemEdition.get_item_status(itemid, metadata)

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
    def get_item_status(cls, itemid, metadata):
        """Returns the status of the item related to importing it in OL.

        Possible return values are:

        * ok
        * not-texts-item
        * bad-repub-state
        * no-imagecount
        * prefix-blacklisted
        * noindex-true
        """
        # Not a book, or scan not complete or no images uploaded
        if metadata.get("mediatype") != "texts":
            return "not-texts-item"

        if metadata.get("repub_state", "4") not in ["4", "6"]:
            return "bad-repub-state"

        if "imagecount" not in metadata:
            return "no-imagecount"

        # items start with these prefixes are not books
        ignore_prefixes = config.get("ia_ignore_prefixes", [])
        for prefix in ignore_prefixes:
            # ignore all JSTOR items
            if itemid.startswith(prefix):
                return "prefix-blacklisted"

        # Anand - Oct 2013
        # If an item is with noindex=true and it is not marked as lending or printdisabled, ignore it.
        # It would have been marked as noindex=true for some reason.
        collections = metadata.get("collection", [])
        if not isinstance(collections, list):
            collections = [collections]
        if metadata.get("noindex") == "true" \
            and "printdisabled" not in collections \
            and "inlibrary" not in collections \
            and "lendinglibrary" not in collections:
            return "noindex-true"

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
                    if isinstance(value[0], basestring):
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
