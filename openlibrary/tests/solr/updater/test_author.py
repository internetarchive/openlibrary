import httpx
import pytest

from openlibrary.solr import utils as solr_utils
from openlibrary.solr.updater.author import AuthorSolrUpdater
from openlibrary.tests.solr.test_update import FakeDataProvider, make_author


class MockResponse:
    def __init__(self, json_data, status_code=200):
        self.json_data = json_data
        self.status_code = status_code

    def json(self):
        return self.json_data


class TestAuthorUpdater:
    @pytest.mark.asyncio
    async def test_workless_author(self, monkeypatch):
        class MockAsyncClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            async def post(self, *a, **kw):
                return MockResponse(
                    {
                        "facets": {
                            "ratings_count_1": 0.0,
                            "ratings_count_2": 0.0,
                            "ratings_count_3": 0.0,
                            "ratings_count_4": 0.0,
                            "ratings_count_5": 0.0,
                            "subject_facet": {"buckets": []},
                            "place_facet": {"buckets": []},
                            "time_facet": {"buckets": []},
                            "person_facet": {"buckets": []},
                        },
                        "response": {"numFound": 0},
                    }
                )

        monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)
        # Otherwise get_solr_base_url() loads conf/openlibrary.yml, which also sets up infobase's server state
        monkeypatch.setattr(solr_utils, "solr_base_url", "http://solr:8983/solr/openlibrary")
        req, _ = await AuthorSolrUpdater(FakeDataProvider()).update_key(make_author(key="/authors/OL25A", name="Somebody"))
        assert req.deletes == []
        assert len(req.adds) == 1
        assert req.adds[0]["key"] == "/authors/OL25A"
