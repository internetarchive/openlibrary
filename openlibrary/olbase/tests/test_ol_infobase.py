from unittest.mock import MagicMock

from openlibrary.plugins import ol_infobase
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


def test_in_process_writes_skip_legacy_write_listeners(monkeypatch):
    site = MagicMock()
    infobase = MagicMock()
    monkeypatch.setattr(ol_infobase.app_config, "in_process_writes", True, raising=False)
    monkeypatch.setattr(ol_infobase.config, "errorlog", None, raising=False)
    monkeypatch.setattr(ol_infobase.config, "writelog", "/tmp/infobase-writelog", raising=False)
    monkeypatch.setattr(ol_infobase.config, "http_listeners", ["http://listener"], raising=False)
    monkeypatch.setattr(ol_infobase.server, "get_site", lambda _: site)
    monkeypatch.setattr(ol_infobase.server, "_infobase", infobase, raising=False)
    monkeypatch.setattr(ol_infobase.server.app, "add_mapping", lambda *args: None)
    monkeypatch.setattr(ol_infobase, "setup_logging", lambda: None)

    ol_infobase.init_plugin()

    infobase.add_event_listener.assert_called_once_with(ol_infobase.invalidate_most_recent_change)
    site.add_trigger.assert_not_called()
