from datetime import datetime
import logging
from collections.abc import Callable

from openlibrary.plugins.worksearch.schemes import SearchScheme

logger = logging.getLogger("openlibrary.worksearch")


class ListSearchScheme(SearchScheme):
    universe = ['type:list']
    all_fields = {  # I have no idea what else to add.
        'key',
        'name',
        'seed',
        'subject',
        'person',
        'place',
        'time',
        'subject_key',
        'person_key',
        'place_key',
        'time_key',
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
        'seed',
        'subject',
        'person',
        'place',
        'time',
        'subject_key',
        'person_key',
        'place_key',
        'time_key',
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
