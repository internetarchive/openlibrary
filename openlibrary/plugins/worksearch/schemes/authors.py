import logging
from collections.abc import Callable
from datetime import datetime
from types import MappingProxyType

from openlibrary.plugins.worksearch.schemes import SearchScheme

logger = logging.getLogger("openlibrary.worksearch")


class AuthorSearchScheme(SearchScheme):
    universe: frozenset[str] = frozenset(['type:author'])
    all_fields: frozenset[str] = frozenset(
        {
            'key',
            'name',
            'alternate_names',
            'birth_date',
            'death_date',
            'date',
            'top_subjects',
            'work_count',
        }
    )
    non_solr_fields: frozenset[str]
    facet_fields: frozenset[str]
    field_name_map: MappingProxyType[str, str]
    sorts: MappingProxyType[str, str | Callable[[], str]] = MappingProxyType(
        {
            'work_count desc': 'work_count desc',
            # Random
            'random': 'random_1 asc',
            'random asc': 'random_1 asc',
            'random desc': 'random_1 desc',
            'random.hourly': lambda: f'random_{datetime.now():%Y%m%dT%H} asc',
            'random.daily': lambda: f'random_{datetime.now():%Y%m%d} asc',
        }
    )
    default_fetched_fields: frozenset[str] = frozenset(
        {
            'key',
            'name',
            'birth_date',
            'death_date',
            'date',
            'top_subjects',
            'work_count',
        }
    )
    facet_rewrites: MappingProxyType[tuple[str, str], str | Callable[[], str]]

    def q_to_solr_params(
        self,
        q: str,
        solr_fields: set[str],
        cur_solr_params: list[tuple[str, str]],
    ) -> list[tuple[str, str]]:
        return [
            ('q', q),
            ('q.op', 'AND'),
            ('defType', 'edismax'),
            ('qf', 'name alternate_names'),
            ('pf', 'name^10 alternate_names^10'),
            ('bf', 'min(work_count,20)'),
        ]
