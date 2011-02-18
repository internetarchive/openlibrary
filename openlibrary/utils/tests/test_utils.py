from openlibrary.utils import str_to_key, read_isbn, url_quote

def test_isbn():
    assert read_isbn('x') is None
    assert read_isbn('1841151866') == '1841151866'
    assert read_isbn('184115186x') == '184115186x'
    assert read_isbn('184115186X') == '184115186X'
    assert read_isbn('184-115-1866') == '1841151866'
    assert read_isbn('9781841151861') == '9781841151861'
    assert read_isbn('978-1841151861') == '9781841151861'
