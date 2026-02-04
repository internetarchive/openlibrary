"""Tests for search verification functionality."""

import web

from openlibrary.plugins.worksearch.code import search


class TestSearchVerification:
    """Tests for search expensive query detection."""

    def setup_method(self):
        """Setup test fixtures."""
        self.search_handler = search()

    def test_is_expensive_search_with_language_colon(self):
        """Test detection of language: syntax."""
        i = web.storage(q='language:eng')
        assert self.search_handler._is_expensive_search(i) is True

    def test_is_expensive_search_empty_query(self):
        """Test that empty queries are not marked as expensive."""
        i = web.storage(q='')
        assert self.search_handler._is_expensive_search(i) is False

    def test_is_expensive_search_no_query(self):
        """Test handling when no query parameter exists."""
        i = web.storage()
        assert self.search_handler._is_expensive_search(i) is False
