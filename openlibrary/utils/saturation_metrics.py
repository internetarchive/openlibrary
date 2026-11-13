"""Prometheus metrics for how close the servers are to saturation, for sizing and autoscaling.

* ``ol_http_requests_in_flight{app}``: requests being handled right now, by web.py and FastAPI.
* ``ol_event_loop_lag_seconds``: how late FastAPI's event loop wakes a task that asked for a 0.1s sleep.
  Anything blocking the loop (sync calls in ``async def`` handlers, e.g. memcache) shows up here.
* ``ol_threadpool_in_use``: threads busy in anyio's default thread pool, which runs FastAPI's sync handlers.
* ``ol_memcache_call_seconds{op}``: time in memcache calls (a sync client, so each one blocks its thread or the event loop).
* ``ol_async_db_pool_*``: the async DB pool's connections and the requests waiting for one.
"""

from __future__ import annotations

import asyncio
import contextlib
from timeit import default_timer
from typing import TYPE_CHECKING

import anyio.to_thread
from prometheus_client import Gauge, Histogram

if TYPE_CHECKING:
    import web
    from starlette.types import ASGIApp, Receive, Scope, Send

SAMPLE_INTERVAL = 0.1  # seconds
# Lag is normally under a millisecond; the upper buckets catch a blocked loop
LAG_BUCKETS = (0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5)

MEMCACHE_BUCKETS = (0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5)

# "livesum": a gauge's value in a multiprocess server (web.py's gunicorn workers) is the sum over live workers
IN_FLIGHT = Gauge("ol_http_requests_in_flight", "Requests being handled right now.", ("app",), multiprocess_mode="livesum")
EVENT_LOOP_LAG = Histogram("ol_event_loop_lag_seconds", "How much later than requested the event loop woke a task.", buckets=LAG_BUCKETS)
MEMCACHE_CALL = Histogram("ol_memcache_call_seconds", "Duration of memcache calls, by operation.", ("op",), buckets=MEMCACHE_BUCKETS)
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
        with IN_FLIGHT.labels("fastapi").track_inprogress():
            await self.app(scope, receive, send)


class WebPyInFlightProcessor:
    """web.py processor counting the requests in flight."""

    def __call__(self, handler):
        with IN_FLIGHT.labels("webpy").track_inprogress():
            return handler()


def instrument_webpy(app: web.application) -> None:
    app.processors.insert(0, WebPyInFlightProcessor())


def sample_once(pool_stats: dict[str, int] | None) -> None:
    """Record the thread pool and DB pool gauges."""
    THREADPOOL_IN_USE.set(anyio.to_thread.current_default_thread_limiter().borrowed_tokens)
    if pool_stats:
        DB_POOL_REQUESTS_WAITING.set(pool_stats.get("requests_waiting", 0))
        DB_POOL_SIZE.set(pool_stats.get("pool_size", 0))
        DB_POOL_AVAILABLE.set(pool_stats.get("pool_available", 0))


async def sample_forever() -> None:
    """Measure the event loop lag, and sample the other gauges, every ``SAMPLE_INTERVAL``. Run as a background task."""
    from openlibrary.core import async_db  # noqa: PLC0415

    while True:
        start = default_timer()
        await asyncio.sleep(SAMPLE_INTERVAL)
        EVENT_LOOP_LAG.observe(max(default_timer() - start - SAMPLE_INTERVAL, 0.0))
        sample_once(async_db.pool_stats())


@contextlib.asynccontextmanager
async def sampling():
    """Run ``sample_forever`` for the block, for FastAPI's lifespan."""
    task = asyncio.create_task(sample_forever(), name="saturation-metrics")
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
