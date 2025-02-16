import logging
from collections.abc import Callable
from datetime import datetime

from openlibrary.plugins.worksearch.schemes import SearchScheme

logger = logging.getLogger("openlibrary.worksearch")


class SubjectSearchScheme(SearchScheme):
    universe = ['type:subject']
    all_fields = {
        'key',
        'name',
        'subject_type',
        'work_count',
    }
    non_solr_fields: set[str] = set()
    facet_fields: set[str] = set()
    field_name_map: dict[str, str] = {}
    sorts = {
        'work_count desc': 'work_count desc',
        # Random
        'random': 'random_1 asc',
        'random asc': 'random_1 asc',
        'random desc': 'random_1 desc',
        'random.hourly': lambda: f'random_{datetime.now():%Y%m%dT%H} asc',
        'random.daily': lambda: f'random_{datetime.now():%Y%m%d} asc',
    }
    default_fetched_fields = {
        'key',
        'name',
        'subject_type',
        'work_count',
    }
    facet_rewrites: dict[tuple[str, str], str | Callable[[], str]] = {}

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
        ]
