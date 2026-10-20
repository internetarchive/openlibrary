"""Per-route Prometheus request metrics, shared by FastAPI and web.py.

Both servers record the same series (``http_requests_total``,
``http_request_duration_seconds``, ...) from prometheus-fastapi-instrumentator's
``metrics.default``, told apart by a ``server`` label. web.py copies FastAPI's
``handler`` label, the route's path template, so an endpoint keeps its series when
it moves to FastAPI, or while both serve it; only ``server`` changes.

web.py names each request the way FastAPI would name the route serving it:

* If a FastAPI route serves the URL, its template, found by the instrumentator's own route matching.
* Otherwise the infogami route, written as a FastAPI template. ``/advancedsearch`` stays
  ``/advancedsearch``; ``/works/OL(\\d+)W/notes`` + ``.json`` becomes ``/works/OL{work_id}W/notes.json``;
  ``/books/OL1M/Some_Title`` becomes ``/books/OL{edition_id}M/{title}``.

So when porting a parameterized route, use the ``handler`` web.py reports for it as the FastAPI path.
Parameters are named ``work_id``, ``edition_id``, ``author_id`` and ``tag_id`` (``OL{work_id}W``),
``list_id`` (``{list_id}``, the whole ``OL1L``), ``username`` after ``/people/``, ``title`` for the
readable-URL slug, and ``key`` otherwise, with ``:path`` if it can contain a ``/``.
"""

from __future__ import annotations

import functools
import logging
import os
import re
from re import _constants as sre  # type: ignore[attr-defined]
from re import _parser as sre_parse  # type: ignore[attr-defined]
from timeit import default_timer
from typing import TYPE_CHECKING, Literal

import web
from prometheus_client import REGISTRY, CollectorRegistry, make_wsgi_app, multiprocess
from prometheus_fastapi_instrumentator import metrics, routing
from starlette.requests import Request
from starlette.responses import Response

from infogami.utils import app as infogami_app
from infogami.utils import types

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

logger = logging.getLogger("openlibrary.prometheus")

# Buckets for http_request_duration_seconds, the only per-route latency histogram.
# (The library's high-resolution histogram has one set of counts for the whole server.)
LATENCY_BUCKETS = (0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 1, 1.5, 2.5, 5, 10, 30, 60)
# Regexes, searched for in the handler name, as the instrumentator does
EXCLUDED_HANDLERS = ("/health", "/metrics")


def request_metrics(server: Literal["fastapi", "webpy"], registry: CollectorRegistry = REGISTRY) -> Callable[[metrics.Info], None] | None:
    """The request metrics, labelled ``server``. None if already registered in ``registry``."""
    return metrics.default(latency_lowr_buckets=LATENCY_BUCKETS, registry=registry, custom_labels={"server": server})


@functools.cache
def _fastapi_app() -> FastAPI | None:
    """The FastAPI routes, for naming web.py requests the way FastAPI would."""
    from fastapi import FastAPI  # noqa: PLC0415

    from openlibrary.asgi_app import _include_routers  # noqa: PLC0415

    app = FastAPI()
    try:
        _include_routers(app)
    except Exception:
        logger.exception("Failed to load the FastAPI routes; naming web.py requests by their infogami routes only")
        return None
    return app


def fastapi_route_name(method: str, path: str) -> str | None:
    """The handler label FastAPI's instrumentator gives this request, or None if no FastAPI route serves it."""
    if (app := _fastapi_app()) is None:
        return None
    scope = {"type": "http", "method": method, "path": path, "root_path": "", "headers": [], "app": app}
    return routing.get_route_name(Request(scope), should_include_root_path=False)


class _Unsupported(Exception):
    pass


_CATEGORIES = {
    sre.CATEGORY_DIGIT: r"\d",
    sre.CATEGORY_NOT_DIGIT: r"\D",
    sre.CATEGORY_SPACE: r"\s",
    sre.CATEGORY_NOT_SPACE: r"\S",
    sre.CATEGORY_WORD: r"\w",
    sre.CATEGORY_NOT_WORD: r"\W",
}
_VARIABLE_OPS = (sre.IN, sre.ANY, sre.NOT_LITERAL)
_OLID_PARAMS = {"W": "work_id", "M": "edition_id", "A": "author_id", "T": "tag_id"}


def _char_class(items) -> tuple[str, bool]:
    """A regex for an ``IN`` node, and whether it can match ``/``."""
    negate = items[0][0] is sre.NEGATE
    parts = []
    slash = False
    for op, av in items[1:] if negate else items:
        if op is sre.LITERAL:
            parts.append(re.escape(chr(av)))
            slash |= av == ord("/")
        elif op is sre.RANGE:
            parts.append(f"{re.escape(chr(av[0]))}-{re.escape(chr(av[1]))}")
            slash |= av[0] <= ord("/") <= av[1]
        elif op is sre.CATEGORY and av in _CATEGORIES:
            parts.append(_CATEGORIES[av])
            slash |= av in (sre.CATEGORY_NOT_DIGIT, sre.CATEGORY_NOT_SPACE, sre.CATEGORY_NOT_WORD)
        else:
            raise _Unsupported(op)
    return f"[{'^' if negate else ''}{''.join(parts)}]", slash != negate


