"""Tests for AuthorSolrBuilder date parsing functionality."""

import pytest

from openlibrary.solr.updater.author import AuthorSolrBuilder


class TestAuthorSolrBuilderDateParsing:
    """Test the _parse_date_to_iso method in AuthorSolrBuilder."""

    @pytest.fixture
    def builder(self):
        """Create a minimal AuthorSolrBuilder for testing."""
        author = {'key': '/authors/OL1A', 'name': 'Test Author'}
        solr_reply = {'response': {'docs': [], 'numFound': 0}, 'facets': {}}
        return AuthorSolrBuilder(author, solr_reply)

    def test_parse_iso_date_format(self, builder):
        """Test parsing YYYY-MM-DD format."""
        result = builder._parse_date_to_iso("2000-01-10")
        assert result == "2000-01-10T00:00:00Z"

    def test_parse_full_date_string(self, builder):
        """Test parsing 'DD Mon YYYY' format."""
        result = builder._parse_date_to_iso("10 Jan 2000")
        assert result == "2000-01-10T00:00:00Z"

    def test_parse_full_date_variant(self, builder):
        """Test parsing 'Month DD, YYYY' format."""
        result = builder._parse_date_to_iso("January 10, 2000")
        assert result == "2000-01-10T00:00:00Z"

    def test_parse_year_only(self, builder):
        """Test parsing year-only strings."""
        result = builder._parse_date_to_iso("1990")
        assert result == "1990-01-01T00:00:00Z"

    def test_parse_approximate_date(self, builder):
        """Test parsing approximate dates fallback to year extraction."""
        result = builder._parse_date_to_iso("approx 1990")
        assert result == "1990-01-01T00:00:00Z"

    def test_parse_circa_date(self, builder):
        """Test parsing 'circa' dates."""
        result = builder._parse_date_to_iso("circa 1845")
        assert result == "1845-01-01T00:00:00Z"

    def test_parse_none_input(self, builder):
        """Test that None input returns None."""
        result = builder._parse_date_to_iso(None)
        assert result is None

    def test_parse_empty_string(self, builder):
        """Test that empty string returns None."""
        result = builder._parse_date_to_iso("")
        assert result is None

    def test_parse_unparsable_string(self, builder):
        """Test that unparsable strings return None."""
        result = builder._parse_date_to_iso("14th century")
        assert result is None

    def test_parse_non_gregorian_date(self, builder):
        """Test that non-parseable calendar dates return None."""
        result = builder._parse_date_to_iso("Persian calendar date")
        assert result is None


class TestAuthorSolrBuilderTimestampProperties:
    """Test the birth_timestamp and death_timestamp properties."""

    def test_birth_timestamp_property(self):
        """Test birth_timestamp property returns parsed date."""
        author = {
            'key': '/authors/OL1A',
            'name': 'Test Author',
            'birth_date': '10 Jan 2000',
        }
        solr_reply = {'response': {'docs': [], 'numFound': 0}, 'facets': {}}
        builder = AuthorSolrBuilder(author, solr_reply)

        assert builder.birth_timestamp == "2000-01-10T00:00:00Z"

    def test_death_timestamp_property(self):
        """Test death_timestamp property returns parsed date."""
        author = {
            'key': '/authors/OL1A',
            'name': 'Test Author',
            'death_date': '15 Mar 2020',
        }
        solr_reply = {'response': {'docs': [], 'numFound': 0}, 'facets': {}}
        builder = AuthorSolrBuilder(author, solr_reply)

        assert builder.death_timestamp == "2020-03-15T00:00:00Z"

    def test_timestamp_property_with_missing_date(self):
        """Test timestamp properties return None when date not present."""
        author = {'key': '/authors/OL1A', 'name': 'Test Author'}
        solr_reply = {'response': {'docs': [], 'numFound': 0}, 'facets': {}}
        builder = AuthorSolrBuilder(author, solr_reply)

        assert builder.birth_timestamp is None
        assert builder.death_timestamp is None

    def test_timestamp_property_with_year_only(self):
        """Test timestamp properties with year-only dates."""
        author = {
            'key': '/authors/OL1A',
            'name': 'Test Author',
            'birth_date': '1835',
            'death_date': '1910',
        }
        solr_reply = {'response': {'docs': [], 'numFound': 0}, 'facets': {}}
        builder = AuthorSolrBuilder(author, solr_reply)

        assert builder.birth_timestamp == "1835-01-01T00:00:00Z"
        assert builder.death_timestamp == "1910-01-01T00:00:00Z"
