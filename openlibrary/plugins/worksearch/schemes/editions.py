import logging
from collections.abc import Mapping
from datetime import datetime
<<<<<<< HEAD
from typing import Mapping, Set, ClassVar
=======
>>>>>>> b1f51bc5c04c4193af189da4c2ea474fb3c334fd
from types import MappingProxyType

from openlibrary.plugins.worksearch.schemes import SearchScheme

logger = logging.getLogger("openlibrary.worksearch")


# Kind of mostly a stub for now since you can't really search editions
# directly, but it's still useful for somethings (eg editions have a custom
# sort logic).
class EditionSearchScheme(SearchScheme):
    # Keep instance variables without overriding with ClassVar
<<<<<<< HEAD
    universe = frozenset(['type:work'])
    all_fields = frozenset([
=======
    universe = 'type:work'
    all_fields = frozenset(
>>>>>>> b1f51bc5c04c4193af189da4c2ea474fb3c334fd
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
        "isbn",
        "publisher",
        "has_fulltext",
        "title_suggest",
        "publish_year",
        "language",
        "publisher_facet",
<<<<<<< HEAD
    ])
    facet_fields: ClassVar[set[str]] = frozenset()
    field_name_map: ClassVar[dict[str, str]] = dict(MappingProxyType({
        'publishers': 'publisher',
        'subtitle': 'alternative_subtitle',
        'title': 'alternative_title',
        # "Private" fields
        # This is private because we'll change it to a multi-valued field instead of a
        # plain string at the next opportunity, which will make it much more usable.
        '_ia_collection': 'ia_collection_s',
    }))
    sorts:ClassVar[dict[str, str]] = dict(MappingProxyType({
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
        # Random
        'random': 'random_1 asc',
        'random asc': 'random_1 asc',
        'random desc': 'random_1 desc',
        'random.hourly': lambda: f'random_{datetime.now():%Y%m%dT%H} asc',
        'random.daily': lambda: f'random_{datetime.now():%Y%m%d} asc',
    }))
    default_fetched_fields: ClassVar[frozenset]= frozenset()
    facet_rewrites: ClassVar[dict[tuple[str, str], str]]= {} 
=======
    )
    facet_fields: set[str] = frozenset()
    field_name_map: Mapping[str, str] = MappingProxyType(
        {
            'publishers': 'publisher',
            'subtitle': 'alternative_subtitle',
            'title': 'alternative_title',
            # "Private" fields
            # This is private because we'll change it to a multi-valued field instead of a
            # plain string at the next opportunity, which will make it much more usable.
            '_ia_collection': 'ia_collection_s',
        }
    )
    sorts: Mapping[str, str] = MappingProxyType(
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
            # Random
            'random': 'random_1 asc',
            'random asc': 'random_1 asc',
            'random desc': 'random_1 desc',
            'random.hourly': lambda: f'random_{datetime.now():%Y%m%dT%H} asc',
            'random.daily': lambda: f'random_{datetime.now():%Y%m%d} asc',
        }
    )
    default_fetched_fields: set[str] = frozenset()
    facet_rewrites: Mapping[tuple[str, str], str] = MappingProxyType({})
>>>>>>> b1f51bc5c04c4193af189da4c2ea474fb3c334fd

    def is_search_field(self, field: str):
        return super().is_search_field(field) or field.startswith('id_')
