from .. import code

class Test_ils_cover_upload:
    def test_build_url(self):
        build_url = code.ils_cover_upload().build_url
        assert build_url("http://example.com/foo", status="ok") == "http://example.com/foo?status=ok"
        assert build_url("http://example.com/foo?bar=true", status="ok") == "http://example.com/foo?bar=true&status=ok"
        
class Test_ils_search:
    def test_format_result(self):
        format_result = code.ils_search().format_result
        
        assert format_result(None) == {
            'status': 'notfound'
        }
        
        doc = {
            'key': '/books/OL1M',
            'type': {'key': '/type/edition'}
        }
        assert format_result(doc) == {
            'status': 'found',
            'olid': 'OL1M',
            'key': '/books/OL1M'
        }
        
        doc = {
            'key': '/books/OL1M',
            'type': {'key': '/type/edition'},
            'covers': [12345]
        }
        assert format_result(doc) == {
            'status': 'found',
            'olid': 'OL1M',
            'key': '/books/OL1M',
            'cover': {
                'small': 'http://covers.openlibrary.org/b/id/12345-S.jpg',
                'medium': 'http://covers.openlibrary.org/b/id/12345-M.jpg',
                'large': 'http://covers.openlibrary.org/b/id/12345-L.jpg',
            }
        }
        
    def test_prepare_data(self):
        prepare_data = code.ils_search().prepare_data
        
        data = {
            'isbn': ['1234567890', '9781234567890', '123-4-56789-0', '978-1-935928-32-4']
        }
        assert prepare_data(data) == {
            'isbn_10': ['1234567890', '123-4-56789-0'],
            'isbn_13': ['9781234567890', '978-1-935928-32-4']
        }
