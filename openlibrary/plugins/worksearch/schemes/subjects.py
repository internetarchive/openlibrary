import logging
import typing
from datetime import datetime
from types import MappingProxyType

from openlibrary.plugins.worksearch.schemes import SearchScheme

if typing.TYPE_CHECKING:
    from openlibrary.fastapi.models import SolrInternalsParams

logger = logging.getLogger("openlibrary.worksearch")


class SubjectSearchScheme(SearchScheme):
    universe = frozenset(['type:subject'])
    all_fields = frozenset(
        {
            'key',
            'name',
            'subject_type',
            'work_count',
        }
    )
    non_solr_fields = frozenset()
    facet_fields = frozenset()
    field_name_map = MappingProxyType({})
    sorts = MappingProxyType(
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
    default_fetched_fields = frozenset(
        {
            'key',
            'name',
            'subject_type',
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
        solr_internals_params: 'SolrInternalsParams | None' = None,
    ) -> list[tuple[str, str]]:
        return [
            ('q', q),
            ('q.op', 'AND'),
            ('defType', 'edismax'),
        ]
