"""Tests for Solr-backed editions table and Work.get_sorted_editions rewiring."""

from unittest.mock import MagicMock, patch

from openlibrary.plugins.upstream.models import Work
from openlibrary.plugins.worksearch.code import (
    EDITION_TABLE_FIELDS,
    SolrEditionWrapper,
    _fetch_work_editions_solr_raw,
    get_solr_editions_for_work,
)
from openlibrary.plugins.worksearch.schemes.editions import EditionSearchScheme


class TestSolrEditionWrapper:
    """Unit tests for SolrEditionWrapper."""

    def test_from_solr_doc_full_mapping(self):
        raw_doc = {
            "key": "/books/OL12345M",
            "work_key": ["OL82536W"],
            "title": "A Great Edition",
            "subtitle": "An Epic Tale",
            "publisher": ["Penguin Books", "Random House"],
            "publish_date": ["October 2001"],
            "publish_year": [2001],
            "format": ["Paperback"],
            "edition_name": ["First Edition"],
            "oclc": ["12345678"],
            "language": ["eng"],
            "cover_i": 999999,
            "isbn": ["123456789X", "9781234567897"],
            "ebook_access": "borrowable",
            "has_fulltext": True,
            "ia": ["greatepic0000unse"],
        }

        wrapper = SolrEditionWrapper.from_solr_doc(raw_doc)

        assert wrapper.key == "/books/OL12345M"
        assert wrapper.title == "A Great Edition"
        assert wrapper.subtitle == "An Epic Tale"
        assert wrapper.publishers == ["Penguin Books", "Random House"]
        assert wrapper.publisher == ["Penguin Books", "Random House"]
        assert wrapper.publish_date == "October 2001"
        assert wrapper.publish_year == [2001]
        assert wrapper.get_publish_year() == 2001
        assert wrapper.physical_format == "Paperback"
        assert wrapper.edition_name == "First Edition"
        assert wrapper.oclc_numbers == ["12345678"]
        assert wrapper.oclc == ["12345678"]
        assert len(wrapper.languages) == 1
        assert wrapper.languages[0].key == "/languages/eng"
        assert wrapper.languages[0].name == "eng"
        assert wrapper.get_isbn10() == "123456789X"
        assert wrapper.get_isbn13() == "9781234567897"
        assert wrapper.ocaid == "greatepic0000unse"
        assert wrapper.has_fulltext is True
        assert wrapper.availability == {"status": "borrow_available", "identifier": "greatepic0000unse"}

        # Dict / Storage protocol compatibility
        assert wrapper["key"] == "/books/OL12345M"
        assert wrapper.get("title") == "A Great Edition"
        assert isinstance(wrapper, dict)
        assert len(dict(wrapper)) > 10

        # Safe attribute lookup (does not raise AttributeError)
        assert wrapper.volumes == []
        assert wrapper.nonexistent_field is None
        assert wrapper.get_authors() == []
        assert wrapper.is_fake_record() is False
        assert wrapper.get_cover_aspect_ratio() is None

        # URLs
        assert "/books/OL12345M" in wrapper.url()
        assert wrapper.get_ia_download_link() == "https://archive.org/download/greatepic0000unse"
        assert "999999-S.jpg" in wrapper.get_cover_url("S")
        assert wrapper.is_access_restricted() is False

    def test_from_solr_doc_empty_fallback(self):
        wrapper = SolrEditionWrapper.from_solr_doc({})

        assert wrapper.key == ""
        assert wrapper.title == ""
        assert wrapper.publishers == []
        assert wrapper.publish_date == ""
        assert wrapper.publish_year is None
        assert wrapper.get_publish_year() is None
        assert wrapper.get_isbn10() is None
        assert wrapper.get_isbn13() is None
        assert wrapper.physical_format == ""
        assert wrapper.availability == {"status": "none"}
        assert wrapper.get_cover_url("M") == "/static/images/icons/avatar_book-sm.png"
        assert wrapper.get_ia_download_link() == ""

    def test_from_solr_doc_public_and_printdisabled_access(self):
        pub_wrapper = SolrEditionWrapper.from_solr_doc({"ebook_access": "public", "ia": ["publicscan01"]})
        assert pub_wrapper.availability == {"status": "open", "identifier": "publicscan01"}
        assert pub_wrapper.is_access_restricted() is False

        pd_wrapper = SolrEditionWrapper.from_solr_doc({"ebook_access": "printdisabled", "ia": ["pdscan01"]})
        assert pd_wrapper.availability == {"status": "borrow_available", "identifier": "pdscan01"}
        assert pd_wrapper.is_access_restricted() is True

    def test_get_publish_year_regex_fallback(self):
        wrapper = SolrEditionWrapper.from_solr_doc({"publish_date": ["Published in 1984 by George"]})
        assert wrapper.get_publish_year() == 1984


