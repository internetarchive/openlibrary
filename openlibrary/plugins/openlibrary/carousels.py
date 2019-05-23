"""Methods for carousels"""

import web
import random

from infogami.infobase.client import storify
from infogami.utils import delegate
from infogami.utils.view import public

from openlibrary.core import search
from openlibrary.core import cache
from openlibrary.plugins.worksearch.search import random_readable_works
from openlibrary.utils import dateutil

@public
def get_editions_by_ia_query(query='', sorts=None, page=1, limit=None,
                             timeout=cache.DEFAULT_CACHE_LIFETIME):
    results = cache.memcache_memoize(
        search.editions_by_ia_query, 'editions.search_ia', timeout=timeout)(
            query=query, sorts=sorts, page=page, limit=limit)
    return storify(results)

@public
def cached_random_readable_works():
    # cache 2k classic works in memcache for 15 minutes
    works = cache.memcache_memoize(
        random_readable_works, "carousel.classics",
        timeout=15*dateutil.MINUTE_SECS)() or []
    return storify(
        random.sample(works, 60) if len(works) > 60 else works
    )


def setup():
    pass
