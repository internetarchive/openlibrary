"""Library for interacting wih archive.org.
"""
import urllib2
from xml.dom import minidom
import simplejson
import web
import logging
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
