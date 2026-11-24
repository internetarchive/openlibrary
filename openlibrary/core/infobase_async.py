"""Async, read-only access to Infobase's tables, for hot read paths.

Infobase (``site.get()``) stays the only writer, and handles every read this module
doesn't. A typed ``site.get().things()`` call runs synchronously on the event loop and
does a lot of work before its one indexed query: two in-process JSON round trips and
about two memcache lookups per property of the type (#14078). ``things()`` here runs
the same query against the same tables, awaited, with the type schema and ids looked
up once per process.
"""

import functools
import json
import re
from typing import Any

from openlibrary.core.async_db import fetch_all, fetch_val
from openlibrary.core.schema import get_schema


class UnsupportedQuery(ValueError):
    """``things()`` only does exact matches on indexed properties of one type;
    use ``site.get().things()`` for anything else."""


# Infobase's datatype for a property's expected type (``readquery.find_datatype``).
_EXPECTED_TYPE_DATATYPES = {
    "/type/string": "str",
    "/type/int": "int",
    "/type/float": "float",
    "/type/boolean": "boolean",
    "/type/datetime": "datetime",
}
# A plain property name: no operators (``title~``), nesting (``works.key``) or labels (``a:title``).
_PLAIN_NAME = re.compile(r"[a-z_][a-z0-9_]*")
# Columns of the ``thing`` table rather than indexed properties.
_THING_COLUMNS = {"key", "created", "last_modified"}

# Types and properties almost never change, so these are looked up once per process.
_type_ids: dict[str, int] = {}
_type_datatypes: dict[str, dict[str, str]] = {}  # type key -> property name -> datatype
_property_ids: dict[tuple[int, str], int] = {}


@functools.cache
def _schema():
    return get_schema()


async def _type_id(type_key: str) -> int | None:
    if type_key not in _type_ids:
        if (type_id := await fetch_val("SELECT id FROM thing WHERE key = %(key)s", {"key": type_key})) is None:
            return None
        _type_ids[type_key] = type_id
    return _type_ids[type_key]


async def _datatypes(type_key: str) -> dict[str, str]:
    """Each property's datatype, from the type's latest revision."""
    if type_key not in _type_datatypes:
        data = await fetch_val(
            "SELECT d.data FROM thing t JOIN data d ON d.thing_id = t.id AND d.revision = t.latest_revision WHERE t.key = %(key)s",
            {"key": type_key},
        )
        datatypes = {}
        for prop in json.loads(data).get("properties", []) if data else []:
            expected = prop.get("expected_type")
            expected_key = expected.get("key") if isinstance(expected, dict) else expected
            datatypes[prop["name"]] = _EXPECTED_TYPE_DATATYPES.get(expected_key or "", "ref")
        _type_datatypes[type_key] = datatypes
    return _type_datatypes[type_key]


async def _property_id(type_id: int, name: str) -> int | None:
    if (type_id, name) not in _property_ids:
        if (property_id := await fetch_val("SELECT id FROM property WHERE type = %(type)s AND name = %(name)s", {"type": type_id, "name": name})) is None:
            return None
        _property_ids[type_id, name] = property_id
    return _property_ids[type_id, name]


def _value_datatype(value: Any, datatypes: dict[str, str], name: str) -> str:
    # Same order as readquery.find_datatype: the value's own type, then the schema,
    # then "str" for a property the type doesn't declare (e.g. OL's ``isbn_`` index).
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    return datatypes.get(name, "str")


async def things(query: dict[str, Any]) -> list[str]:
    """Keys of the things matching ``query``, like ``site.get().things(query)``.

    Supports ``{"type": T, name: value, ..., "limit": n}``: exact matches on indexed
    properties of one type. Raises ``UnsupportedQuery`` for anything else.
    """
    conditions = dict(query)
    type_key = conditions.pop("type", None)
    try:
        limit = min(int(conditions.pop("limit", 20)), 1000)
    except TypeError, ValueError:
        raise UnsupportedQuery(query) from None  # Infobase falls back to its default limit
    if not isinstance(type_key, str) or not conditions:
        raise UnsupportedQuery(query)

    if (type_id := await _type_id(type_key)) is None:
        return []
    datatypes = await _datatypes(type_key)

    tables = ["thing"]
    wheres = ["thing.type = %(type_id)s"]
    params: dict[str, Any] = {"type_id": type_id, "limit": limit}
    for i, (name, value) in enumerate(conditions.items()):
        if name in _THING_COLUMNS or not _PLAIN_NAME.fullmatch(name) or value is None or isinstance(value, (list, dict)):
            raise UnsupportedQuery(query)
        datatype = _value_datatype(value, datatypes, name)
        # Table names come from Open Library's schema, never from the query.
        if (table := _schema().find_table(type_key, datatype, name)) is None:
            raise UnsupportedQuery(query)
        if (key_id := await _property_id(type_id, name)) is None:
            return []  # no thing has ever had this property
        if datatype == "ref" and (value := await fetch_val("SELECT id FROM thing WHERE key = %(key)s", {"key": value})) is None:
            return []
        tables.append(f"{table} AS d{i}")
        wheres += [f"d{i}.thing_id = thing.id", f"d{i}.key_id = %(key_id{i})s", f"d{i}.value = %(value{i})s"]
        params |= {f"key_id{i}": key_id, f"value{i}": value}

    rows = await fetch_all(f"SELECT thing.key FROM {', '.join(tables)} WHERE {' AND '.join(wheres)} LIMIT %(limit)s", params)
    return [row["key"] for row in rows]
