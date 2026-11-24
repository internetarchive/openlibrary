"""``@nonblocking``: mark a FastAPI route that never blocks the event loop.

In Kubernetes such routes can be served by FastAPI pods tuned for many concurrent requests on one event loop.
scripts/generate_fastapi_routes.py lists them under ``fastapiNonblockingRoutes`` in conf/k8s/fastapi-routes.yaml, and
every other route under ``fastapiRoutes``. The decorator changes nothing else: locally and on the VMs the route behaves the same.

When unsure, leave it off. An unmarked route is always safe; a wrongly marked one stalls every request on its pod.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

DEFAULT = "default"
NONBLOCKING = "nonblocking"
GROUPS = (DEFAULT, NONBLOCKING)

_ATTR = "_ol_nonblocking"


def nonblocking[F: Callable[..., Any]](endpoint: F) -> F:
    """Declare that this route never blocks the event loop, so it may be served with many requests on one loop.

    Being ``async def`` isn't enough. Everything the route calls, at any depth, must be one of:

    - awaited async I/O: ``openlibrary.core.async_db`` (``fetch_one``, ``fetch_all``, ``fetch_val``, ``execute``),
      ``httpx.AsyncClient``, Solr through ``run_solr_query_async``
    - quick pure-CPU work (parsing, building a response)

    and none of these, which block:

    - memcache, including ``cache.memoize``, ``cache.singleflight_cache`` and ``get_memcache()`` (the client is sync)
    - infobase: ``site.get()`` and web.py's site object, ``get_current_user()``, ``accounts.find``
    - the legacy database (``db.get_db()``) and ``async_bridge.run``
    - template rendering (Jinja or Templetor), file reads, ``requests``
    - a sync dependency: a ``def`` function or a class in ``Depends()`` runs in FastAPI's thread pool. Take
      query parameters as ``Annotated[Model, Query()]`` (with every parameter in that one model) instead.

    The route generator rejects a sync endpoint or a sync dependency. The rest is up to the author and reviewer;
    production's Server-Timing header shows any sync I/O as ``blocking``, which a nonblocking route should never have.

        @nonblocking
        @router.get("/foo.json")
        async def foo(): ...

    It can go above or below the route decorator: it only tags the function, which the router keeps a reference to.
    """
    if not inspect.iscoroutinefunction(endpoint):
        raise TypeError(f"@nonblocking needs an `async def` endpoint, not {endpoint.__qualname__}")
    setattr(endpoint, _ATTR, True)
    return endpoint


def route_group(endpoint: Callable[..., Any]) -> str:
    """The group a route is listed under in conf/k8s/fastapi-routes.yaml."""
    return NONBLOCKING if getattr(endpoint, _ATTR, False) else DEFAULT
