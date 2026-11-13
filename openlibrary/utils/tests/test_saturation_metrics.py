import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from openlibrary.utils import olmemcache, saturation_metrics


def sample(name, labels=None):
    return REGISTRY.get_sample_value(name, labels or {}) or 0


def test_in_flight_counts_requests_until_they_end():
    seen = []
    app = FastAPI()

    @app.get("/ok")
    async def ok():
        seen.append(sample("ol_http_requests_in_flight"))
        return {}

    @app.get("/boom")
    async def boom():
        raise RuntimeError("boom")

    app.add_middleware(saturation_metrics.InFlightMiddleware)
    client = TestClient(app)
    before = sample("ol_http_requests_in_flight")
    assert client.get("/ok").status_code == 200
    with pytest.raises(RuntimeError):
        client.get("/boom")
    assert seen == [before + 1]
    assert sample("ol_http_requests_in_flight") == before


def test_sample_pools(monkeypatch):
    monkeypatch.setattr(saturation_metrics.anyio.to_thread, "current_default_thread_limiter", lambda: MagicMock(borrowed_tokens=3))
    monkeypatch.setattr(saturation_metrics.async_db, "pool_stats", lambda: {"requests_waiting": 4, "pool_size": 2, "pool_available": 1})
    saturation_metrics.sample_pools()
    assert sample("ol_threadpool_in_use") == 3
    assert sample("ol_async_db_pool_requests_waiting") == 4
    assert sample("ol_async_db_pool_size") == 2
    assert sample("ol_async_db_pool_available") == 1


@pytest.mark.asyncio
async def test_sampling_records_event_loop_lag():
    before = sample("ol_event_loop_lag_seconds_count")
    async with saturation_metrics.sampling():
        await asyncio.sleep(saturation_metrics.SAMPLE_INTERVAL * 3)
    assert sample("ol_event_loop_lag_seconds_count") > before


def test_memcache_calls_are_timed():
    client = olmemcache.Client.__new__(olmemcache.Client)
    client._client = MagicMock()
    client._client.get.return_value = None
    client.compress = lambda v: v
    before = sample("ol_memcache_call_seconds_count", {"op": "get"}), sample("ol_memcache_call_seconds_count", {"op": "set"})
    assert client.get("k") is None
    client.set("k", "v")
    after = sample("ol_memcache_call_seconds_count", {"op": "get"}), sample("ol_memcache_call_seconds_count", {"op": "set"})
    assert after == (before[0] + 1, before[1] + 1)
