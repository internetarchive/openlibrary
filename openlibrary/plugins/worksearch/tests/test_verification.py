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
    
    def test_is_expensive_search_with_wildcard(self):
        """Test detection of wildcard queries."""
        i = web.storage(q='*:*')
        assert self.search_handler._is_expensive_search(i) is True
    
    def test_is_expensive_search_with_field_syntax(self):
        """Test detection of field-specific syntax."""
        i = web.storage(q='title:hobbit')
        assert self.search_handler._is_expensive_search(i) is True
    
    def test_is_expensive_search_with_boolean_operator(self):
        """Test detection of boolean operators."""
        i = web.storage(q='test AND query')
        assert self.search_handler._is_expensive_search(i) is True
        
        i = web.storage(q='test OR query')
        assert self.search_handler._is_expensive_search(i) is True
        
        i = web.storage(q='test NOT query')
        assert self.search_handler._is_expensive_search(i) is True
    
    def test_is_expensive_search_with_language_filter(self):
        """Test detection of language filter parameter."""
        i = web.storage(q='test', language=['eng'])
        assert self.search_handler._is_expensive_search(i) is True
    
    def test_is_expensive_search_with_range_query(self):
        """Test detection of range queries."""
        i = web.storage(q='year:[1900 TO 2000]')
        assert self.search_handler._is_expensive_search(i) is True
        
        i = web.storage(q='year:{1900 TO 2000}')
        assert self.search_handler._is_expensive_search(i) is True
    
    def test_is_expensive_search_simple_query(self):
        """Test that simple queries are not marked as expensive."""
        i = web.storage(q='the hobbit')
        assert self.search_handler._is_expensive_search(i) is False
    
    def test_is_expensive_search_empty_query(self):
        """Test that empty queries are not marked as expensive."""
        i = web.storage(q='')
        assert self.search_handler._is_expensive_search(i) is False
    
    def test_is_expensive_search_no_query(self):
        """Test handling when no query parameter exists."""
        i = web.storage()
        assert self.search_handler._is_expensive_search(i) is False
