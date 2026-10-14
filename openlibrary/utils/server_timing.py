"""Per-request backend timings for the ``Server-Timing`` response header (FastAPI only).

https://www.w3.org/TR/server-timing/ -- shown in the browser devtools Network tab.

Timings live in a ContextVar, which FastAPI's threadpool and ``async_bridge`` copy,
so sync code called from a request records into the same place. Outside a request
everything here is a no-op.

Metric names are used as given, so keep them HTTP tokens and avoid ``total``,
``sentry-trace`` and ``baggage`` (Sentry's browser SDK reads those two).
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

import web

from infogami.utils import stats

if TYPE_CHECKING:
    from collections.abc import Iterator


class RequestTimings:
    """(count, seconds, failures) per metric name, for one request. Thread-safe."""

    def __init__(self) -> None:
        self.start = time.perf_counter()
        self._lock = threading.Lock()
        self._metrics: dict[str, list[float]] = {}
        self._open: dict[int, list[tuple[str | None, float]]] = {}  # infogami stats.begin() calls, per thread

    def record(self, name: str, seconds: float, failed: bool = False) -> None:
        with self._lock:
            metric = self._metrics.setdefault(name, [0, 0.0, 0])
            metric[0] += 1
            metric[1] += seconds
            metric[2] += failed

    def snapshot(self) -> dict[str, tuple[int, float, int]]:
        with self._lock:
            return {name: (int(count), seconds, int(failures)) for name, (count, seconds, failures) in self._metrics.items()}

    def _begin(self, name: str | None) -> None:
        with self._lock:
            self._open.setdefault(threading.get_ident(), []).append((name, time.perf_counter()))

    def _end(self) -> None:
        with self._lock:
            if not (stack := self._open.get(threading.get_ident())):
                return
            name, started = stack.pop()
        if name is not None:
            self.record(name, time.perf_counter() - started)


_current: ContextVar[RequestTimings | None] = ContextVar("server_timing", default=None)
_rendering: ContextVar[bool] = ContextVar("server_timing_rendering", default=False)


def start_request() -> tuple[RequestTimings, object]:
    timings = RequestTimings()
    return timings, _current.set(timings)


def end_request(token) -> None:
    _current.reset(token)


class Call:
    """Set ``failed`` for errors that don't raise, e.g. a 5xx response."""

    failed = False


@contextmanager
def timed(name: str) -> Iterator[Call]:
    """Time the block (sync or async) as ``name``; it counts as failed if it raises."""
    call = Call()
    if (timings := _current.get()) is None:
        yield call
        return
    started = time.perf_counter()
    try:
        yield call
    except BaseException:
        call.failed = True
        raise
    finally:
        timings.record(name, time.perf_counter() - started, call.failed)


@contextmanager
def timed_render() -> Iterator[None]:
    """Time template rendering as ``render``. Nested renders count once, in the outermost."""
    if _current.get() is None or _rendering.get():
        yield
        return
    token = _rendering.set(True)
    try:
        with timed("render"):
            yield
    finally:
        _rendering.reset(token)


def format_header(timings: RequestTimings) -> str:
    """e.g. ``total;dur=294.1, solr;dur=57.0;desc="2 calls (1 failed)"``"""
    parts = [f"total;dur={(time.perf_counter() - timings.start) * 1000:.1f}"]
    for name, (count, seconds, failures) in sorted(timings.snapshot().items()):
        desc = f"{count} {'call' if count == 1 else 'calls'}" + (f" ({failures} failed)" if failures else "")
        parts.append(f'{name};dur={seconds * 1000:.1f};desc="{desc}"')
    return ", ".join(parts)


def send_to_statsd(timings: RequestTimings) -> None:
    """Send the request's timings to Graphite, like web.py's X-OL-Stats hook does."""
    from openlibrary.core import stats as statsd  # noqa: PLC0415

    statsd.put("ol.fastapi.total", (time.perf_counter() - timings.start) * 1000)
    for name, (_, seconds, failures) in timings.snapshot().items():
        statsd.put(f"ol.fastapi.{name}", seconds * 1000)
        if failures:
            statsd.increment(f"ol.fastapi.{name}.failed", n=failures)


def _infogami_metric_name(name: str) -> str | None:
    if name in ("db", "archive.org"):  # timed directly instead
        return None
    return name.split(".", maxsplit=1)[0]  # "memcache.get" -> "memcache"


_bridge_installed = False


def install_legacy_bridge() -> None:
    """Time legacy code during FastAPI requests: infogami's ``stats.begin()/end()``
    (infobase, memcache), which would otherwise pile up in thread-local ``web.ctx``,
    and every web.py DB query as ``db``. infogami's ``end(error=True)`` is ignored:
    in-process infobase reports ordinary not-founds that way."""
    global _bridge_installed
    if _bridge_installed:
        return
    original_begin, original_end = stats.begin, stats.end
    original_db_execute = web.db.DB._db_execute

    def begin(name, **kw):
        if (timings := _current.get()) is None:
            return original_begin(name, **kw)
        timings._begin(_infogami_metric_name(name))

    def end(**kw):
        if (timings := _current.get()) is None:
            return original_end(**kw)
        timings._end()

    def _db_execute(self, cur, sql_query):
        with timed("db"):
            return original_db_execute(self, cur, sql_query)

    stats.begin, stats.end = begin, end
    web.db.DB._db_execute = _db_execute
    _bridge_installed = True
