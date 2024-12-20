from openlibrary.utils import (
    extract_numeric_id_from_olid,
    str_to_key,
)


def test_str_to_key():
    assert str_to_key('x') == 'x'
    assert str_to_key('X') == 'x'
    assert str_to_key('[X]') == 'x'
    assert str_to_key('!@<X>;:') == '!x'
    assert str_to_key('!@(X);:') == '!(x)'


def test_extract_numeric_id_from_olid():
    assert extract_numeric_id_from_olid('/works/OL123W') == '123'
    assert extract_numeric_id_from_olid('OL123W') == '123'
