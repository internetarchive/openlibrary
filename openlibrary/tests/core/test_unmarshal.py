from datetime import datetime
import re

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


def test_ct1_unmarshal_list():
    input_data = [
        {"type": "/type/text", "value": "hello, world"},
        {"type": "/type/datetime", "value": "2009-01-02T03:04:05.006789"},
    ]
    expected_output = [
        Text("hello, world"),
        parse_datetime("2009-01-02T03:04:05.006789"),
    ]
    assert unmarshal(input_data) == expected_output


def test_ct2_unmarshal_dict_with_key():
    input_data = {"value": "hello, world", "type": "/type/text"}
    expected_output = Text("hello, world")
    assert unmarshal(input_data) == expected_output


def test_ct3_unmarshal_dict_with_value_and_type():
    input_data = {"value": "hello, world", "type": "/type/text"}
    expected_output = Text("hello, world")
    assert unmarshal(input_data) == expected_output


def test_ct4_unmarshal_dict_with_value_and_type_datetime():
    input_data = {"value": "2009-01-02T03:04:05.006789", "type": "/type/datetime"}
    expected_output = parse_datetime("2009-01-02T03:04:05.006789")
    assert unmarshal(input_data) == expected_output


def test_ct5_unmarshal_dict_with_no_key_or_value():
    input_data = {}
    expected_output = {}
    assert unmarshal(input_data) == expected_output


def test_ct6_unmarshal_dict_with_no_type_or_key():
    input_data = {"value": "hello, world"}
    expected_output = input_data
    assert unmarshal(input_data) == expected_output


def test_ct7_unmarshal_dict_with_complex_data():
    input_data = {
        "key1": "value1",
        "key2": {"value2": "value2", "type": "/type/text"},
        "key3": "2009-01-02T03:04:05.006789",
    }
    expected_output = {
        "key1": "value1",
        "key2": {"value2": "value2", "type": "/type/text"},
        "key3": "2009-01-02T03:04:05.006789",
    }
    assert unmarshal(input_data) == expected_output


def test_ct8_unmarshal_list_with_invalid_type():
    input_data = [{"type": "/type/invalid", "value": "hello, world"}]
    expected_output = ["hello, world"]
    assert unmarshal(input_data) == expected_output


def test_ct9_unmarshal_dict_with_invalid_type():
    input_data = {"type": "/type/invalid", "value": "hello, world"}
    expected_output = "hello, world"
    assert unmarshal(input_data) == expected_output


def test_ct10_unmarshal_dict_with_empty_value():
    input_data = {"value": "", "type": "/type/text"}
    expected_output = ""
    assert unmarshal(input_data) == expected_output


def test_ct11_unmarshal_dict_with_empty_dict():
    input_data = {}
    expected_output = {}
    assert unmarshal(input_data) == expected_output
