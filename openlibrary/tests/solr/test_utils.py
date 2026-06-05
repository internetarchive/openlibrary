import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ConnectError, Response

from openlibrary.solr import utils
from openlibrary.solr.utils import SolrUpdateRequest, solr_update
from openlibrary.utils import retry as retry_module


class TestSolrUpdate:
    pytestmark = pytest.mark.asyncio

    def setup_solr_post(self, monkeypatch, response=None, side_effect=None):
        mock_post = AsyncMock(return_value=response, side_effect=side_effect)
        mock_solr = MagicMock()
        mock_solr.async_session.post = mock_post
        monkeypatch.setattr(utils, "get_solr", lambda: mock_solr)
        monkeypatch.setattr(retry_module.asyncio, "sleep", AsyncMock())
        return mock_post

    def sample_response_200(self):
        return Response(
            200,
            request=MagicMock(),
            content=json.dumps(
                {
                    "responseHeader": {
                        "errors": [],
                        "maxErrors": -1,
                        "status": 0,
                        "QTime": 183,
                    }
                }
            ),
        )

    def sample_global_error(self):
        return Response(
            400,
            request=MagicMock(),
            content=json.dumps(
                {
                    "responseHeader": {
                        "errors": [],
                        "maxErrors": -1,
                        "status": 400,
                        "QTime": 76,
                    },
                    "error": {
                        "metadata": [
                            "error-class",
                            "org.apache.solr.common.SolrException",
                            "root-error-class",
                            "org.apache.solr.common.SolrException",
                        ],
                        "msg": "Unknown key 'key' at [14]",
                        "code": 400,
                    },
                }
            ),
        )

    def sample_individual_error(self):
        return Response(
            400,
            request=MagicMock(),
            content=json.dumps(
                {
                    "responseHeader": {
                        "errors": [
                            {
                                "type": "ADD",
                                "id": "/books/OL1M",
                                "message": "[doc=/books/OL1M] missing required field: type",
                            }
                        ],
                        "maxErrors": -1,
                        "status": 0,
                        "QTime": 10,
                    }
                }
            ),
        )

    def sample_response_503(self):
        return Response(
            503,
            request=MagicMock(),
            content=b"<html><body><h1>503 Service Unavailable</h1>",
        )

    async def test_successful_response(self, monkeypatch, monkeytime):
        mock_post = self.setup_solr_post(monkeypatch, response=self.sample_response_200())

        await solr_update(
            SolrUpdateRequest(commit=True),
            solr_base_url="http://localhost:8983/solr/foobar",
        )

        assert mock_post.call_count == 1

    async def test_non_json_solr_503(self, monkeypatch, monkeytime):
        mock_post = self.setup_solr_post(monkeypatch, response=self.sample_response_503())

        await solr_update(
            SolrUpdateRequest(commit=True),
            solr_base_url="http://localhost:8983/solr/foobar",
        )

        assert mock_post.call_count > 1

    async def test_solr_offline(self, monkeypatch, monkeytime):
        mock_post = self.setup_solr_post(monkeypatch, side_effect=ConnectError("", request=MagicMock()))

        await solr_update(
            SolrUpdateRequest(commit=True),
            solr_base_url="http://localhost:8983/solr/foobar",
        )

        assert mock_post.call_count > 1

    async def test_invalid_solr_request(self, monkeypatch, monkeytime):
        mock_post = self.setup_solr_post(monkeypatch, response=self.sample_global_error())

        await solr_update(
            SolrUpdateRequest(commit=True),
            solr_base_url="http://localhost:8983/solr/foobar",
        )

        assert mock_post.call_count == 1

    async def test_bad_apple_in_solr_request(self, monkeypatch, monkeytime):
        mock_post = self.setup_solr_post(monkeypatch, response=self.sample_individual_error())

        await solr_update(
            SolrUpdateRequest(commit=True),
            solr_base_url="http://localhost:8983/solr/foobar",
        )

        assert mock_post.call_count == 1

    async def test_other_non_ok_status(self, monkeypatch, monkeytime):
        mock_post = self.setup_solr_post(monkeypatch, response=Response(500, request=MagicMock(), content="{}"))

        await solr_update(
            SolrUpdateRequest(commit=True),
            solr_base_url="http://localhost:8983/solr/foobar",
        )

        assert mock_post.call_count > 1
