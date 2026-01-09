# See https://github.com/internetarchive/openlibrary/pull/10283#issuecomment-2940908216

import logging
from datetime import datetime
from types import MappingProxyType

from openlibrary.plugins.worksearch.schemes import SearchScheme

logger = logging.getLogger("openlibrary.worksearch")


# define a search scheme for lists, similar to SubjectSearchScheme
class ListSearchScheme(SearchScheme):
    # this search only applies to list type documents
    universe = frozenset(['type:list OR list_type:*'])
    all_fields = frozenset(
        {
            'key',  # unique identifier for the list
            'name',  # name/title of the list
            'seed',
            'subject',
            'subject_key',
            'person',
            'person_key',
            'place',
            'place_key',
            'time',
            'time_key',
            'last_modified',
            'seed_count',
        }
    )

    # short description of the list
    non_solr_fields = frozenset({'description'})

    facet_fields = frozenset()
    field_name_map = MappingProxyType({})
    sorts = MappingProxyType(
        {
            'name asc': 'name asc',
            'last_modified': 'last_modified desc',
            'last_modified asc': 'last_modified asc',
            'last_modified desc': 'last_modified desc',
            'seed_count': 'seed_count desc',
            'seed_count asc': 'seed_count asc',
            'seed_count desc': 'seed_count desc',
            # Random (kept from SubjectSearchScheme)
            'random': 'random_1 asc',
            'random asc': 'random_1 asc',
            'random desc': 'random_1 desc',
            'random.hourly': lambda: f'random_{datetime.now():%Y%m%dT%H} asc',
            'random.daily': lambda: f'random_{datetime.now():%Y%m%d} asc',
        }
    )
    default_fetched_fields = frozenset({'key', 'name'})

    facet_rewrites = MappingProxyType({})

    # converts user search query into a Solr-compatible query
    def q_to_solr_params(
        self,
        q: str,
        solr_fields: set[str],
        cur_solr_params: list[tuple[str, str]],
        highlight: bool = False,
    ) -> list[tuple[str, str]]:
        return [
            ('q', q),  # actual query string
            ('q.op', 'AND'),  # use 'AND" for matching multiple words in search queries
            ('defType', 'edismax'),  # use edismax parser for better full-text search
        ]
