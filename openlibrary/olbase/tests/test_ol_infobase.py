from openlibrary.plugins.ol_infobase import OLIndexer

class TestOLIndexer:
    def test_expand_isbns(self):
        indexer = OLIndexer()
        isbn_10 = ['123456789X']
        isbn_13 = ['9781234567897']
        both = isbn_10 + isbn_13
        assert indexer.expand_isbns([]) == []
        assert indexer.expand_isbns(isbn_10) == both
        assert indexer.expand_isbns(isbn_13) == both
        assert indexer.expand_isbns(both) == both
