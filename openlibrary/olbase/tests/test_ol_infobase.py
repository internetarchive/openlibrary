from openlibrary.plugins.ol_infobase import OLIndexer

class TestOLIndexer:
    def test_normalize_isbn(self):
        indexer = OLIndexer()
        assert indexer.normalize_isbn("123456789X") == "123456789X"
        assert indexer.normalize_isbn("123-456-789-X") == "123456789X"
        assert indexer.normalize_isbn("123-456-789-X ") == "123456789X"
        
    def test_expand_isbns(self):
        indexer = OLIndexer()
        assert indexer.expand_isbns([]) == []
        assert indexer.expand_isbns(["123456789X"]) == ["123456789X", "9781234567897"]
        assert indexer.expand_isbns(["9781234567897"]) == ["123456789X", "9781234567897"]
        assert indexer.expand_isbns(["123456789X", "9781234567897"]) == ["123456789X", "9781234567897"]