def _variable(op, av) -> tuple[str, bool]:
    if op is sre.ANY:
        return ".", True
    if op is sre.NOT_LITERAL:
        return f"[^{re.escape(chr(av))}]", av != ord("/")
    return _char_class(av)


def _instrument(items, params: list[bool]) -> str:
    """Rewrite a parsed regex, capturing each variable part (``\\d+``, ``[^/]+``, ``.*``) as ``p<n>``.
    Literals, including the alternative of a ``(lists|series)`` that matched, are kept as they are."""
    out = []
    for op, av in items:
        if op is sre.LITERAL:
            out.append(re.escape(chr(av)))
        elif op is sre.SUBPATTERN:
            out.append(f"(?:{_instrument(av[-1], params)})")
        elif op is sre.BRANCH:
            out.append(f"(?:{'|'.join(_instrument(branch, params) for branch in av[1])})")
        elif op is sre.AT and av in (sre.AT_BEGINNING, sre.AT_END, sre.AT_BEGINNING_STRING, sre.AT_END_STRING):
            pass
        elif op in (sre.MAX_REPEAT, sre.MIN_REPEAT):
            low, high, sub = av
            quantifier = f"{{{low},{'' if high is sre.MAXREPEAT else high}}}" + ("?" if op is sre.MIN_REPEAT else "")
            if len(sub) == 1 and sub[0][0] in _VARIABLE_OPS:
                regex, slash = _variable(*sub[0])
                out.append(f"(?P<p{len(params)}>{regex}{quantifier})")
                params.append(slash)
            else:
                out.append(f"(?:{_instrument(sub, params)}){quantifier}")
        elif op in _VARIABLE_OPS:
            regex, slash = _variable(op, av)
            out.append(f"(?P<p{len(params)}>{regex})")
            params.append(slash)
        else:
            raise _Unsupported(op)
    return "".join(out)


@functools.cache
def _instrumented(pattern: str) -> tuple[re.Pattern[str], tuple[bool, ...]] | None:
    params: list[bool] = []
    try:
        return re.compile(_instrument(sre_parse.parse(pattern), params)), tuple(params)
    except _Unsupported, re.error:
        return None


def _param_name(before: str, after: str, can_contain_slash: bool) -> str:
    if before.endswith("OL") and after[:1] in _OLID_PARAMS:
        return _OLID_PARAMS[after[:1]]
    if before.endswith("/OL") and after[:1] == "L":
        return "list_id"
    if before.endswith("/people/"):
        return "username"
    return "key:path" if can_contain_slash else "key"


def route_template(pattern: str, path: str) -> str:
    """The FastAPI-style template for the infogami route ``pattern``, as it matched ``path``.

    >>> route_template(r"/works/OL(\\d+)W/notes", "/works/OL1W/notes")
    '/works/OL{work_id}W/notes'
    >>> route_template(r"((?:/people/[^/]+)?/(?:lists|series)/OL\\d+L)/editions", "/people/foo/lists/OL1L/editions")
    '/people/{username}/lists/{list_id}/editions'
    """
    if not (instrumented := _instrumented(pattern)) or not (match := instrumented[0].fullmatch(path)):
        return pattern  # still one label per route
    template = ""
    end = 0
    names: set[str] = set()
    for i, can_contain_slash in enumerate(instrumented[1]):
        start, stop = match.span(f"p{i}")
        if start < end or start == stop:  # unmatched, empty, or inside a part already replaced
            continue
        template += path[end:start]
        name = _param_name(template, path[stop:], can_contain_slash)
        if name == "list_id":  # the whole OL1L, as the FastAPI list routes take it
            template = template.removesuffix("OL")
            stop += 1
        name, _, converter = name.partition(":")
        unique, n = name, 2
        while unique in names:  # FastAPI needs distinct names
            unique, n = f"{name}{n}", n + 1
        names.add(unique)
        template += f"{{{unique}{':' if converter else ''}{converter}}}"
        end = stop
    return template + path[end:]


@functools.cache
def _page_patterns() -> dict[type, str]:
    return {cls: pattern for pattern, by_encoding in infogami_app.pages.items() for cls in by_encoding.values()}


_OLID_KEY = re.compile(r"/(\w+)/OL\d+([AMWLT])(/[^/]+)?")


