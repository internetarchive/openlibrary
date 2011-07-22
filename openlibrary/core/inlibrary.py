"""Tools for in-library lending.
"""
import web
import cache
from infogami.utils import delegate

def _get_libraries(site=None):
    """Returns all the libraries each as a dict."""
    if 'env' not in web.ctx:
        delegate.fakeload()
    
    site = site or web.ctx.site

    keys = site.things(query={"type": "/type/library", "limit": 1000, "status": "approved"})
    libraries = site.get_many(keys)
    return [lib.dict() for lib in libraries]
    
# cache the result for an hour in memcache
_get_libraries_memoized = cache.memcache_memoize(_get_libraries, "inlibrary._get_libraries", timeout=60*60)

def get_libraries():
    """Returns all the libraries."""
    libraries = _get_libraries_memoized()
    return [web.ctx.site.new(doc['key'], doc) for doc in libraries]

def _get_library(libraries, ip):
    """Returns the library containing the given ip as dict.
    """
    for lib in libraries:
        if lib.has_ip(ip):
            return lib

def get_library():
    """Returns library document if the IP of the current request is in the IP range of that library.
    """
    if "library" not in web.ctx:
        web.ctx.library = _get_library(get_libraries(), web.ctx.ip)
    return web.ctx.library
    
def filter_inlibrary():
    """Returns True if the IP of the current request is in the IP range of one of the libraries.
    """
    return bool(get_library())