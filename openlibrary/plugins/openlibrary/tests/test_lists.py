import json
from unittest.mock import patch

import pytest

from openlibrary.plugins.openlibrary.lists import ListRecord


class TestListRecord:
    def test_from_input_no_data(self):
        with (
            patch('web.input') as mock_web_input,
            patch('web.data') as mock_web_data,
        ):
            mock_web_data.return_value = b''
            mock_web_input.return_value = {
                'key': None,
                'name': 'foo',
                'description': 'bar',
                'seeds': [],
            }
            assert ListRecord.from_input() == ListRecord(
                key=None,
                name='foo',
                description='bar',
                seeds=[],
            )

    def test_from_input_with_data(self):
        with (
            patch('web.input') as mock_web_input,
            patch('web.data') as mock_web_data,
            patch('web.ctx') as mock_web_ctx,
        ):
            mock_web_ctx.env = {}
            mock_web_data.return_value = b'key=/lists/OL1L&name=foo+data&description=bar&seeds--0--key=/books/OL1M&seeds--1--key=/books/OL2M'
            mock_web_input.return_value = {
                'key': None,
                'name': 'foo',
                'description': 'bar',
                'seeds': [],
            }
            assert ListRecord.from_input() == ListRecord(
                key='/lists/OL1L',
                name='foo data',
                description='bar',
                seeds=[{'key': '/books/OL1M'}, {'key': '/books/OL2M'}],
            )

    def test_from_input_with_json_data(self):
        with (
            patch('web.input') as mock_web_input,
            patch('web.data') as mock_web_data,
            patch('web.ctx') as mock_web_ctx,
        ):
            mock_web_ctx.env = {'CONTENT_TYPE': 'application/json'}
            mock_web_data.return_value = json.dumps(
                {
                    'name': 'foo data',
                    'description': 'bar',
                    'seeds': [{'key': '/books/OL1M'}, {'key': '/books/OL2M'}],
                }
            ).encode('utf-8')
            mock_web_input.return_value = {
                'key': None,
                'name': 'foo',
                'description': 'bar',
                'seeds': [],
            }
            assert ListRecord.from_input() == ListRecord(
                key=None,
                name='foo data',
                description='bar',
                seeds=[{'key': '/books/OL1M'}, {'key': '/books/OL2M'}],
            )

    SEED_TESTS: tuple = (
        ([], []),
        (['OL1M'], [{'key': '/books/OL1M'}]),
        (['OL1M', 'OL2M'], [{'key': '/books/OL1M'}, {'key': '/books/OL2M'}]),
        (['OL1M,OL2M'], [{'key': '/books/OL1M'}, {'key': '/books/OL2M'}]),
    )

    @pytest.mark.parametrize(('seeds', 'expected'), SEED_TESTS)
    def test_from_input_seeds(self, seeds, expected):
        with (
            patch('web.input') as mock_web_input,
            patch('web.data') as mock_web_data,
        ):
            mock_web_data.return_value = b''
            mock_web_input.return_value = {
                'key': None,
                'name': 'foo',
                'description': 'bar',
                'seeds': seeds,
            }
            assert ListRecord.from_input() == ListRecord(
                key=None,
                name='foo',
                description='bar',
                seeds=expected,
            )

    def test_normalize_input_seed(self):
        f = ListRecord.normalize_input_seed

        assert f("/books/OL1M") == {"key": "/books/OL1M"}
        assert f({"key": "/books/OL1M"}) == {"key": "/books/OL1M"}
        assert f("/subjects/love") == "subject:love"
        assert f("subject:love") == "subject:love"

    def test_normalize_input_seed_with_blank_key(self):
        """Test that normalize_input_seed rejects blank keys.

        Blank keys should raise a ValueError instead of
        being accepted and passed through to the database.
        """
        f = ListRecord.normalize_input_seed

        # Blank keys should now raise ValueError
        with pytest.raises(ValueError, match="Seed key cannot be empty"):
            f({'key': ''})

        # Valid keys should still work
        assert f({'key': '/books/OL1M'}) == {'key': '/books/OL1M'}

    def test_from_input_rejects_blank_keys(self):
        """Test that form submission rejects seeds with blank keys.

        Attempting to submit a form with blank keys
        should raise a ValueError during normalization.
        """
        with (
            patch('web.input') as mock_web_input,
            patch('web.data') as mock_web_data,
        ):
            mock_web_data.return_value = b''
            mock_web_input.return_value = {
                'key': None,
                'name': 'foo',
                'description': 'bar',
                'seeds': [
                    {'key': '/books/OL1M'},  # valid
                    {'key': ''},  # blank key - should raise error
                    {'key': '/books/OL2M'},  # valid
                ],
            }
            # Blank keys should now raise ValueError during normalization
            with pytest.raises(ValueError, match="Seed key cannot be empty"):
                ListRecord.from_input()
