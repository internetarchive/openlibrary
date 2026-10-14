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

import httpx
import web

from infogami.utils import stats

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator


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
    except Exception:  # not BaseException: a cancelled request isn't a backend failure
        call.failed = True
        raise
    finally:
        timings.record(name, time.perf_counter() - started, call.failed)


class _HttpCall:
    """One request's timing, recorded once: when its response body is closed, or on error."""

    def __init__(self, timings: RequestTimings, name: str) -> None:
        self.timings = timings
        self.name = name
        self.started = time.perf_counter()
        self.failed = False
        self._recorded = False

    @classmethod
    def start(cls, request: httpx.Request, default_name: str) -> _HttpCall | None:
        if (timings := _current.get()) is None:
            return None
        return cls(timings, request.extensions.get("server_timing", default_name))

    def finish(self, failed: bool = False) -> None:
        self.failed |= failed
        if not self._recorded:
            self._recorded = True
            self.timings.record(self.name, time.perf_counter() - self.started, self.failed)

    def got_response(self, response: httpx.Response) -> bool:
        """Note the response; True if its body is still to be read, so needs wrapping."""
        self.failed = response.is_server_error
        if response.is_closed:  # body was already in memory, e.g. from httpx.MockTransport
            self.finish()
            return False
        return True


class TimedTransport(httpx.AsyncBaseTransport):
    """Times every request an ``httpx.AsyncClient`` sends, e.g.
    ``httpx.AsyncClient(transport=TimedTransport("solr"))``.

    Requests are timed as ``name`` unless they name themselves, e.g.
    ``client.get(url, extensions={"server_timing": "ia-loans"})``.

    Each timing runs until the response body is closed, so it includes the download;
    httpx reads the body only after the transport returns. A response streamed with
    ``stream=True`` and never closed isn't recorded. 5xx responses and transport
    errors (timeouts, refused connections) count as failed; each redirect is its own call.
    """

    def __init__(self, name: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.name = name
        self._transport = transport or httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if (call := _HttpCall.start(request, self.name)) is None:
            return await self._transport.handle_async_request(request)
        try:
            response = await self._transport.handle_async_request(request)
        except Exception:
            call.finish(failed=True)
            raise
        if call.got_response(response):
            assert isinstance(response.stream, httpx.AsyncByteStream)
            response.stream = _TimedAsyncStream(response.stream, call)
        return response

    async def aclose(self) -> None:
        await self._transport.aclose()


class TimedSyncTransport(httpx.BaseTransport):
    """``TimedTransport`` for a sync ``httpx.Client``."""

    def __init__(self, name: str, transport: httpx.BaseTransport | None = None) -> None:
        self.name = name
        self._transport = transport or httpx.HTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if (call := _HttpCall.start(request, self.name)) is None:
            return self._transport.handle_request(request)
        try:
            response = self._transport.handle_request(request)
        except Exception:
            call.finish(failed=True)
            raise
        if call.got_response(response):
            assert isinstance(response.stream, httpx.SyncByteStream)
            response.stream = _TimedSyncStream(response.stream, call)
        return response

    def close(self) -> None:
        self._transport.close()


class _TimedAsyncStream(httpx.AsyncByteStream):
    def __init__(self, stream: httpx.AsyncByteStream, call: _HttpCall) -> None:
        self._stream = stream
        self._call = call

    async def __aiter__(self) -> AsyncIterator[bytes]:
        try:
            async for chunk in self._stream:
                yield chunk
        except Exception:
            self._call.failed = True
            raise

    async def aclose(self) -> None:
        try:
            await self._stream.aclose()
        finally:
            self._call.finish()


class _TimedSyncStream(httpx.SyncByteStream):
    def __init__(self, stream: httpx.SyncByteStream, call: _HttpCall) -> None:
        self._stream = stream
        self._call = call

    def __iter__(self) -> Iterator[bytes]:
        try:
            yield from self._stream
        except Exception:
            self._call.failed = True
            raise

    def close(self) -> None:
        try:
            self._stream.close()
        finally:
            self._call.finish()


@contextmanager
def timed_render() -> Iterator[None]:
    """Time template rendering as ``render``. Nested renders count once, in the outermost.

    Includes any Solr/DB/etc. calls the templates make, which also show under their own names.
    """
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
