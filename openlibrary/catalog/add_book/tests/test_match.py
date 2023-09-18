import pytest

from openlibrary.catalog.add_book.match import editions_match
from openlibrary.catalog.add_book import load


def test_editions_match_identical_record(mock_site):
    rec = {
        'title': 'Test item',
        'lccn': ['12345678'],
        'authors': [{'name': 'Smith, John', 'birth_date': '1980'}],
        'source_records': ['ia:test_item'],
    }
    reply = load(rec)
    ekey = reply['edition']['key']
    e = mock_site.get(ekey)
    assert editions_match(rec, e) is True
