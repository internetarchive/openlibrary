import sys
import unittest
import sys
import unittest
from unittest.mock import MagicMock, patch
import json

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
            'openlibrary.plugins.upstream.utils': MagicMock(),
        }

    # Helper for dot-access dicts (serializable by json.dumps)
    class Obj(dict):
        def __getattr__(self, name):
            if name in self:
                return self[name]
            raise AttributeError(name)

    # Helper: create a minimal response-like object that is safe for code that
    # may access .text, .content, .json() or .select(). Using this avoids
    # json.loads() being passed a MagicMock.
    def _make_solr_response(self, select_result):
        class _Resp:
            def __init__(self, result):
                self._result = result
                # ensure .text/.content are serialised JSON (bytes/str)
                try:
                    self.text = json.dumps(result)
                    self.content = self.text.encode("utf-8")
                except Exception:
                    # fall back to empty JSON
                    self.text = "{}"
                    self.content = b"{}"
                # Mimic select method as a mock so we can track calls
                self.select = MagicMock(return_value=result)

            def json(self):
                # emulate requests.Response.json()
                return self._result
        return _Resp(select_result)

    def test_language_query_params(self):
        # Setup the mocks required for import and execution
        with patch.dict(sys.modules, self.get_common_mocks()):
            # Import inside the patched context
            if 'openlibrary.plugins.worksearch.languages' in sys.modules:
                del sys.modules['openlibrary.plugins.worksearch.languages']
            if 'openlibrary.plugins.worksearch.subjects' in sys.modules:
                del sys.modules['openlibrary.plugins.worksearch.subjects']

            from openlibrary.plugins.worksearch import languages

            # Mock get_solr
            # Mock get_solr
            with patch(
                'openlibrary.plugins.worksearch.search.get_solr'
            ) as mock_get_solr:
                # Provide a safe response object (handles .text, .content, .json(), .select)
                mock_solr_instance = self._make_solr_response({'facets': {'language': []}})
                mock_get_solr.return_value = mock_solr_instance

                # Call the function
                languages.get_all_language_counts('work')

                # Verify arguments
                args, kwargs = mock_solr_instance.select.call_args
                self.assertTrue(
                    kwargs.get('_pass_time_allowed'),
                    "Should have _pass_time_allowed=True",
                )

    def test_subject_query_params(self):
        with patch.dict(sys.modules, self.get_common_mocks()):
            # Ensure we re-import to get the mocks
            if 'openlibrary.plugins.worksearch.subjects' in sys.modules:
                del sys.modules['openlibrary.plugins.worksearch.subjects']

            # Explicitly import the module we want to patch to ensure it exists
            from openlibrary.plugins.worksearch import subjects

            with patch(
                'openlibrary.plugins.worksearch.code.run_solr_query'
            ) as mock_run_solr_query:
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

    def test_language_ebook_count_publish_year(self):
        with patch.dict(sys.modules, self.get_common_mocks()):
            if 'openlibrary.plugins.worksearch.languages' in sys.modules:
                del sys.modules['openlibrary.plugins.worksearch.languages']

            from openlibrary.plugins.worksearch import languages

            with patch(
                'openlibrary.plugins.worksearch.search.get_solr'
            ) as mock_get_solr:
                # Test LanguageEngine.get_ebook_count with different publish_year inputs
                engine = languages.LanguageEngine()
                
                # Mock result - wrap into safe response object
                # Use self.Obj so json.dumps works AND dot-access works (v.value, v.count)
                mock_result = {
                    'facets': {'has_fulltext': [self.Obj(value='true', count=10)]}
                }
                mock_solr_instance = self._make_solr_response(mock_result)
                mock_get_solr.return_value = mock_solr_instance

                # Case 1: Single year > 2000
                engine.get_ebook_count("English", "eng", 2025)
                args, kwargs = mock_solr_instance.select.call_args
                self.assertEqual(
                    args[0]['publish_year'], 2025, "Should handle years > 2000"
                )

                # Case 2: List of years (range)
                engine.get_ebook_count("English", "eng", [1990, 2025])
                args, kwargs = mock_solr_instance.select.call_args
                self.assertEqual(
                    args[0]['publish_year'],
                    (1990, 2025),
                    "Should handle ranges ending > 2000",
                )

    def test_date_range_filter(self):
        # This one is a pure function and shouldn't need heavy mocking if imports are handled
        with patch.dict(sys.modules, self.get_common_mocks()):
            if 'openlibrary.plugins.worksearch.subjects' in sys.modules:
                del sys.modules['openlibrary.plugins.worksearch.subjects']

            from openlibrary.plugins.worksearch.subjects import (
                date_range_to_publish_year_filter,
            )

            self.assertEqual(
                date_range_to_publish_year_filter("1990-2025"), "[1990 TO 2025]"
            )
            self.assertEqual(date_range_to_publish_year_filter("2025"), "2025")
            self.assertEqual(date_range_to_publish_year_filter("invalid"), "")
            self.assertEqual(date_range_to_publish_year_filter("1990-invalid"), "")

    # PORTED TESTS FROM test_worksearch.py

    def test_process_facet(self):
        with patch.dict(sys.modules, self.get_common_mocks()):
            if 'openlibrary.plugins.worksearch.code' in sys.modules:
                del sys.modules['openlibrary.plugins.worksearch.code']

            from openlibrary.plugins.worksearch.code import process_facet

            facets = [('false', 46), ('true', 2)]
            # Note: The original test expects list output
            self.assertEqual(
                list(process_facet('has_fulltext', facets)),
                [
                    ('true', 'yes', 2),
                    ('false', 'no', 46),
                ],
            )

    def test_prepare_solr_query_params_first_publish_year_string(self):
        with patch.dict(sys.modules, self.get_common_mocks()):
            if 'openlibrary.plugins.worksearch.code' in sys.modules:
                del sys.modules['openlibrary.plugins.worksearch.code']
            if 'openlibrary.plugins.worksearch.schemes.works' in sys.modules:
                del sys.modules['openlibrary.plugins.worksearch.schemes.works']

            from openlibrary.plugins.worksearch.code import _prepare_solr_query_params
            from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme

            scheme = WorkSearchScheme()
            param = {'first_publish_year': '1997'}
            params, fields = _prepare_solr_query_params(scheme, param)

            param2 = {'first_publish_year': ['1997']}
            params2, fields2 = _prepare_solr_query_params(scheme, param2)
            self.assertEqual(params, params2)
            self.assertEqual(fields, fields2)
            # Check that the fq param for first_publish_year is correctly added
            fq_params = [p for p in params if p[0] == 'fq']
            self.assertIn(('fq', 'first_publish_year:"1997"'), fq_params)


if __name__ == '__main__':
    unittest.main()