class TestFetchWorkEditionsSolrRaw:
    """Unit tests for _fetch_work_editions_solr_raw."""

    @patch("openlibrary.plugins.worksearch.code.run_solr_query")
    def test_fetch_work_editions_defaults(self, mock_run_solr):
        mock_run_solr.return_value = MagicMock(docs=[{"key": "/books/OL1M", "title": "Edition 1"}])

        docs = _fetch_work_editions_solr_raw("OL82536W")

        assert len(docs) == 1
        assert docs[0]["key"] == "/books/OL1M"
        mock_run_solr.assert_called_once()
        args, kwargs = mock_run_solr.call_args

        assert isinstance(args[0], EditionSearchScheme)
        assert args[1] == {"q": "*:*"}
        assert kwargs["offset"] == 0
        assert kwargs["rows"] == 10
        assert kwargs["fields"] == EDITION_TABLE_FIELDS
        assert kwargs["sort"] == "new"
        assert kwargs["facet"] is False
        assert kwargs["request_label"] == "WORK_EDITIONS_TABLE"
        assert ("fq", 'work_key:"OL82536W"') in kwargs["extra_params"]

    @patch("openlibrary.plugins.worksearch.code.run_solr_query")
    def test_fetch_work_editions_ebooks_only(self, mock_run_solr):
        mock_run_solr.return_value = MagicMock(docs=[])

        _fetch_work_editions_solr_raw("/works/OL82536W/", ebooks_only=True, limit=5)

        _, kwargs = mock_run_solr.call_args
        assert kwargs["rows"] == 5
        assert ("fq", 'work_key:"OL82536W"') in kwargs["extra_params"]
        assert ("fq", "(has_fulltext:true OR ebook_access:(public OR borrowable OR printdisabled))") in kwargs["extra_params"]

    @patch("openlibrary.plugins.worksearch.code.run_solr_query")
    def test_fetch_work_editions_unbounded_limit_fixes_7233(self, mock_run_solr):
        mock_run_solr.return_value = MagicMock(docs=[])

        # limit=None corresponds to mode="all"
        _fetch_work_editions_solr_raw("OL82536W", limit=None)

        _, kwargs = mock_run_solr.call_args
        # Bypasses 1000 limit, requests up to 10000 editions from Solr
        assert kwargs["rows"] == 10000


