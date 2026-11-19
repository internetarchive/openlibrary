import json
from typing import Any, cast
from unittest.mock import patch

import pytest

from openlibrary.core.lists.model import AnnotatedSeedDict, List, ThingReferenceDict
from openlibrary.plugins.openlibrary.lists import (
    ListRecord,
    _list_record_with_added_seeds,
    _seed_identifier,
)


class FakeSeed:
    def __init__(self, seed):
        self.seed = seed

    def to_json(self):
        return self.seed


class FakeList:
    key = '/people/openlibrary/lists/OL1L'
    name = 'Favorites'
    description = 'Existing description'
    comment_ = 'Existing comment'

    def get_seeds(self):
        return [
            FakeSeed({'key': '/works/OL1W'}),
            FakeSeed('subject:love'),
            FakeSeed({'thing': {'key': '/books/OL3M'}, 'notes': 'Keep my note'}),
        ]


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
        ):
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

    def test_seed_identifier(self):
        assert _seed_identifier('subject:love') == 'subject:love'
        assert _seed_identifier(cast(ThingReferenceDict, {'key': '/works/OL1W'})) == '/works/OL1W'
        assert _seed_identifier(cast(AnnotatedSeedDict, {'thing': {'key': '/books/OL1M'}})) == '/books/OL1M'

    def test_list_record_with_added_seeds_flattens_and_deduplicates(self):
        list_record = _list_record_with_added_seeds(
            cast(List, FakeList()),
            cast(Any, [
                'OL1W, OL2W',
                ('/subjects/love', {'key': '/books/OL3M'}, '/books/OL4M'),
            ]),
        )

        assert list_record == ListRecord(
            key='/people/openlibrary/lists/OL1L',
            name='Favorites',
            description='Existing description',
            seeds=[
                {'key': '/works/OL1W'},
                'subject:love',
                {'thing': {'key': '/books/OL3M'}, 'notes': 'Keep my note'},
                {'key': '/works/OL2W'},
                {'key': '/books/OL4M'},
            ],
            comment_='Existing comment',
        )
