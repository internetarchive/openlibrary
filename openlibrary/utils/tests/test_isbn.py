from .. import isbn

def test_isbn_13_to_isbn_10():
    assert isbn.isbn_13_to_isbn_10("978-0-940787-08-7") == "0940787083"
    assert isbn.isbn_13_to_isbn_10("9780940787087") == "0940787083"
    assert isbn.isbn_13_to_isbn_10("BAD-ISBN") is None

def test_isbn_10_to_isbn_13():
    assert isbn.isbn_10_to_isbn_13("0-940787-08-3") == "9780940787087"
    assert isbn.isbn_10_to_isbn_13("0940787083") == "9780940787087"
    assert isbn.isbn_10_to_isbn_13("BAD-ISBN") is None

def test_opposite_isbn():
    assert isbn.opposite_isbn("0-940787-08-3") == "9780940787087"
    assert isbn.opposite_isbn("978-0-940787-08-7") == "0940787083"
    assert isbn.opposite_isbn("BAD-ISBN") is None
