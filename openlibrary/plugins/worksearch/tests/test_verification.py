import sys
import unittest
from unittest.mock import MagicMock, patch

# Mock psycopg2 and db before they are imported
sys.modules['psycopg2'] = MagicMock()
sys.modules['psycopg2.errors'] = MagicMock()
sys.modules['openlibrary.core.db'] = MagicMock()

import web

# Mock web.ctx
web.ctx = web.storage()
web.ctx.site = MagicMock()
web.ctx.features = {}
web.ctx.env = {}

from openlibrary.plugins.worksearch import languages, subjects

class TestVerification(unittest.TestCase):
    @patch('openlibrary.plugins.worksearch.search.get_solr')
    def test_language_query_params(self, mock_get_solr):
        # Setup mock
        mock_solr_instance = MagicMock()
        mock_get_solr.return_value = mock_solr_instance
        mock_solr_instance.select.return_value = {'facets': {'language': []}}

        # Call the function
        languages.get_all_language_counts('work')

        # Verify arguments
        args, kwargs = mock_solr_instance.select.call_args
        self.assertTrue(kwargs.get('_pass_time_allowed'), "Should have _pass_time_allowed=True")

    @patch('openlibrary.plugins.worksearch.code.run_solr_query')
    def test_subject_query_params(self, mock_run_solr_query):
        # Setup mock
        mock_result = MagicMock(num_found=0, docs=[])
        mock_result.facet_counts = {
            'has_fulltext': [],
            'subject_facet': [],
            'place_facet': [],
            'person_facet': [],
            'time_facet': [],
            'author_key': [],
            'publisher_facet': [],
            'language': [],
            'publish_year': []
        }
        mock_run_solr_query.return_value = mock_result
        
        engine = subjects.SubjectEngine(
            name="subject", key="subjects", prefix="/subjects/", facet="subject_facet", facet_key="subject_key"
        )

        # Call the function
        engine.get_subject("/subjects/foo", details=True)

        # Verify arguments
        args, kwargs = mock_run_solr_query.call_args
        facet_params = kwargs.get('facet')
        
        # Find publish_year facet config
        publish_year_config = next((f for f in facet_params if isinstance(f, dict) and f.get('name') == 'publish_year'), None)
        
        self.assertIsNotNone(publish_year_config, "Should have publish_year facet config")
        self.assertEqual(publish_year_config.get('limit'), 2000, "Should have limit=2000 for publish_year")

    @patch('openlibrary.plugins.worksearch.search.get_solr')
    def test_language_ebook_count_publish_year(self, mock_get_solr):
        # Test LanguageEngine.get_ebook_count with different publish_year inputs
        engine = languages.LanguageEngine()
        mock_solr_instance = MagicMock()
        mock_get_solr.return_value = mock_solr_instance
        
        # Mock result
        mock_result = {'facets': {'has_fulltext': [web.storage(value='true', count=10)]}}
        mock_solr_instance.select.return_value = mock_result

        # Case 1: Single year > 2000
        engine.get_ebook_count("English", "eng", 2025)
        args, kwargs = mock_solr_instance.select.call_args
        self.assertEqual(args[0]['publish_year'], 2025, "Should handle years > 2000")

        # Case 2: List of years (range)
        engine.get_ebook_count("English", "eng", [1990, 2025])
        args, kwargs = mock_solr_instance.select.call_args
        self.assertEqual(args[0]['publish_year'], (1990, 2025), "Should handle ranges ending > 2000")

    def test_date_range_filter(self):
        # Test the date_range_to_publish_year_filter helper in subjects.py
        from openlibrary.plugins.worksearch.subjects import date_range_to_publish_year_filter
        
        self.assertEqual(date_range_to_publish_year_filter("1990-2025"), "[1990 TO 2025]")
        self.assertEqual(date_range_to_publish_year_filter("2025"), "2025")
        self.assertEqual(date_range_to_publish_year_filter("invalid"), "")
        self.assertEqual(date_range_to_publish_year_filter("1990-invalid"), "")

if __name__ == '__main__':
    unittest.main()
