import asyncio
from unittest.mock import MagicMock

import pytest
import web
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from openlibrary.utils import olmemcache, saturation_metrics


def sample(name, labels=None):
    return REGISTRY.get_sample_value(name, labels or {})


def test_fastapi_counts_requests_in_flight():
    seen = []
    app = FastAPI()

    @app.get("/x")
    async def x():
        seen.append(sample("ol_http_requests_in_flight", {"app": "fastapi"}))
        return {}

    app.add_middleware(saturation_metrics.InFlightMiddleware)
    before = sample("ol_http_requests_in_flight", {"app": "fastapi"}) or 0
    assert TestClient(app).get("/x").status_code == 200
    assert seen == [before + 1]
    assert sample("ol_http_requests_in_flight", {"app": "fastapi"}) == before


def test_fastapi_in_flight_drops_when_the_handler_fails():
    app = FastAPI()

    @app.get("/boom")
    async def boom():
        raise RuntimeError("boom")

    app.add_middleware(saturation_metrics.InFlightMiddleware)
    before = sample("ol_http_requests_in_flight", {"app": "fastapi"}) or 0
    with pytest.raises(RuntimeError):
        TestClient(app).get("/boom")
    assert sample("ol_http_requests_in_flight", {"app": "fastapi"}) == before


def test_webpy_counts_requests_in_flight():
    seen = []

    class thing:
        def GET(self):
            seen.append(sample("ol_http_requests_in_flight", {"app": "webpy"}))
            raise web.notfound()

    app = web.application(("/thing", "thing"), {"thing": thing})
    saturation_metrics.instrument_webpy(app)
    before = sample("ol_http_requests_in_flight", {"app": "webpy"}) or 0
    app.request("/thing")
    assert seen == [before + 1]
    assert sample("ol_http_requests_in_flight", {"app": "webpy"}) == before


def test_sample_once_records_pools(monkeypatch):
    monkeypatch.setattr(saturation_metrics.anyio.to_thread, "current_default_thread_limiter", lambda: MagicMock(borrowed_tokens=3))
    saturation_metrics.sample_once({"requests_waiting": 4, "pool_size": 2, "pool_available": 1})
    assert sample("ol_threadpool_in_use") == 3
    assert sample("ol_async_db_pool_requests_waiting") == 4
    assert sample("ol_async_db_pool_size") == 2
    assert sample("ol_async_db_pool_available") == 1


@pytest.mark.asyncio
async def test_sampling_records_event_loop_lag():
    before = sample("ol_event_loop_lag_seconds_count") or 0
    async with saturation_metrics.sampling():
        await asyncio.sleep(saturation_metrics.SAMPLE_INTERVAL * 3)
    assert sample("ol_event_loop_lag_seconds_count") >= before + 1


def test_memcache_calls_are_timed(monkeypatch):
    client = olmemcache.Client.__new__(olmemcache.Client)
    client._client = MagicMock()
    client._client.get.return_value = None
    client.compress = client.decompress = lambda v: v
    before = sample("ol_memcache_call_seconds_count", {"op": "get"}) or 0
    assert client.get("k") is None
    client.set("k", "v")
    assert sample("ol_memcache_call_seconds_count", {"op": "get"}) == before + 1
    assert sample("ol_memcache_call_seconds_count", {"op": "set"}) >= 1
