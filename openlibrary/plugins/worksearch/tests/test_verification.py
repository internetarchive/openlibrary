import sys
import unittest
from unittest.mock import MagicMock, patch

# We do NOT want to mock modules globally as it breaks other tests in the suite.
# Instead, we will use patch.dict on sys.modules contextually.


class TestVerification(unittest.TestCase):
    def setUp(self):
        # Create a clean mock for web.ctx for each test
        self.mock_web = MagicMock()
        self.mock_web.ctx = MagicMock()
        self.mock_web.ctx.features = {}
        self.mock_web.ctx.env = {}
        self.mock_web.ctx.site = MagicMock()
        self.mock_web.input = MagicMock()
        # Mock web.__version__ to satisfy assertions in infogami/utils/template.py
        self.mock_web.__version__ = "0.62"

    def get_common_mocks(self):
        """Returns a dictionary of common mocks needed for most tests."""

        # Mock safeint to behave like the real thing for our test cases
        def side_effect_safeint(val, default=None):
            try:
                return int(val)
            except (ValueError, TypeError):
                return default

        mock_safeint = MagicMock(side_effect=side_effect_safeint)

        # Mock infogami.utils.view to provide safeint
        mock_view = MagicMock()
        mock_view.safeint = mock_safeint

        # Mock openlibrary.core.cache to have a pass-through memoize
        mock_cache = MagicMock()
        mock_cache.memoize.side_effect = lambda *args, **kwargs: lambda f: f

        return {
            'psycopg2': MagicMock(),
            'psycopg2.errors': MagicMock(),
            'openlibrary.core.db': MagicMock(),
            'memcache': MagicMock(),
            'pymemcache': MagicMock(),
            'pymemcache.test.utils': MagicMock(),
            'luqum': MagicMock(),
            'luqum.tree': MagicMock(),
            'luqum.exceptions': MagicMock(),
            'web': self.mock_web,
            'web.template': MagicMock(),
            'validate_email': MagicMock(),
            'infogami.plugins.api.code': MagicMock(),
            'infogami.utils': MagicMock(),
            'infogami.utils.view': mock_view,
            'openlibrary.core.cache': mock_cache,
            'openlibrary.core.lending': MagicMock(),
            'openlibrary.core.models': MagicMock(),
            'openlibrary.solr.query_utils': MagicMock(),
            'openlibrary.utils': MagicMock(),
            'openlibrary.utils.solr': MagicMock(),
            'openlibrary.utils.dateutil': MagicMock(),
            'openlibrary.utils.ddc': MagicMock(),
            'openlibrary.utils.isbn': MagicMock(),
            'openlibrary.utils.lcc': MagicMock(),
            'openlibrary.utils.async_utils': MagicMock(),
            'openlibrary.accounts': MagicMock(),
            # upstream utils import web.template
            'openlibrary.plugins.upstream.utils': MagicMock(),
            'openlibrary.plugins.worksearch.search': MagicMock(),
        }

    def test_language_query_params(self):
        """Verify _pass_time_allowed=True is passed to Solr for language counts."""
        with patch.dict(sys.modules, self.get_common_mocks()):
            if 'openlibrary.plugins.worksearch.languages' in sys.modules:
                del sys.modules['openlibrary.plugins.worksearch.languages']

            from openlibrary.plugins.worksearch import languages

            # Mock get_solr
            with patch(
                'openlibrary.plugins.worksearch.search.get_solr'
            ) as mock_get_solr:
                mock_solr_instance = MagicMock()
                # Ensure .text and .content are strings/bytes to satisfy json.loads logic if invoked
                mock_solr_instance.text = '{}'
                mock_solr_instance.content = b'{}'
                mock_get_solr.return_value = mock_solr_instance

                # We return a generic dict. We assume the code iterates the facets locally.
                # If the code tries to access properties (row.value), we put MagicMocks in the list.
                mock_solr_instance.select.return_value = {'facets': {'language': []}}

                # Call the function
                languages.get_all_language_counts('work')

                # Verify arguments - this is the core verification
                args, kwargs = mock_solr_instance.select.call_args
                self.assertTrue(
                    kwargs.get('_pass_time_allowed'),
                    "Should have _pass_time_allowed=True",
                )

    def test_subject_query_params(self):
        """Verify publish_year facet limit is set to 2000."""
        with patch.dict(sys.modules, self.get_common_mocks()):
            if 'openlibrary.plugins.worksearch.subjects' in sys.modules:
                del sys.modules['openlibrary.plugins.worksearch.subjects']

            from openlibrary.plugins.worksearch import subjects

            with patch(
                'openlibrary.plugins.worksearch.code.run_solr_query'
            ) as mock_run_solr_query:
                # Setup mock return value
                mock_result = MagicMock(num_found=0, docs=[])
                # Provide empty lists for all expected keys to avoid iteration errors
                mock_result.facet_counts = {
                    'has_fulltext': [],
                    'subject_facet': [],
                    'place_facet': [],
                    'person_facet': [],
                    'time_facet': [],
                    'author_key': [],
                    'publisher_facet': [],
                    'language': [],
                    'publish_year': [],
                }
                mock_run_solr_query.return_value = mock_result

                engine = subjects.SubjectEngine(
                    name="subject",
                    key="subjects",
                    prefix="/subjects/",
                    facet="subject_facet",
                    facet_key="subject_key",
                )

                # Call the function
                engine.get_subject("/subjects/foo", details=True)

                # Verify arguments
                args, kwargs = mock_run_solr_query.call_args
                facet_params = kwargs.get('facet')

                # Find publish_year facet config
                publish_year_config = next(
                    (
                        f
                        for f in facet_params
                        if isinstance(f, dict) and f.get('name') == 'publish_year'
                    ),
                    None,
                )

                self.assertIsNotNone(
                    publish_year_config, "Should have publish_year facet config"
                )
                self.assertEqual(
                    publish_year_config.get('limit'),
                    2000,
                    "Should have limit=2000 for publish_year",
                )


if __name__ == '__main__':
    unittest.main()
