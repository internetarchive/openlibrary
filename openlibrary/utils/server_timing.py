"""Per-request backend timings for the ``Server-Timing`` response header (FastAPI only).

https://www.w3.org/TR/server-timing/ -- shown in the browser devtools Network tab.

Timings live in a ContextVar, which FastAPI's threadpool and ``async_bridge`` copy,
so sync code called from a request records into the same place. Outside a request
everything here is a no-op.

Metric names are used as given, so keep them HTTP tokens and avoid ``total``,
``sentry-trace`` and ``baggage`` (Sentry's browser SDK reads those two).
"""

from __future__ import annotations

import asyncio
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

import httpx
import web

from infogami.utils import stats
from openlibrary.utils.async_utils import AsyncBridge, async_bridge

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator


class RequestTimings:
    """(count, seconds, failures) per metric name, for one request. Thread-safe."""

    def __init__(self) -> None:
        self.start = time.perf_counter()
        self._lock = threading.Lock()
        self._metrics: dict[str, list[float]] = {}
        self._open: dict[int, list[tuple[str | None, float]]] = {}  # infogami stats.begin() calls, per thread
        self._blocking: dict[str, list[float]] = {}  # source -> [count, seconds]

    def record_blocking(self, source: str, seconds: float) -> None:
        """Sync I/O that held the event loop: counts toward ``blocking``, broken down by source."""
        self.record("blocking", seconds)
        with self._lock:
            entry = self._blocking.setdefault(source, [0, 0.0])
            entry[0] += 1
            entry[1] += seconds

    def blocking_breakdown(self) -> list[tuple[str, int, float]]:
        with self._lock:
            return sorted(((source, int(count), seconds) for source, (count, seconds) in self._blocking.items()), key=lambda b: -b[2])

    def record(self, name: str, seconds: float, failed: bool = False, count: int = 1) -> None:
        with self._lock:
            metric = self._metrics.setdefault(name, [0, 0.0, 0])
            metric[0] += count
            metric[1] += seconds
            metric[2] += failed

    def snapshot(self) -> dict[str, tuple[int, float, int]]:
        with self._lock:
            return {name: (int(count), seconds, int(failures)) for name, (count, seconds, failures) in self._metrics.items()}

    def _begin(self, name: str | None) -> None:
        with self._lock:
            self._open.setdefault(threading.get_ident(), []).append((name, time.perf_counter()))

    def _inside(self, name: str) -> bool:
        with self._lock:
            return any(open_name == name for open_name, _ in self._open.get(threading.get_ident(), ()))

    def _end(self) -> None:
        with self._lock:
            if not (stack := self._open.get(threading.get_ident())):
                return
            name, started = stack.pop()
        if name is not None:
            self.record(name, time.perf_counter() - started)


_current: ContextVar[RequestTimings | None] = ContextVar("server_timing", default=None)
_rendering: ContextVar[_Render | None] = ContextVar("server_timing_rendering", default=None)


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
            with _blocking(self.name):
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


class _Render:
    """The template render in progress: its engine's metric name, and when it last (re)started."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.started = time.perf_counter()


@contextmanager
def timed_render(name: str) -> Iterator[None]:
    """Time template rendering as ``name``: ``render-jinja`` or ``render-templetor``.

    The engines nest in each other, so each records only its own time: rendering
    the other engine pauses the outer one's timer, and the two add up to the total
    render time. A render nested in the same engine counts once, in the outermost.

    Includes any Solr/DB/etc. calls the templates make, which also show under their own names.
    """
    outer = _rendering.get()
    if (timings := _current.get()) is None or (outer is not None and outer.name == name):
        yield
        return
    render = _Render(name)
    if outer is not None:  # pause the other engine
        timings.record(outer.name, render.started - outer.started, count=0)
    token = _rendering.set(render)
    failed = False
    try:
        yield
    except Exception:
        failed = True
        raise
    finally:
        _rendering.reset(token)
        ended = time.perf_counter()
        timings.record(name, ended - render.started, failed)
        if outer is not None:  # resume it
            outer.started = ended


def format_header(timings: RequestTimings) -> str:
    """e.g. ``total;dur=294.1, solr;dur=57.0;desc="2 calls (1 failed)"``"""
    parts = [f"total;dur={(time.perf_counter() - timings.start) * 1000:.1f}"]
    for name, (count, seconds, failures) in sorted(timings.snapshot().items()):
        desc = f"{count} {'call' if count == 1 else 'calls'}" + (f" ({failures} failed)" if failures else "")
        if name == "blocking":
            desc = ", ".join(f"{source} {secs * 1000:.0f}ms ({n})" for source, n, secs in timings.blocking_breakdown())
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
    for source, _, seconds in timings.blocking_breakdown():
        statsd.put(f"ol.fastapi.blocking.{source}", seconds * 1000)


def _infogami_metric_name(name: str) -> str | None:
    if name in ("db", "archive.org"):  # timed directly instead
        return None
    return name.split(".", maxsplit=1)[0]  # "memcache.get" -> "memcache"


_bridge_installed = False


def _on_event_loop() -> bool:
    """On a request's event loop (an async route), not in the threadpool or the bridge thread."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return threading.current_thread() is not async_bridge._thread


