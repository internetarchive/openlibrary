"""Prometheus metrics for how close FastAPI is to saturation, for sizing and autoscaling.

* ``ol_event_loop_lag_seconds``: how late the event loop wakes a task that asked for a 0.1s sleep.
  Anything blocking the loop (sync calls in ``async def`` handlers, e.g. memcache) shows up here.
* ``ol_http_requests_in_flight``: requests being handled right now.
* ``ol_threadpool_in_use``: threads busy in anyio's default thread pool, which runs FastAPI's sync handlers.
* ``ol_async_db_pool_*``: the async DB pool's connections and the requests waiting for one.

Memcache call time, ``ol_memcache_call_seconds{op}``, is recorded in ``openlibrary/utils/olmemcache.py``.
"""

from __future__ import annotations

import asyncio
import contextlib
from timeit import default_timer
from typing import TYPE_CHECKING

import anyio.to_thread
from prometheus_client import Gauge, Histogram

from openlibrary.core import async_db

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

SAMPLE_INTERVAL = 0.1  # seconds
# Lag is normally under a millisecond; the upper buckets catch a blocked loop
LAG_BUCKETS = (0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5)

EVENT_LOOP_LAG = Histogram("ol_event_loop_lag_seconds", "How much later than requested the event loop woke a task.", buckets=LAG_BUCKETS)
# "livesum": in multiprocess mode, the sum over live workers (prometheus_multiprocess deletes dead workers' files)
IN_FLIGHT = Gauge("ol_http_requests_in_flight", "Requests being handled right now.", multiprocess_mode="livesum")
THREADPOOL_IN_USE = Gauge("ol_threadpool_in_use", "Threads busy in anyio's default thread pool.", multiprocess_mode="livesum")
DB_POOL_REQUESTS_WAITING = Gauge("ol_async_db_pool_requests_waiting", "Requests waiting for an async DB pool connection.", multiprocess_mode="livesum")
DB_POOL_SIZE = Gauge("ol_async_db_pool_size", "Connections currently in the async DB pool.", multiprocess_mode="livesum")
DB_POOL_AVAILABLE = Gauge("ol_async_db_pool_available", "Idle connections in the async DB pool.", multiprocess_mode="livesum")


class InFlightMiddleware:
    """ASGI middleware counting the HTTP requests in flight, until their responses are sent."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        with IN_FLIGHT.track_inprogress():
            await self.app(scope, receive, send)


def sample_pools() -> None:
    """Record the thread pool and DB pool gauges."""
    THREADPOOL_IN_USE.set(anyio.to_thread.current_default_thread_limiter().borrowed_tokens)
    if stats := async_db.pool_stats():
        DB_POOL_REQUESTS_WAITING.set(stats["requests_waiting"])
        DB_POOL_SIZE.set(stats["pool_size"])
        DB_POOL_AVAILABLE.set(stats["pool_available"])


async def _sample_forever() -> None:
    while True:
        start = default_timer()
        await asyncio.sleep(SAMPLE_INTERVAL)
        EVENT_LOOP_LAG.observe(max(default_timer() - start - SAMPLE_INTERVAL, 0.0))
        sample_pools()


@contextlib.asynccontextmanager
async def sampling():
    """Measure the event loop lag, and sample the pools, every ``SAMPLE_INTERVAL`` during the block. For FastAPI's lifespan."""
    task = asyncio.create_task(_sample_forever(), name="saturation-metrics")
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
