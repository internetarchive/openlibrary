# coding=utf-8
from openlibrary.utils import str_to_key, read_isbn, url_quote, finddict, escape_bracket

def test_isbn():
    assert read_isbn('x') is None
    assert read_isbn('1841151866') == '1841151866'
    assert read_isbn('184115186x') == '184115186x'
    assert read_isbn('184115186X') == '184115186X'
    assert read_isbn('184-115-1866') == '1841151866'
    assert read_isbn('9781841151861') == '9781841151861'
    assert read_isbn('978-1841151861') == '9781841151861'

def test_str_to_key():
    assert str_to_key('x') == 'x'
    assert str_to_key('X') == 'x'
    assert str_to_key('[X]') == 'x'
    assert str_to_key('!@<X>;:') == '!x'
    assert str_to_key('!@(X);:') == '!(x)'

def test_url_quote():
    assert url_quote('x') == 'x'
    result = url_quote(u'£20') 
    assert result == '%C2%A320'
    assert url_quote('test string') == 'test+string'

def test_finddict():
    dicts = [{"x": 1, "y": 2}, {"x": 3, "y": 4}]
    assert finddict(dicts, x=1) == {'x': 1, 'y': 2}

def test_escape_bracket():
    assert escape_bracket('test') == 'test'
    assert escape_bracket('this [is a] test') == 'this \\[is a\\] test'
    assert escape_bracket('aaa [10 TO 500] bbb') == 'aaa [10 TO 500] bbb'

