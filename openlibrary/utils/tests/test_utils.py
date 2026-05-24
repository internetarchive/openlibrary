from openlibrary.utils import (
    extract_numeric_id_from_olid,
)


def test_extract_numeric_id_from_olid():
    assert extract_numeric_id_from_olid("/works/OL123W") == "123"
    assert extract_numeric_id_from_olid("OL123W") == "123"
