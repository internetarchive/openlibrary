import datetime
from openlibrary.plugins.importapi import code
from openlibrary.mocks.mock_infobase import MockSite
"""Tests for Koha ILS (Integrated Library System) code.
"""

class Test_ils_cover_upload:
    def test_build_url(self):
        build_url = code.ils_cover_upload().build_url
        assert build_url("http://example.com/foo", status="ok") == "http://example.com/foo?status=ok"
        assert build_url("http://example.com/foo?bar=true", status="ok") == "http://example.com/foo?bar=true&status=ok"

class Test_ils_search:
    def test_format_result(self, mock_site):
        format_result = code.ils_search().format_result

        assert format_result({"doc": {}}, False, "") == {
            'status': 'notfound'
        }

        doc = {
            'key': '/books/OL1M',
            'type': {'key': '/type/edition'}
        }
        timestamp = datetime.datetime(2010, 1, 2, 3, 4, 5)
        mock_site.save(doc, timestamp=timestamp)
        assert format_result({'doc': doc}, False, "") == {
            'status': 'found',
            'olid': 'OL1M',
            'key': '/books/OL1M'
        }

        doc = {
            'key': '/books/OL1M',
            'type': {'key': '/type/edition'},
            'covers': [12345]
        }
        timestamp = datetime.datetime(2011, 1, 2, 3, 4, 5)
        mock_site.save(doc, timestamp=timestamp)
        assert format_result({'doc': doc}, False, "") == {
            'status': 'found',
            'olid': 'OL1M',
            'key': '/books/OL1M',
            'covers': [12345],
            'cover': {
                'small': 'https://covers.openlibrary.org/b/id/12345-S.jpg',
                'medium': 'https://covers.openlibrary.org/b/id/12345-M.jpg',
                'large': 'https://covers.openlibrary.org/b/id/12345-L.jpg',
            }
        }

    def test_prepare_input_data(self):
        prepare_input_data = code.ils_search().prepare_input_data

        data = {
            'isbn': ['1234567890', '9781234567890'],
            'ocaid': ['abc123def'],
            'publisher': 'Some Books',
            'authors': ['baz']
        }
        assert prepare_input_data(data) == {
            'doc': {
                'identifiers': {
                     'isbn': ['1234567890', '9781234567890'],
                      'ocaid': ['abc123def']
                },
                'publisher': 'Some Books',
                'authors': [{'name': 'baz'}]
            }
        }