# Sync calls in progress on this thread: (source, started, counts toward blocking).
_sync_calls = threading.local()


def _blocking_start(source: str | None) -> None:
    stack = _sync_calls.__dict__.setdefault("stack", [])
    # Only the outermost named call counts, so an infobase read's own SQL isn't counted twice.
    counts = source is not None and _current.get() is not None and not any(s[0] for s in stack) and _on_event_loop()
    stack.append((source, time.perf_counter(), counts))


def _blocking_end() -> None:
    if not (stack := getattr(_sync_calls, "stack", None)):
        return
    source, started, counts = stack.pop()
    if counts and (timings := _current.get()) is not None:
        timings.record_blocking(source, time.perf_counter() - started)


@contextmanager
def _blocking(source: str) -> Iterator[None]:
    """Count sync I/O that runs on the event loop toward ``blocking``."""
    _blocking_start(source)
    try:
        yield
    finally:
        _blocking_end()


def install_legacy_bridge() -> None:
    """Time legacy code during FastAPI requests: infogami's ``stats.begin()/end()``
    (infobase, memcache), which would otherwise pile up in thread-local ``web.ctx``;
    every web.py DB query as ``db-legacy`` (except infobase's own in-process reads, which
    are part of ``infobase``; the async pool reports ``db``); and every Templetor template
    or macro render as ``render-templetor``, whichever helper called it.

    Sync I/O that runs on the event loop (an async route) also counts toward ``blocking``,
    broken down by source in its description: legacy DB, infobase, memcache, sync HTTP,
    and ``async_bridge.run()`` waits. Only the outermost call counts, so nothing is
    counted twice; awaited I/O never counts.

    infogami's ``end(error=True)`` is ignored: in-process infobase reports ordinary
    not-founds that way."""
    global _bridge_installed
    if _bridge_installed:
        return
    original_begin, original_end = stats.begin, stats.end
    original_db_execute = web.db.DB._db_execute
    original_template_call = web.template.Template.__call__

    original_bridge_run = AsyncBridge.run

    def begin(name, **kw):
        if (timings := _current.get()) is None:
            return original_begin(name, **kw)
        metric = _infogami_metric_name(name)
        timings._begin(metric)
        _blocking_start(metric)

    def end(**kw):
        if (timings := _current.get()) is None:
            return original_end(**kw)
        timings._end()
        _blocking_end()

    def _db_execute(self, cur, sql_query):
        timings = _current.get()
        if timings is not None and timings._inside("infobase"):
            # Infobase's in-process reads (hybrid connection): already timed as infobase.
            return original_db_execute(self, cur, sql_query)
        with _blocking("db-legacy"), timed("db-legacy"):
            return original_db_execute(self, cur, sql_query)

    def bridge_run(self, coro):
        # Sync code on the event loop waiting for async_bridge (e.g. a bridged Solr query).
        with _blocking("bridge"):
            return original_bridge_run(self, coro)

    def template_call(self, *a, **kw):
        with timed_render("render-templetor"):
            return original_template_call(self, *a, **kw)

    stats.begin, stats.end = begin, end
    web.db.DB._db_execute = _db_execute
    AsyncBridge.run = bridge_run  # type: ignore[method-assign]
    web.template.Template.__call__ = template_call
    _bridge_installed = True
