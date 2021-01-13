import requests
from unittest.mock import Mock, patch

from openlibrary.core import fulltext

from infogami import config


class Test_fulltext_search_api:
    def test_config(self):
        assert not hasattr(config, 'plugin_inside')
        response = fulltext.fulltext_search_api({})
        assert response == {'error': 'Unable to prepare search engine'}


    def test_query_exception(self):
        with patch('openlibrary.core.fulltext.requests.get') as mock_get:
            config.plugin_inside = {'search_endpoint': 'mock'}
            raiser = Mock(side_effect=requests.exceptions.HTTPError('Unable to Connect'))
            mock_response = Mock()
            mock_response.raise_for_status = raiser
            mock_get.return_value = mock_response
            response = fulltext.fulltext_search_api({'q':'hello'})
            assert response == {'error': 'Unable to query search engine'}

    def test_bad_json(self):
        with patch('openlibrary.core.fulltext.requests.get') as mock_get:
            config.plugin_inside = {'search_endpoint': 'mock'}
            mock_response = Mock(json=Mock(side_effect=Exception('Not JSON')))
            mock_get.return_value = mock_response

            response = fulltext.fulltext_search_api({'q':'hello'})
            assert response == {'error': 'Error converting search engine data to JSON'}
