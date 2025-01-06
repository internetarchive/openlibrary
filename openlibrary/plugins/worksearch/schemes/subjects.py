import logging
from datetime import datetime
from typing import ClassVar, Dict, Set, Callable, List, Tuple

from openlibrary.plugins.worksearch.schemes import SearchScheme

logger = logging.getLogger("openlibrary.worksearch")


class SubjectSearchScheme(SearchScheme):
    universe: ClassVar[list[str]] = ['type:subject']
    all_fields: ClassVar[set[str]] = {
        'key',
        'name',
        'subject_type',
        'work_count',
    }
    non_solr_fields: ClassVar[set[str]] = set()
    facet_fields: ClassVar[set[str]] = set()
    field_name_map: ClassVar[dict[str,str]] = {}
    sorts: ClassVar[Dict[str, str | Callable[[], str]]]= {
        'work_count desc': 'work_count desc',
        # Random
        'random': 'random_1 asc',
        'random asc': 'random_1 asc',
        'random desc': 'random_1 desc',
        'random.hourly': lambda: f'random_{datetime.now():%Y%m%dT%H} asc',
        'random.daily': lambda: f'random_{datetime.now():%Y%m%d} asc',
    }
    default_fetched_fields: ClassVar[set[str]] = {
        'key',
        'name',
        'subject_type',
        'work_count',
    }
    facet_rewrites: ClassVar[Dict[tuple[str, str], str | Callable[[], str]]] = {
        ('public_scan', 'true'): 'ebook_access:public'
    }

    def q_to_solr_params(
        self,
        q: str,
        solr_fields: set[str],
        cur_solr_params: list[tuple[str, str]]
    ) -> List[tuple[str, str]]:
        return [
            ('q', q),
            ('q.op', 'AND'),
            ('defType', 'edismax'),
        ]
