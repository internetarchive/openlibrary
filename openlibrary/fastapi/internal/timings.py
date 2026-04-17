"""
Helpers for recording and reporting timing information in FastAPI handlers. The recorded
times are visible in your browser's dev tools. Click on the request in the Networks panel,
and then select the "Timing" tab to see a breakdown of the different timing entries recorded by
the server.

To use, add the `@monitor_as_server_timing('name')` decorator on any function you want to
track. The argument is the name of the timing entry that will appear in dev tools.
"""

import asyncio
import functools
import time
from collections.abc import Callable
from contextvars import ContextVar

from fastapi import Request

# Per-request storage for timing entries
_timings: ContextVar[dict[str, float] | None] = ContextVar("_timings", default=None)


def record_timing(name: str, duration_ms: float) -> None:
    """Add a timing entry if we're inside a tracked request."""
    if (timings := _timings.get()) is not None:
        timings[name] = duration_ms


def monitor_as_server_timing(name: str):
    """Decorator that measures execution time and records it to Server-Timing."""

    def decorator(func: Callable):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                record_timing(name, duration_ms)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                record_timing(name, duration_ms)

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


def build_server_timing_header(timings: dict[str, float]) -> str:
    """Format timings as a Server-Timing header value."""
    return ", ".join(f"{name};dur={duration:.1f}" for name, duration in timings.items())


async def server_timing_middleware(request: Request, call_next):
    if request.query_params.get("_timings") != "true":
        return await call_next(request)

    # Initialize a fresh timing dict for this request
    token = _timings.set({})
    try:
        response = await call_next(request)
    finally:
        timings = _timings.get()
        _timings.reset(token)

    if timings:
        response.headers["Server-Timing"] = build_server_timing_header(timings)

    return response
