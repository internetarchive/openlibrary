import logging
from collections.abc import Callable
from datetime import datetime
from typing import ClassVar

from openlibrary.plugins.worksearch.schemes import SearchScheme

logger = logging.getLogger("openlibrary.worksearch")


class AuthorSearchScheme(SearchScheme):
    universe: ClassVar[list[str]] = ['type:author']
    all_fields: ClassVar[set[str]] = {
        'key',
        'name',
        'alternate_names',
        'birth_date',
        'death_date',
        'date',
        'top_subjects',
        'work_count',
    }
    non_solr_fields: ClassVar[set[str]] = set()
    facet_fields: ClassVar[set[str]] = set()
    field_name_map: ClassVar[dict[str, str]] = {}
    sorts: ClassVar[dict[str, str | Callable[[], str]]] = {
        'work_count desc': 'work_count desc',
        # Random
        'random': 'random_1 asc',
        'random asc': 'random_1 asc',
        'random desc': 'random_1 desc',
        'random.hourly': lambda: f'random_{datetime.now():%Y%m%dT%H} asc',
        'random.daily': lambda: f'random_{datetime.now():%Y%m%d} asc',
    }
    default_fetched_fields: ClassVar[set[str]] = {  # Annotated with ClassVar
        'key',
        'name',
        'birth_date',
        'death_date',
        'date',
        'top_subjects',
        'work_count',
    }
    facet_rewrites: ClassVar[dict[tuple[str, str], str | Callable[[], str]]] = {
        ('public_scan', 'true'): 'ebook_access:public'
    }  # Annotated with ClassVar

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