def _key_template(key: str) -> str:
    """e.g. ``/books/OL1M`` -> ``/books/OL{edition_id}M``, for pages infogami serves by type.
    A title still in the path (``ReadableUrlProcessor`` redirected before taking it out) becomes ``/{title}``."""
    if m := _OLID_KEY.fullmatch(key):
        return route_template(rf"/{m[1]}/OL\d+{m[2]}", key.removesuffix(m[3] or "")) + ("/{title}" if m[3] else "")
    if re.fullmatch(r"/people/[^/]+", key):  # users have no type pattern
        return "/people/{username}"
    for pattern in types.type_patterns:
        if pattern.startswith("^") and re.search(pattern, key):
            return route_template(pattern, key)
    return "/{key:path}"


def _with_title(template: str, real_path: str, requested_path: str) -> str:
    """Put back the ``/{title}`` segment ``ReadableUrlProcessor`` took out of the path."""
    real, requested, segments = real_path.split("/"), requested_path.split("/"), template.split("/")
    if len(requested) != len(real) + 1 or len(segments) != len(real):
        return template
    for i in range(1, len(requested)):
        if requested[:i] == real[:i] and requested[i + 1 :] == real[i:]:
            return "/".join([*segments[:i], "{title}", *segments[i:]])
    return template


def infogami_route_name(requested_path: str) -> str | None:
    """The infogami route serving the current request as a FastAPI template, looked up the way
    ``infogami.utils.app.delegate`` does. ``requested_path`` is the path before processors rewrote it."""
    path = web.ctx.path
    suffix = ""
    if (encoding := web.ctx.get("encoding")) and path.endswith(f".{encoding}"):
        suffix = f".{encoding}"
        path = path.removesuffix(suffix)

    try:
        cls, _ = infogami_app.find_page()
    except web.HTTPError:  # unknown encoding
        return None

    mode = ""
    if cls is not None:
        template = route_template(_page_patterns()[cls], path) if cls in _page_patterns() else "none"
    elif (parts := path.rpartition("/"))[0] and parts[2] in infogami_app.views:
        # find_view() fetches the page to find its type, so go by the path instead
        template = f"{_key_template(parts[0])}/{parts[2]}"
    elif (m := web.input(_method="GET").get("m", "view")) in infogami_app.modes:
        template = _key_template(path)
        mode = "" if m == "view" else f"?m={m}"
    else:
        return None
    return _with_title(template, path, requested_path.removesuffix(suffix)) + suffix + mode


def webpy_route_name(requested_path: str) -> str:
    return fastapi_route_name(web.ctx.method, requested_path) or infogami_route_name(requested_path) or "none"


class WebPyPrometheusProcessor:
    """web.py processor recording FastAPI's request metrics. Add it outermost, so it times the other processors too."""

    def __init__(self, instrumentation: Callable[[metrics.Info], None]) -> None:
        self.instrumentation = instrumentation

    def __call__(self, handler):
        requested_path = web.ctx.path  # before e.g. ReadableUrlProcessor rewrites it
        start = default_timer()
        body = None
        try:
            body = handler()
            return body
        finally:
            duration = max(default_timer() - start, 0.0)
            try:
                self._record(requested_path, body, duration)
            except Exception:
                logger.exception("Failed to record Prometheus request metrics")

    def _record(self, requested_path: str, body, duration: float) -> None:
        handler = webpy_route_name(requested_path)
        if any(re.search(pattern, handler) for pattern in EXCLUDED_HANDLERS):
            return

        status = web.ctx.status.split(" ", maxsplit=1)[0]
        request_headers = [(b"content-length", web.ctx.env["CONTENT_LENGTH"].encode())] if web.ctx.env.get("CONTENT_LENGTH") else []
        response = Response(status_code=int(status))
        response.headers["content-length"] = str(_response_size(body))
        self.instrumentation(
            metrics.Info(
                request=Request({"type": "http", "method": web.ctx.method, "path": web.ctx.path, "headers": request_headers}),
                response=response,
                method=web.ctx.method,
                modified_handler=handler,
                modified_status=status,
                modified_duration=duration,
                modified_duration_without_streaming=duration,
            )
        )


def _response_size(body) -> int:
    if (length := dict(web.ctx.get("headers", [])).get("Content-Length")) is not None:
        return int(length)
    if isinstance(body, str):
        return len(body.encode())
    if isinstance(body, bytes):
        return len(body)
    return 0  # streamed


def instrument_webpy(app: web.application, wsgi_app):
    """Record request metrics for the web.py ``app``, and serve them at ``/metrics`` from ``wsgi_app``.

    Only call this in the web.py server: FastAPI loads the web.py app too, and records its own metrics.
    """
    if instrumentation := request_metrics("webpy"):
        app.processors.insert(0, WebPyPrometheusProcessor(instrumentation))
        _fastapi_app()  # load the routes now, not in the first request

    registry = REGISTRY
    if "PROMETHEUS_MULTIPROC_DIR" in os.environ:  # one set of metrics for all the gunicorn workers
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    metrics_app = make_wsgi_app(registry)

    def wrapper(environ, start_response):
        if environ.get("PATH_INFO") == "/metrics":
            return metrics_app(environ, start_response)
        return wsgi_app(environ, start_response)

    return wrapper
