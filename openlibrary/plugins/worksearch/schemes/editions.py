import logging
from datetime import datetime
from types import MappingProxyType

from openlibrary.plugins.worksearch.schemes import SearchScheme

logger = logging.getLogger("openlibrary.worksearch")

_EDITION_QF = "title^40 alternative_title^20 author_name^20 isbn^10 publisher^5"


class EditionSearchScheme(SearchScheme):
    universe = frozenset(["type:edition"])
    all_fields = frozenset(
        {
            "key",
            "work_key",
            "title",
            "subtitle",
            "alternative_title",
            "alternative_subtitle",
            "cover_i",
            "ebook_access",
            "publish_date",
            "lccn",
            "oclc",
            "ia",
            "ia_collection",
            "isbn",
            "access_score",
            "discovery_score",
            "evaluation_score",
            "usefulness_score",
            "publisher",
            "has_fulltext",
            "title_suggest",
            "publish_year",
            "language",
            "publisher_facet",
            "author_name",
            "author_key",
            "edition_name",
        }
    )
    non_solr_fields = frozenset()
    facet_fields = frozenset()
    field_name_map = MappingProxyType(
        {
            "publishers": "publisher",
        }
    )
    sorts = MappingProxyType(
        {
            "old": "def(publish_year, 9999) asc",
            "new": "publish_year desc",
            "title": "title_sort asc",
            # Ebook access
            "ebook_access": "ebook_access desc",
            "ebook_access asc": "ebook_access asc",
            "ebook_access desc": "ebook_access desc",
            # Key
            "key": "key asc",
            "key asc": "key asc",
            "key desc": "key desc",
            # Quality scores
            "access_score": "access_score desc",
            "access_score asc": "access_score asc",
            "access_score desc": "access_score desc",
            "discovery_score": "discovery_score desc",
            "discovery_score asc": "discovery_score asc",
            "discovery_score desc": "discovery_score desc",
            "evaluation_score": "evaluation_score desc",
            "evaluation_score asc": "evaluation_score asc",
            "evaluation_score desc": "evaluation_score desc",
            "usefulness_score": "usefulness_score desc",
            "usefulness_score asc": "usefulness_score asc",
            "usefulness_score desc": "usefulness_score desc",
            # Random
            "random": "random_1 asc",
            "random asc": "random_1 asc",
            "random desc": "random_1 desc",
            "random.hourly": lambda: f"random_{datetime.now():%Y%m%dT%H} asc",
            "random.daily": lambda: f"random_{datetime.now():%Y%m%d} asc",
        }
    )
    default_fetched_fields = frozenset(
        {
            "key",
            "work_key",
            "title",
            "subtitle",
            "cover_i",
            "ebook_access",
            "publish_date",
            "language",
            "publisher",
            "isbn",
        }
    )
    facet_rewrites = MappingProxyType({})

    def is_search_field(self, field: str):
        return super().is_search_field(field) or field.startswith("id_")

    def q_to_solr_params(self, q, solr_fields, cur_solr_params, highlight=False, solr_internals_params=None):
        return [
            ("q", q),
            ("defType", "edismax"),
            ("qf", _EDITION_QF),
            ("q.op", "AND"),
        ]
