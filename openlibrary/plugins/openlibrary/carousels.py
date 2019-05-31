"""Methods for carousels"""

from infogami.infobase.client import storify
from infogami.utils.view import public

from openlibrary.core import search
from openlibrary.core import cache

@public
def get_editions_by_ia_query(query='', sorts=None, page=1, limit=None,
                             timeout=cache.DEFAULT_CACHE_LIFETIME):
    results = cache.memcache_memoize(
        search.editions_by_ia_query, 'editions.search_ia', timeout=timeout)(
            query=query, sorts=sorts, page=page, limit=limit)
    return storify(results)

def setup():
    pass
