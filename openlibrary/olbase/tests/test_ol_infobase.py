from openlibrary.plugins.ol_infobase import OLIndexer, fix_table_of_contents


class TestOLIndexer:
    def test_expand_isbns(self):
        indexer = OLIndexer()
        isbn_10 = ["123456789X"]
        isbn_13 = ["9781234567897"]
        both = isbn_10 + isbn_13
        assert indexer.expand_isbns([]) == []
        assert sorted(indexer.expand_isbns(isbn_10)) == both
        assert sorted(indexer.expand_isbns(isbn_13)) == both
        assert sorted(indexer.expand_isbns(both)) == both


class TestFixTableOfContents:
    def test_legacy_shapes(self):
        assert fix_table_of_contents(["Preface", {"value": "Chapter One"}]) == [
            {"level": 0, "label": "", "title": "Preface", "pagenum": ""},
            {"level": 0, "label": "", "title": "Chapter One", "pagenum": ""},
        ]

    def test_coerces_core_fields(self):
        assert fix_table_of_contents([{"level": "2", "title": "Chapter One"}]) == [{"level": 2, "label": "", "title": "Chapter One", "pagenum": ""}]

    def test_preserves_extra_fields(self):
        toc = [
            {
                "level": 0,
                "title": "Preface",
                "pagenum": "1",
                "authors": [{"name": "Alice Author"}],
                "subtitle": "A beginning",
                "description": "Some description",
                "type": {"key": "/type/toc_item"},
            }
        ]
        assert fix_table_of_contents(toc) == [{"label": "", **toc[0]}]

    def test_drops_empty_rows(self):
        assert fix_table_of_contents(["", {}, {"type": {"key": "/type/toc_item"}}]) == []
