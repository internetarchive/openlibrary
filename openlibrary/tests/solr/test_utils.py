from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ConnectError, Response

from openlibrary.solr import utils
from openlibrary.solr.utils import SolrUpdateRequest, solr_update


class TestSolrUpdate:
    pytestmark = pytest.mark.asyncio

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
            200,
            request=MagicMock(),
            content=json.dumps(
                {
                    "responseHeader": {
                        "errors": [
                            {
                                "type": "ADD",
                                "id": "/works/OL16086453W",
                                "message": "ERROR: [doc=/works/OL16086453W] unknown field 'foo'",
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
        mock_post = AsyncMock(return_value=self.sample_response_200())
        monkeypatch.setattr(utils.httpx_client, "post", mock_post)

        await solr_update(
            SolrUpdateRequest(commit=True),
            solr_base_url="http://localhost:8983/solr/foobar",
        )

        assert mock_post.call_count == 1

    async def test_non_json_solr_503(self, monkeypatch, monkeytime):
        mock_post = AsyncMock(return_value=self.sample_response_503())
        monkeypatch.setattr(utils.httpx_client, "post", mock_post)

        await solr_update(
            SolrUpdateRequest(commit=True),
            solr_base_url="http://localhost:8983/solr/foobar",
        )

        assert mock_post.call_count > 1

    async def test_solr_offline(self, monkeypatch, monkeytime):
        mock_post = AsyncMock(side_effect=ConnectError("", request=MagicMock()))
        monkeypatch.setattr(utils.httpx_client, "post", mock_post)

        await solr_update(
            SolrUpdateRequest(commit=True),
            solr_base_url="http://localhost:8983/solr/foobar",
        )

        assert mock_post.call_count > 1

    async def test_invalid_solr_request(self, monkeypatch, monkeytime):
        mock_post = AsyncMock(return_value=self.sample_global_error())
        monkeypatch.setattr(utils.httpx_client, "post", mock_post)

        await solr_update(
            SolrUpdateRequest(commit=True),
            solr_base_url="http://localhost:8983/solr/foobar",
        )

        assert mock_post.call_count == 1

    async def test_bad_apple_in_solr_request(self, monkeypatch, monkeytime):
        mock_post = AsyncMock(return_value=self.sample_individual_error())
        monkeypatch.setattr(utils.httpx_client, "post", mock_post)

        await solr_update(
            SolrUpdateRequest(commit=True),
            solr_base_url="http://localhost:8983/solr/foobar",
        )

        assert mock_post.call_count == 1

    async def test_other_non_ok_status(self, monkeypatch, monkeytime):
        mock_post = AsyncMock(return_value=Response(500, request=MagicMock(), content="{}"))
        monkeypatch.setattr(utils.httpx_client, "post", mock_post)

        await solr_update(
            SolrUpdateRequest(commit=True),
            solr_base_url="http://localhost:8983/solr/foobar",
        )

        assert mock_post.call_count > 1
