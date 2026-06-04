from __future__ import annotations
import logging
import typing
from datetime import datetime
from types import MappingProxyType

from openlibrary.plugins.worksearch.schemes import SearchScheme
from openlibrary.solr.utils import get_solr_next

if typing.TYPE_CHECKING:
    from openlibrary.fastapi.models import SolrInternalsParams

logger = logging.getLogger("openlibrary.worksearch")


class AuthorSearchScheme(SearchScheme):
    universe = frozenset(["type:author"])
    all_fields = frozenset(
        {
            "key",
            "name",
            "alternate_names",
            "birth_date",
            "death_date",
            "date",
            "top_subjects",
            "work_count",
        }
    )
    non_solr_fields = frozenset()
    facet_fields = frozenset()
    field_name_map = MappingProxyType({})
    sorts = MappingProxyType(
        {
            "work_count desc": "work_count desc",
            # TODO: fallback can be removed after reindex is complete
            # NOTE: Lambda needed here, since get_solr_next reads in the openlibrary.yml
            # at import-time, resulting in side-effects that cause unit tests to fail
            "name": lambda: "name_sort asc" if get_solr_next() else "name_str asc",
            # Birth Year
            "birth_date asc": "birth_date asc",
            "birth_date desc": "birth_date desc",
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
            "name",
            "birth_date",
            "death_date",
            "date",
            "top_subjects",
            "work_count",
        }
    )
    facet_rewrites = MappingProxyType({})

    def q_to_solr_params(
        self,
        q: str,
        solr_fields: set[str],
        cur_solr_params: list[tuple[str, str]],
        highlight: bool = False,
        solr_internals_params: SolrInternalsParams | None = None,
    ) -> list[tuple[str, str]]:
        return [
            ("q", q),
            ("q.op", "AND"),
            ("defType", "edismax"),
            ("qf", "name alternate_names"),
            ("pf", "name^10 alternate_names^10"),
            ("bf", "min(work_count,20)"),
        ]
