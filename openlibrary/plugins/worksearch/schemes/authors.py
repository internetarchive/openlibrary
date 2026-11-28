import logging
import re
import typing
from datetime import date, datetime, timedelta
from types import MappingProxyType

import luqum.tree

from openlibrary.plugins.worksearch.schemes import SearchScheme
from openlibrary.solr.query_utils import luqum_replace_child, luqum_traverse
from openlibrary.utils.dateutil import format_solr_date

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
            "birth_timestamp",
            "death_timestamp",
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
            "name": "name_sort asc",
            # Birth Date
            # TODO: Switch these to birth_timestamp once a full reindex has populated it
            "birth_date asc": "birth_date asc",
            "birth_date desc": "birth_date desc",
            "birth_timestamp asc": "birth_timestamp asc",
            "birth_timestamp desc": "birth_timestamp desc",
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

    def transform_user_query(self, user_query: str, q_tree: luqum.tree.Item) -> luqum.tree.Item:
        for node, _ in luqum_traverse(q_tree):
            if isinstance(node, luqum.tree.SearchField) and node.name in ("birth_timestamp", "death_timestamp"):
                rewrite_partial_dates_as_solr_ranges(node)
        return q_tree

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


def expand_partial_date_to_solr_range(value: str) -> tuple[str, str] | None:
    """The half-open ``[start, end)`` Solr date range covered by a partial date
    (``1842``, ``1842-05``, ``1842-05-03``), a BC year (``264BC``) or a year
    prefix (``18*``, ``184*``). Returns None for anything else, e.g. a full
    Solr timestamp or ``*``.

    >>> expand_partial_date_to_solr_range("18*")
    ('1800-01-01T00:00:00Z', '1900-01-01T00:00:00Z')
    """
    if m := re.fullmatch(r"(\d{1,4})\s*BCE?", value, re.IGNORECASE):
        year = 1 - int(m.group(1))
        return format_solr_date(year), format_solr_date(year + 1)
    if m := re.fullmatch(r"(\d{1,3})\*", value):
        scale = 10 ** (4 - len(m.group(1)))
        start_year = int(m.group(1)) * scale
        if start_year < 1:
            return None
        end_year = start_year + scale
        return format_solr_date(start_year), format_solr_date(end_year) if end_year <= 9999 else "*"
    if m := re.fullmatch(r"(\d{1,4})(?:-(\d{2})(?:-(\d{2}))?)?", value):
        year = int(m.group(1))
        month, day = (int(g) if g else None for g in m.groups()[1:])
        try:
            start = date(year, month or 1, day or 1)
            if day:
                end = start + timedelta(days=1)
            elif month:
                end = date(year + (month == 12), month % 12 + 1, 1)
            else:
                end = date(year + 1, 1, 1)
        except ValueError, OverflowError:
            return None
        return format_solr_date(start.year, start.month, start.day), format_solr_date(end.year, end.month, end.day)
    return None


def rewrite_partial_dates_as_solr_ranges(sf: luqum.tree.SearchField) -> None:
    """Let users query pdate fields with partial dates, which Solr rejects,
    by rewriting them into timestamp ranges:

    - ``birth_timestamp:1842`` -> ``birth_timestamp:[1842-01-01T00:00:00Z TO 1843-01-01T00:00:00Z}``
    - ``birth_timestamp:18*`` -> ``birth_timestamp:[1800-01-01T00:00:00Z TO 1900-01-01T00:00:00Z}``
    - ``birth_timestamp:[1800 TO 1900]`` -> ``birth_timestamp:[1800-01-01T00:00:00Z TO 1901-01-01T00:00:00Z}``
    - ``birth_timestamp:264BC`` -> ``birth_timestamp:[-0263-01-01T00:00:00Z TO -0262-01-01T00:00:00Z}``

    Negative timestamps can't be written directly, since the query parser
    reads a leading ``-`` as NOT; hence the BC syntax.
    """
    for node, parents in list(luqum_traverse(sf.expr, [sf])):
        parent = parents[-1]
        if isinstance(node, luqum.tree.Range):
            low, high = node.low.value, node.high.value
            include_low, include_high = node.include_low, node.include_high
            if low_range := expand_partial_date_to_solr_range(low):
                # [1800 TO ... starts at 1800; {1800 TO ... starts after it
                low, include_low = low_range[0] if include_low else low_range[1], True
            if high_range := expand_partial_date_to_solr_range(high):
                # ... TO 1900] ends after 1900; ... TO 1900} ends before it
                high, include_high = high_range[1] if include_high else high_range[0], False
            if (low, high) == (node.low.value, node.high.value):
                continue
        elif (
            isinstance(node, (luqum.tree.Word, luqum.tree.Phrase))
            and not isinstance(parent, luqum.tree.Range)
            and (value_range := expand_partial_date_to_solr_range(node.value.strip('"')))
        ):
            (low, high), include_low, include_high = value_range, True, False
        else:
            continue

        # Built directly: re-parsing would choke on BC dates' leading "-"
        new_node = luqum.tree.Range(
            luqum.tree.Word(low, tail=" "),
            luqum.tree.Word(high, head=" "),
            include_low=include_low,
            include_high=include_high,
        )
        new_node.head, new_node.tail = node.head, node.tail
        if getattr(parent, "expr", None) is node:
            parent.expr = new_node
        else:
            luqum_replace_child(parent, node, new_node)
