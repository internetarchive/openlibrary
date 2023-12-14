import httpx
import pytest
from openlibrary.solr import update_work
from openlibrary.solr.updater.author import AuthorSolrUpdater
from openlibrary.tests.solr.test_update_work import FakeDataProvider, make_author


class MockResponse:
    def __init__(self, json_data, status_code=200):
        self.json_data = json_data
        self.status_code = status_code

    def json(self):
        return self.json_data


class TestAuthorUpdater:
    @classmethod
    def setup_class(cls):
        update_work.data_provider = FakeDataProvider()

    @pytest.mark.asyncio()
    async def test_workless_author(self, monkeypatch):
        class MockAsyncClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            async def get(self, url, params):
                return MockResponse(
                    {
                        "facet_counts": {
                            "facet_fields": {
                                "place_facet": [],
                                "person_facet": [],
                                "subject_facet": [],
                                "time_facet": [],
                            }
                        },
                        "response": {"numFound": 0},
                    }
                )

        monkeypatch.setattr(httpx, 'AsyncClient', MockAsyncClient)
        req, _ = await AuthorSolrUpdater(FakeDataProvider()).update_key(
            make_author(key='/authors/OL25A', name='Somebody')
        )
        assert req.deletes == []
        assert len(req.adds) == 1
        assert req.adds[0]['key'] == "/authors/OL25A"
