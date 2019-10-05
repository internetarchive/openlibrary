from ..isbn import isbn_10_to_isbn_13, isbn_13_to_isbn_10, \
    normalize_isbn, opposite_isbn

def test_isbn_13_to_isbn_10():
    assert isbn_13_to_isbn_10('978-0-940787-08-7') == '0940787083'
    assert isbn_13_to_isbn_10('9780940787087') == '0940787083'
    assert isbn_13_to_isbn_10('BAD-ISBN') is None

def test_isbn_10_to_isbn_13():
    assert isbn_10_to_isbn_13('0-940787-08-3') == '9780940787087'
    assert isbn_10_to_isbn_13('0940787083') == '9780940787087'
    assert isbn_10_to_isbn_13('BAD-ISBN') is None

def test_opposite_isbn():
    assert opposite_isbn('0-940787-08-3') == '9780940787087'
    assert opposite_isbn('978-0-940787-08-7') == '0940787083'
    assert opposite_isbn('BAD-ISBN') is None

def test_normalize_isbn():
    assert normalize_isbn('a') is None
    assert normalize_isbn('1841151866') == '1841151866'
    assert normalize_isbn('184115186x') == '184115186X'
    assert normalize_isbn('184115186X') == '184115186X'
    assert normalize_isbn('184-115-1866') == '1841151866'
    assert normalize_isbn('9781841151861') == '9781841151861'
    assert normalize_isbn('978-1841151861') == '9781841151861'
