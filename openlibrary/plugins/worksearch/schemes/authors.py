import logging
from datetime import datetime
from types import MappingProxyType

from openlibrary.plugins.worksearch.schemes import SearchScheme

logger = logging.getLogger("openlibrary.worksearch")


class AuthorSearchScheme(SearchScheme):
    universe = frozenset(['type:author'])
    all_fields = frozenset(
        {
            'key',
            'name',
            'alternate_names',
            'birth_date',
            'death_date',
            'birth_timestamp',
            'death_timestamp',
            'date',
            'top_subjects',
            'work_count',
        }
    )
    non_solr_fields = frozenset()
    facet_fields = frozenset()
    field_name_map = MappingProxyType({})
    sorts = MappingProxyType(
        {
            'work_count desc': 'work_count desc',
            'name': 'name_str asc',
            # Birth Year (legacy, using string field)
            'birth_date asc': 'birth_date asc',
            'birth_date desc': 'birth_date desc',
            # Birth Timestamp (normalized for proper chronological sorting)
            'birth_timestamp asc': 'birth_timestamp asc',
            'birth_timestamp desc': 'birth_timestamp desc',
            # Random
            'random': 'random_1 asc',
            'random asc': 'random_1 asc',
            'random desc': 'random_1 desc',
            'random.hourly': lambda: f'random_{datetime.now():%Y%m%dT%H} asc',
            'random.daily': lambda: f'random_{datetime.now():%Y%m%d} asc',
        }
    )
    default_fetched_fields = frozenset(
        {
            'key',
            'name',
            'birth_date',
            'death_date',
            'birth_timestamp',
            'death_timestamp',
            'date',
            'top_subjects',
            'work_count',
        }
    )
    facet_rewrites = MappingProxyType({})

    def q_to_solr_params(
        self,
        q: str,
        solr_fields: set[str],
        cur_solr_params: list[tuple[str, str]],
        highlight: bool = False,
    ) -> list[tuple[str, str]]:
        return [
            ('q', q),
            ('q.op', 'AND'),
            ('defType', 'edismax'),
            ('qf', 'name alternate_names'),
            ('pf', 'name^10 alternate_names^10'),
            ('bf', 'min(work_count,20)'),
        ]
