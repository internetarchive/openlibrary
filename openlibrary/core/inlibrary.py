"""Tools for in-library lending.
"""
import web
import cache
import iprange
from infogami.utils import delegate

def _get_libraries(site=None):
    """Returns all the libraries each as a dict."""
    if 'env' not in web.ctx:
        delegate.fakeload()
    
    site = site or web.ctx.site

    keys = site.things(query={"type": "/type/library", "limit": 1000, "status": "approved"})
    libraries = site.get_many(sorted(keys))
    return [lib.dict() for lib in libraries]

# cache the result for an hour in memcache
_get_libraries_memoized = cache.memcache_memoize(_get_libraries, "inlibrary._get_libraries", timeout=60*60)

@cache.memoize(engine="memcache", key=lambda: "inlibrary.libraries-hash")
def _get_libraries_hash():
    """Returns a hash of libraries. When any one of the libraries is modified, the hash changes.
    """
    libraries = _get_libraries_memoized()
    return hash(",".join("%s@%s" % (x['key'], x['revision']) for x in libraries))

_ip_dict = None
_libraries_hash = None

def _get_ip_dict():
    """Returns an :class:`iprange.IPDict` instance with mapping from ips to library keys.
    """
    global _ip_dict, _libraries_hash
    # Use the library-hash to decide whether or not the value need to be recomputed.
    h = _get_libraries_hash()
    if _libraries_hash != h:
        _libraries_hash = h
        _ip_dict = _make_ip_dict()
    return _ip_dict

def _make_ip_dict():
    libraries = _get_libraries_memoized()
    d = iprange.IPDict()
    for lib in libraries:
        # ip_ranges will be of the form {"type": "/type/text", "value": "foo"}
        ip_ranges = lib.get("ip_ranges", "")
        if isinstance(ip_ranges, dict):
            ip_ranges = ip_ranges['value']
        if ip_ranges:
            d.add_ip_range_text(ip_ranges, lib)
    return d    
    
def get_libraries():
    """Returns all the libraries."""
    libraries = _get_libraries_memoized()
    libraries = [web.ctx.site.new(doc['key'], doc) for doc in libraries]
    return libraries

def get_library():
    """Returns library document if the IP of the current request is in the IP range of that library.
    """
    if "library" not in web.ctx:
        d = _get_ip_range_mapping()
        lib = d.get(web.ctx.ip)
        web.ctx.library = lib and web.ctx.site.new(lib['key'], lib)
    return web.ctx.library
    
def filter_inlibrary():
    """Returns True if the IP of the current request is in the IP range of one of the libraries.
    """
    return bool(get_library())