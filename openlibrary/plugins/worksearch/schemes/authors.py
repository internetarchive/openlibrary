import logging
import re
import typing
from datetime import date, datetime, timedelta
from types import MappingProxyType

import luqum.tree

from openlibrary.plugins.worksearch.schemes import SearchScheme
from openlibrary.solr.query_utils import luqum_replace_child, luqum_traverse

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
            if isinstance(node, luqum.tree.SearchField) and node.name in DATE_FIELDS:
                date_transform(node)
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


DATE_FIELDS = frozenset({"birth_timestamp", "death_timestamp"})
_PARTIAL_DATE_RE = re.compile(r"(\d{1,4})(?:-(\d{2})(?:-(\d{2}))?)?")
_YEAR_PREFIX_RE = re.compile(r"(\d{1,3})\*")
_BC_YEAR_RE = re.compile(r"(\d{1,4})\s*BCE?", re.IGNORECASE)


def _solr_year(year: int) -> str:
    """Start of ``year`` in ISO 8601 astronomical numbering (1 BC = 0000)."""
    return f"{'-' if year < 0 else ''}{abs(year):04d}-01-01T00:00:00Z"


def _solr_date(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}-{d.day:02d}T00:00:00Z"


def partial_date_bounds(value: str) -> tuple[str, str] | None:
    """The half-open ``[start, end)`` Solr date range covered by a partial date
    (``1842``, ``1842-05``, ``1842-05-03``), a BC year (``264BC``) or a year
    prefix (``18*``, ``184*``).
    Returns None for anything else, e.g. a full Solr timestamp or ``*``.

    >>> partial_date_bounds("18*")
    ('1800-01-01T00:00:00Z', '1900-01-01T00:00:00Z')
    """
    if m := _BC_YEAR_RE.fullmatch(value):
        year = 1 - int(m.group(1))
        return _solr_year(year), _solr_year(year + 1)
    if m := _YEAR_PREFIX_RE.fullmatch(value):
        scale = 10 ** (4 - len(m.group(1)))
        start_year = int(m.group(1)) * scale
        if start_year < 1:
            return None
        end_year = start_year + scale
        return _solr_year(start_year), _solr_year(end_year) if end_year <= 9999 else "*"
    if m := _PARTIAL_DATE_RE.fullmatch(value):
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
        return _solr_date(start), _solr_date(end)
    return None


def _date_range_node(low: str, high: str, include_low: bool, include_high: bool) -> luqum.tree.Range:
    # Built directly: re-parsing would choke on BC dates' leading "-"
    return luqum.tree.Range(
        luqum.tree.Word(low, tail=" "),
        luqum.tree.Word(high, head=" "),
        include_low=include_low,
        include_high=include_high,
    )


def _transform_date_value(val: luqum.tree.Item) -> luqum.tree.Item | None:
    if isinstance(val, luqum.tree.Range):
        low, high = val.low.value, val.high.value
        include_low, include_high = val.include_low, val.include_high
        if low_bounds := partial_date_bounds(low):
            # [1800 TO ... starts at 1800; {1800 TO ... starts after it
            low, include_low = low_bounds[0] if include_low else low_bounds[1], True
        if high_bounds := partial_date_bounds(high):
            # ... TO 1900] ends after 1900; ... TO 1900} ends before it
            high, include_high = high_bounds[1] if include_high else high_bounds[0], False
        if (low, high) == (val.low.value, val.high.value):
            return None
        return _date_range_node(low, high, include_low, include_high)
    if isinstance(val, (luqum.tree.Word, luqum.tree.Phrase)) and (bounds := partial_date_bounds(val.value.strip('"'))):
        return _date_range_node(*bounds, include_low=True, include_high=False)
    return None


def date_transform(sf: luqum.tree.SearchField) -> None:
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
        if isinstance(parent, luqum.tree.Range):
            continue  # handled with the Range itself
        if (new_node := _transform_date_value(node)) is None:
            continue
        new_node.head, new_node.tail = node.head, node.tail
        if getattr(parent, "expr", None) is node:
            parent.expr = new_node
        else:
            luqum_replace_child(parent, node, new_node)