class TestGetSolrEditionsForWork:
    """Unit tests for get_solr_editions_for_work."""

    @patch("openlibrary.plugins.worksearch.code.get_cached_work_editions_raw")
    def test_uses_memcache_for_bounded_queries(self, mock_cached_raw):
        mock_cached_raw.return_value = [{"key": "/books/OL1M", "title": "Cached Edition"}]

        editions = get_solr_editions_for_work("/works/OL82536W", limit=10)

        assert len(editions) == 1
        assert isinstance(editions[0], SolrEditionWrapper)
        assert editions[0].key == "/books/OL1M"
        mock_cached_raw.assert_called_once_with("OL82536W", False, 10, "new")

    @patch("openlibrary.plugins.worksearch.code._fetch_work_editions_solr_raw")
    def test_bypasses_memcache_for_mode_all(self, mock_raw):
        mock_raw.return_value = [{"key": "/books/OL1M", "title": "Direct Edition"}]

        editions = get_solr_editions_for_work("OL82536W", limit=None)

        assert len(editions) == 1
        mock_raw.assert_called_once_with("OL82536W", False, None, "new")

    @patch("openlibrary.plugins.worksearch.code.run_solr_query")
    @patch("openlibrary.plugins.worksearch.code.get_cached_work_editions_raw")
    def test_fetches_missing_requested_keys(self, mock_cached_raw, mock_run_solr):
        mock_cached_raw.return_value = [{"key": "/books/OL1M", "title": "Top Edition", "publish_year": [2010]}]
        mock_run_solr.return_value = MagicMock(docs=[{"key": "/books/OL999M", "title": "Missing Requested", "publish_year": [2020]}])

        editions = get_solr_editions_for_work(
            "OL82536W",
            limit=10,
            keys=["/books/OL999M"],
        )

        assert len(editions) == 2
        keys = [e.key for e in editions]
        assert "/books/OL1M" in keys
        assert "/books/OL999M" in keys
        # Editions are sorted by publish year descending
        assert editions[0].key == "/books/OL999M"

    @patch("openlibrary.core.lending.get_availability")
    @patch("openlibrary.plugins.worksearch.code.get_cached_work_editions_raw")
    def test_attaches_lending_availability(self, mock_cached_raw, mock_get_availability):
        mock_cached_raw.return_value = [
            {"key": "/books/OL1M", "title": "Scanned Book", "ocaid": "scanned01", "publish_year": [2010]},
            {"key": "/books/OL2M", "title": "Physical Book", "publish_year": [2015]},
        ]
        mock_get_availability.return_value = {"scanned01": {"status": "open", "identifier": "scanned01", "is_readable": True}}

        editions = get_solr_editions_for_work("OL82536W", limit=10)

        assert len(editions) == 2
        mock_get_availability.assert_called_once_with("identifier", ["scanned01"])
        ed_scanned = next(e for e in editions if e.key == "/books/OL1M")
        ed_physical = next(e for e in editions if e.key == "/books/OL2M")
        assert ed_scanned.availability == {"status": "open", "identifier": "scanned01", "is_readable": True}
        assert ed_physical.availability == {"status": "none"}


class TestWorkGetSortedEditionsRewire:
    """Unit tests verifying Work.get_sorted_editions Solr integration and DB fallback."""

    @patch("openlibrary.plugins.upstream.models.get_solr_editions_for_work")
    def test_returns_solr_editions_when_available(self, mock_get_solr):
        mock_solr_ed = SolrEditionWrapper.from_solr_doc({"key": "/books/OL1M", "title": "Solr Edition"})
        mock_get_solr.return_value = [mock_solr_ed]

        work = Work(None, "works/OL82536W")
        work._get_sorted_editions_db = MagicMock()

        editions = work.get_sorted_editions(limit=10)

        assert editions == [mock_solr_ed]
        mock_get_solr.assert_called_once_with(
            work_key="works/OL82536W",
            ebooks_only=False,
            limit=10,
            keys=None,
        )
        work._get_sorted_editions_db.assert_not_called()

    @patch("openlibrary.plugins.upstream.models.get_solr_editions_for_work")
    def test_falls_back_to_db_when_solr_returns_empty(self, mock_get_solr):
        mock_get_solr.return_value = []

        work = Work(None, "works/OL82536W")
        mock_db_ed = MagicMock(key="/books/OL2M")
        work._get_sorted_editions_db = MagicMock(return_value=[mock_db_ed])

        editions = work.get_sorted_editions(limit=10)

        assert editions == [mock_db_ed]
        work._get_sorted_editions_db.assert_called_once_with(
            ebooks_only=False,
            limit=10,
            keys=None,
        )

    @patch("openlibrary.plugins.upstream.models.get_solr_editions_for_work")
    def test_falls_back_to_db_when_solr_raises_exception(self, mock_get_solr):
        mock_get_solr.side_effect = RuntimeError("Solr connection error")

        work = Work(None, "works/OL82536W")
        mock_db_ed = MagicMock(key="/books/OL3M")
        work._get_sorted_editions_db = MagicMock(return_value=[mock_db_ed])

        editions = work.get_sorted_editions(limit=10)

        assert editions == [mock_db_ed]
        work._get_sorted_editions_db.assert_called_once_with(
            ebooks_only=False,
            limit=10,
            keys=None,
        )
