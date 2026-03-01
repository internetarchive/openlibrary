import logging
from datetime import datetime
from types import MappingProxyType

from openlibrary.plugins.worksearch.schemes import SearchScheme

logger = logging.getLogger("openlibrary.worksearch")


# Kind of mostly a stub for now since you can't really search editions
# directly, but it's still useful for somethings (eg editions have a custom
# sort logic).
class EditionSearchScheme(SearchScheme):
    universe = frozenset(['type:work'])
    all_fields = frozenset(
        {
            "key",
            "title",
            "subtitle",
            "alternative_title",
            "alternative_subtitle",
            "cover_i",
            "ebook_access",
            "publish_date",
            "lccn",
            "ia",
            "ia_collection",
            "isbn",
            "metadata_score",
            "usefulness_score",
            "publisher",
            "has_fulltext",
            "title_suggest",
            "publish_year",
            "language",
            "publisher_facet",
        }
    )
    non_solr_fields = frozenset()
    facet_fields = frozenset()
    field_name_map = MappingProxyType(
        {
            'publishers': 'publisher',
            'subtitle': 'alternative_subtitle',
            'title': 'alternative_title',
        }
    )
    sorts = MappingProxyType(
        {
            'old': 'def(publish_year, 9999) asc',
            'new': 'publish_year desc',
            'title': 'title_sort asc',
            # Ebook access
            'ebook_access': 'ebook_access desc',
            'ebook_access asc': 'ebook_access asc',
            'ebook_access desc': 'ebook_access desc',
            # Key
            'key': 'key asc',
            'key asc': 'key asc',
            'key desc': 'key desc',
            # Quality scores
            'metadata_score': 'metadata_score desc',
            'metadata_score asc': 'metadata_score asc',
            'metadata_score desc': 'metadata_score desc',
            'usefulness_score': 'usefulness_score desc',
            'usefulness_score asc': 'usefulness_score asc',
            'usefulness_score desc': 'usefulness_score desc',
            # Random
            'random': 'random_1 asc',
            'random asc': 'random_1 asc',
            'random desc': 'random_1 desc',
            'random.hourly': lambda: f'random_{datetime.now():%Y%m%dT%H} asc',
            'random.daily': lambda: f'random_{datetime.now():%Y%m%d} asc',
        }
    )
    default_fetched_fields = frozenset()
    facet_rewrites = MappingProxyType({})

    def is_search_field(self, field: str):
        return super().is_search_field(field) or field.startswith('id_')
