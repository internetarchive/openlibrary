import logging
from typing import Optional, Union
from collections.abc import Callable

import luqum.tree
from luqum.exceptions import ParseError
from openlibrary.solr.query_utils import (
    escape_unknown_fields,
    fully_escape_query,
    luqum_parser,
)

logger = logging.getLogger("openlibrary.worksearch")


class SearchScheme:
    # Set of queries that define the universe of this scheme
    universe: list[str]
    # All actual solr fields that can be in a user query
    all_fields: set[str]
    # These fields are fetched for facets and can also be url params
    facet_fields: set[str]
    # Mapping of user-only fields to solr fields
    field_name_map: dict[str, str]
    # Mapping of user sort to solr sort
    sorts: dict[str, Union[str, Callable[[], str]]]
    # Default
    default_fetched_fields: set[str]
    # Fields that should be rewritten
    facet_rewrites: dict[tuple[str, str], Union[str, Callable[[], str]]]

    def is_search_field(self, field: str):
        return field in self.all_fields or field in self.field_name_map

    def process_user_sort(self, user_sort: str) -> str:
        """
        Convert a user-provided sort to a solr sort

        >>> from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme
        >>> scheme = WorkSearchScheme()
        >>> scheme.process_user_sort('editions')
        'edition_count desc'
        >>> scheme.process_user_sort('editions, new')
        'edition_count desc,first_publish_year desc'
        >>> scheme.process_user_sort('random')
        'random_1 asc'
        >>> scheme.process_user_sort('random_custom_seed')
        'random_custom_seed asc'
        >>> scheme.process_user_sort('random_custom_seed desc')
        'random_custom_seed desc'
        >>> scheme.process_user_sort('random_custom_seed asc')
        'random_custom_seed asc'
        """

        def process_individual_sort(sort: str):
            if sort.startswith('random_'):
                # Allow custom randoms; so anything random_* is allowed
                return sort if ' ' in sort else f'{sort} asc'
            else:
                solr_sort = self.sorts[sort]
                return solr_sort() if callable(solr_sort) else solr_sort

        return ','.join(
            process_individual_sort(s.strip()) for s in user_sort.split(',')
        )

    def process_user_query(self, q_param: str) -> str:
        if q_param == '*:*':
            # This is a special solr syntax; don't process
            return q_param

        try:
            q_param = escape_unknown_fields(
                (
                    # Solr 4+ has support for regexes (eg `key:/foo.*/`)! But for now,
                    # let's not expose that and escape all '/'. Otherwise
                    # `key:/works/OL1W` is interpreted as a regex.
                    q_param.strip()
                    .replace('/', '\\/')
                    # Also escape unexposed lucene features
                    .replace('?', '\\?')
                    .replace('~', '\\~')
                ),
                self.is_search_field,
                lower=True,
            )
            q_tree = luqum_parser(q_param)
        except ParseError:
            # This isn't a syntactically valid lucene query
            logger.warning("Invalid lucene query", exc_info=True)
            # Escape everything we can
            q_tree = luqum_parser(fully_escape_query(q_param))

        q_tree = self.transform_user_query(q_param, q_tree)
        return str(q_tree)

    def transform_user_query(
        self,
        user_query: str,
        q_tree: luqum.tree.Item,
    ) -> luqum.tree.Item:
        return q_tree

    def build_q_from_params(self, params: dict) -> Optional[str]:
        return None

    def q_to_solr_params(
        self,
        q: str,
        solr_fields: set[str],
        cur_solr_params: list[tuple[str, str]],
    ) -> list[tuple[str, str]]:
        return [('q', q)]
