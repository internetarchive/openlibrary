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

if __name__ == '__main__':
    unittest.main()
