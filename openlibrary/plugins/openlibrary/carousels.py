"""Methods for carousels"""

from infogami.infobase.client import storify
from infogami.utils.view import public

from openlibrary.core.ia import IAEditionSearch
from openlibrary.core import cache

@public
def get_editions_by_ia_query(query='', sorts=None, page=1, limit=None,
                             timeout=cache.DEFAULT_CACHE_LIFETIME):
    def editions_by_ia_query(query='', sorts=None, page=1, limit=None):
        # Enable method to be cacheable
        if 'env' not in web.ctx:
            delegate.fakeload()
        editions = IAEditionSearch.get(query=query, sorts=sorts, page=page, limit=limit)
        return editions

    results = cache.memcache_memoize(
        editions_by_ia_query, 'editions.search_ia', timeout=timeout)(
            query=query, sorts=sorts, page=page, limit=limit)
    return storify(results)
