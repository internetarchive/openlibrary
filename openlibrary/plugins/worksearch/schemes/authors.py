from datetime import datetime
import logging

from openlibrary.plugins.worksearch.schemes import SearchScheme

logger = logging.getLogger("openlibrary.worksearch")


class AuthorSearchScheme(SearchScheme):
    universe = ['type:author']
    all_fields = {
        'key',
        'name',
        'alternate_names',
        'birth_date',
        'death_date',
        'date',
        'top_subjects',
        'work_count',
    }
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
        'birth_date',
        'death_date',
        'date',
        'top_subjects',
        'work_count',
    }
    facet_rewrites: dict[tuple[str, str], str] = {}

    def q_to_solr_params(self, q: str, solr_fields: set[str]) -> list[tuple[str, str]]:
        return [
            ('q', q),
            ('q.op', 'AND'),
            ('defType', 'edismax'),
            ('qf', 'name alternate_names'),
        ]
