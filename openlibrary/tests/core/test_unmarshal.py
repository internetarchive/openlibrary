import re
from datetime import datetime

import pytest

from openlibrary.api import unmarshal


class Text(str):
    __slots__ = ()

    def __repr__(self):
        return "<text: %s>" % str.__repr__(self)


class Reference(str):
    __slots__ = ()

    def __repr__(self):
        return "<ref: %s>" % str.__repr__(self)


def parse_datetime(value: datetime | str) -> datetime:
    """Parses ISO datetime formatted string.::

    >>> parse_datetime("2009-01-02T03:04:05.006789")
    datetime.datetime(2009, 1, 2, 3, 4, 5, 6789)
    """
    if isinstance(value, datetime):
        return value
    tokens = re.split(r'-|T|:|\.| ', value)
    return datetime(*(int(token) for token in tokens))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({}, {}),
        ({"value": "", "type": "/type/text"}, ""),
        ({"value": "hello, world"}, {"value": "hello, world"}),
        ({"value": "hello, world", "type": "/type/text"}, Text("hello, world")),
        ({"type": "/type/invalid", "value": "hello, world"}, "hello, world"),
        ([{"type": "/type/invalid", "value": "hello, world"}], ["hello, world"]),
        (
            {"value": "2009-01-02T03:04:05.006789", "type": "/type/datetime"},
            parse_datetime("2009-01-02T03:04:05.006789"),
        ),
        (
            [
                {"type": "/type/text", "value": "hello, world"},
                {"type": "/type/datetime", "value": "2009-01-02T03:04:05.006789"},
            ],
            [
                Text("hello, world"),
                parse_datetime("2009-01-02T03:04:05.006789"),
            ],
        ),
        (
            {
                "key1": "value1",
                "key2": {"value2": "value2", "type": "/type/text"},
                "key3": "2009-01-02T03:04:05.006789",
            },
            {
                "key1": "value1",
                "key2": {"value2": "value2", "type": "/type/text"},
                "key3": "2009-01-02T03:04:05.006789",
            },
        ),
    ],
)
def test_unmarshal(data, expected) -> None:
    assert unmarshal(data) == expected
