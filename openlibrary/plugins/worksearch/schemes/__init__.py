import logging
import typing
from collections.abc import Callable
from types import MappingProxyType

from luqum.exceptions import ParseError

from openlibrary.solr.query_utils import (
    escape_unknown_fields,
    fully_escape_query,
    luqum_parser,
)
from openlibrary.utils.request_context import get_request_lang

if typing.TYPE_CHECKING:
    import luqum.tree

    from openlibrary.fastapi.models import SolrInternalsParams


logger = logging.getLogger("openlibrary.worksearch")


class SearchScheme:
    # Set of queries that define the universe of this scheme
    universe: frozenset[str]
    # All actual solr fields that can be in a user query
    all_fields: frozenset[str]
    # Fields that can be read, but which aren't stored in solr
    non_solr_fields: frozenset[str]
    # These fields are fetched for facets and can also be url params
    facet_fields: frozenset[str]
    # Mapping of user-only fields to solr fields
    field_name_map: MappingProxyType[str, str]
    # Mapping of user sort to solr sort
    sorts: MappingProxyType[str, str | Callable[[], str]]
    # Default
    default_fetched_fields: frozenset[str]
    # Fields that should be rewritten
    facet_rewrites: MappingProxyType[tuple[str, str], str | Callable[[], str]]
    # Language of user
    lang: str

    def __init__(self, lang: str | None = None):
        self.lang = lang or get_request_lang()

    def is_search_field(self, field: str):
        return field in self.all_fields or field in self.field_name_map

    # Sort keys with these prefixes accept an arbitrary custom seed suffix
    # (e.g. ``random_mySeed``), so they are validated by prefix rather than by
    # exact membership in ``sorts``.
    RANDOM_SORT_PREFIXES = ("random_", "random.hourly_", "random.daily_")

    @classmethod
    def validate_user_sort(cls, user_sort: str) -> str:
        """Validate a user-provided sort string without resolving it to a solr sort.

        ``user_sort`` may be a single key, a comma-separated list of keys
        (carousels pass e.g. ``trending,trending_score_hourly_sum``) or a
        ``random_*`` form. Returns ``user_sort`` unchanged when every component
        is valid; raises ``ValueError`` naming the valid options otherwise.

        This backs both the FastAPI request validators and ``process_user_sort``
        so there is a single definition of "valid sort". It mirrors
        ``openlibrary.fastapi.search.create_sort_option_type`` (used for
        author/list/edition search) but additionally accepts the comma-separated
        and ``random_*`` forms that ``process_user_sort`` supports.

        >>> from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme
        >>> WorkSearchScheme.validate_user_sort('new,editions')
        'new,editions'
        >>> WorkSearchScheme.validate_user_sort('bogus')  # doctest: +ELLIPSIS
        Traceback (most recent call last):
            ...
        ValueError: Invalid sort option: 'bogus'. Valid options are: editions, ...
        """
        for part in user_sort.split(","):
            sort = part.strip()
            # Empty components (a trailing/doubled comma, or whitespace-only input)
            # carry no sort and are skipped here — process_user_sort skips them too,
            # so they resolve to "no sort" rather than a 500. The two MUST agree on
            # empties: if one skips and the other does not, `self.sorts[""]` raises
            # KeyError. Non-empty unknown keys are rejected.
            if not sort or sort in cls.sorts or sort.startswith(cls.RANDOM_SORT_PREFIXES):
                continue
            valid = ", ".join((*cls.sorts.keys(), *cls.RANDOM_SORT_PREFIXES))
            raise ValueError(f"Invalid sort option: '{sort}'. Valid options are: {valid}")
        return user_sort

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
        'random_1_custom_seed asc'
        >>> scheme.process_user_sort('random_custom_seed desc')
        'random_1_custom_seed desc'
        >>> scheme.process_user_sort('random_custom_seed asc')
        'random_1_custom_seed asc'
        """
        # Reject unknown sorts with a clear ValueError naming the valid options,
        # rather than letting the ``self.sorts[...]`` lookups below raise a bare
        # KeyError (which surfaces to the user as an opaque 500). After this call
        # every non-empty component below is guaranteed to be a valid key.
        self.validate_user_sort(user_sort)

        def process_individual_sort(sort: str) -> str:
            if sort.startswith(("random_", "random.hourly_", "random.daily_")):
                # Allow custom randoms; so anything random_* is allowed
                # Also Allow custom time randoms to allow carousels with overlapping
                # books to have a fresh ordering when on the same collection
                sort_order: str | None = None
                if " " in sort:
                    sort, sort_order = sort.split(" ", 1)
                random_type, random_seed = sort.split("_", 1)
                solr_sort = self.sorts[random_type]
                solr_sort_str = solr_sort() if callable(solr_sort) else solr_sort
                solr_sort_field, solr_sort_order = solr_sort_str.split(" ", 1)
                sort_order = sort_order or solr_sort_order
                return f"{solr_sort_field}_{random_seed} {sort_order}"
            else:
                solr_sort = self.sorts[sort]
                return solr_sort() if callable(solr_sort) else solr_sort

        # Skip empty components (trailing/doubled commas, whitespace-only) so
        # ``self.sorts[""]`` is never reached — consistent with validate_user_sort.
        return ",".join(process_individual_sort(s.strip()) for s in user_sort.split(",") if s.strip())

    def process_user_query(self, q_param: str) -> str:
        if q_param == "*:*":
            # This is a special solr syntax; don't process
            return q_param

        try:
            q_param = escape_unknown_fields(
                (
                    # Solr 4+ has support for regexes (eg `key:/foo.*/`)! But for now,
                    # let's not expose that and escape all '/'. Otherwise
                    # `key:/works/OL1W` is interpreted as a regex.
                    q_param.strip()
                    .replace("/", "\\/")
                    # Also escape unexposed lucene features
                    .replace("?", "\\?")
                    .replace("~", "\\~")
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

    def build_q_from_params(self, params: dict) -> str | None:
        return None

    def q_to_solr_params(
        self,
        q: str,
        solr_fields: set[str],
        cur_solr_params: list[tuple[str, str]],
        highlight: bool = False,
        solr_internals_params: SolrInternalsParams | None = None,
    ) -> list[tuple[str, str]]:
        return [("q", q)]

    def add_non_solr_fields(self, solr_fields: set[str], solr_result: dict) -> None:
        raise NotImplementedError
