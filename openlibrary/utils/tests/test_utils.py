# coding=utf-8
from openlibrary.utils import (
    escape_bracket,
    extract_numeric_id_from_olid,
    finddict,
    str_to_key,
)


def test_str_to_key():
    assert str_to_key('x') == 'x'
    assert str_to_key('X') == 'x'
    assert str_to_key('[X]') == 'x'
    assert str_to_key('!@<X>;:') == '!x'
    assert str_to_key('!@(X);:') == '!(x)'


def test_finddict():
    dicts = [{'x': 1, 'y': 2}, {'x': 3, 'y': 4}]
    assert finddict(dicts, x=1) == {'x': 1, 'y': 2}

def test_escape_bracket():
    assert escape_bracket('test') == 'test'
    assert escape_bracket('this [is a] test') == 'this \\[is a\\] test'
    assert escape_bracket('aaa [10 TO 500] bbb') == 'aaa [10 TO 500] bbb'

def test_extract_numeric_id_from_olid():
    assert extract_numeric_id_from_olid('/works/OL123W') == '123'
    assert extract_numeric_id_from_olid('OL123W') == '123'
