import logging
from datetime import datetime

from openlibrary.plugins.worksearch.schemes import SearchScheme

logger = logging.getLogger("openlibrary.worksearch")


class AuthorSearchScheme(SearchScheme):
    def __init__(self):
        super().__init__()
        self._universe = {'type:author'}
        self._all_fields = {
            'key',
            'name',
            'alternate_names',
            'birth_date',
            'death_date',
            'date',
            'top_subjects',
            'work_count',
        }
        self._non_solr_fields = set()
        self._facet_fields = set()
        self._field_name_map = {}
        self._sorts = {
            'work_count desc': 'work_count desc',
            # Random
            'random': 'random_1 asc',
            'random asc': 'random_1 asc',
            'random desc': 'random_1 desc',
            'random.hourly': lambda: f'random_{datetime.now():%Y%m%dT%H} asc',
            'random.daily': lambda: f'random_{datetime.now():%Y%m%d} asc',
        }
        self._default_fetched_fields = {
            'key',
            'name',
            'birth_date',
            'death_date',
            'date',
            'top_subjects',
            'work_count',
        }
        self._facet_rewrites = {}

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
