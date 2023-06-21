import unittest
import datetime
import re
from openlibrary.api import unmarshal


class Text(str):
    def __repr__(self):
        return "<text: %s>" % str.__repr__(self)


class Reference(str):
    def __repr__(self):
        return "<ref: %s>" % str.__repr__(self)


def parse_datetime(value):
    """Parses ISO datetime formatted string.::

    >>> parse_datetime("2009-01-02T03:04:05.006789")
    datetime.datetime(2009, 1, 2, 3, 4, 5, 6789)
    """
    if isinstance(value, datetime.datetime):
        return value
    else:
        tokens = re.split(r'-|T|:|\.| ', value)
        return datetime.datetime(*map(int, tokens))


class UnmarshalTest(unittest.TestCase):
    def test_CT1_unmarshal_list(self):
        input_data = [
            {"type": "/type/text", "value": "hello, world"},
            {"type": "/type/datetime", "value": "2009-01-02T03:04:05.006789"},
        ]
        expected_output = [
            Text("hello, world"),
            parse_datetime("2009-01-02T03:04:05.006789"),
        ]
        self.assertEqual(unmarshal(input_data), expected_output)

    def test_CT2_unmarshal_dict_with_key(self):
        input_data = {"value": "hello, world", "type": "/type/text"}
        expected_output = Text("hello, world")
        self.assertEqual(unmarshal(input_data), expected_output)

    def test_CT3_unmarshal_dict_with_value_and_type(self):
        input_data = {"value": "hello, world", "type": "/type/text"}
        expected_output = Text("hello, world")
        self.assertEqual(unmarshal(input_data), expected_output)

    def test_CT4_unmarshal_dict_with_value_and_type_datetime(self):
        input_data = {"value": "2009-01-02T03:04:05.006789", "type": "/type/datetime"}
        expected_output = parse_datetime("2009-01-02T03:04:05.006789")
        self.assertEqual(unmarshal(input_data), expected_output)

    def test_CT5_unmarshal_dict_with_no_key_or_value(self):
        input_data = {}
        expected_output = {}
        self.assertEqual(unmarshal(input_data), expected_output)

    def test_CT6_unmarshal_dict_with_no_type_or_key(self):
        input_data = {"value": "hello, world"}
        expected_output = input_data
        self.assertEqual(unmarshal(input_data), expected_output)

    def test_CT7_unmarshal_dict_with_complex_data(self):
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
        self.assertEqual(unmarshal(input_data), expected_output)

    def test_CT8_unmarshal_list_with_invalid_type(self):
        input_data = [{"type": "/type/invalid", "value": "hello, world"}]
        expected_output = ["hello, world"]
        self.assertEqual(unmarshal(input_data), expected_output)

    def test_CT9_unmarshal_dict_with_invalid_type(self):
        input_data = {"type": "/type/invalid", "value": "hello, world"}
        expected_output = "hello, world"
        self.assertEqual(unmarshal(input_data), expected_output)

    def test_CT10_unmarshal_dict_with_empty_value(self):
        input_data = {"value": "", "type": "/type/text"}
        expected_output = ""
        self.assertEqual(unmarshal(input_data), expected_output)

    def test_CT11_unmarshal_dict_with_empty_dict(self):
        input_data = {}
        expected_output = {}

        self.assertEqual(unmarshal(input_data), expected_output)
