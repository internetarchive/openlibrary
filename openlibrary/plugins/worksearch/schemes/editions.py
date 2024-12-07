import logging
from datetime import datetime

from openlibrary.plugins.worksearch.schemes import SearchScheme

logger = logging.getLogger("openlibrary.worksearch")


# Kind of mostly a stub for now since you can't really search editions
# directly, but it's still useful for somethings (eg editions have a custom
# sort logic).
class EditionSearchScheme(SearchScheme):
    universe = ['type:work']
    all_fields = {
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
    }
    facet_fields: set[str] = set()
    field_name_map = {
        'publishers': 'publisher',
        'subtitle': 'alternative_subtitle',
        'title': 'alternative_title',
        # "Private" fields
        # This is private because we'll change it to a multi-valued field instead of a
        # plain string at the next opportunity, which will make it much more usable.
        '_ia_collection': 'ia_collection_s',
    }
    sorts = {
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
    default_fetched_fields: set[str] = set()
    facet_rewrites = {}

    def is_search_field(self, field: str):
        return super().is_search_field(field) or field.startswith('id_')
