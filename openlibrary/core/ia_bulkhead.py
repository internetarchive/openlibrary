"""Global cap on concurrent requests to archive.org's availability services.

web.py workers are synchronous, so a worker waiting on archive.org can't serve
anything else. When archive.org slows down, those calls pile up until they hold
every worker and the whole site goes down with it (#13956). This caps how many
availability requests can be in flight at once, across every worker on every
host, with a counter in memcache. A request over the cap isn't made: callers get
the same "error" availability they already show when archive.org fails.
"""

import functools
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

import memcache

from infogami import config
from openlibrary.core import stats

logger = logging.getLogger("openlibrary.ia_bulkhead")

DEFAULT_MAX_CONCURRENT = 15

# The counter is bucketed into fixed windows so that a slot leaked by a killed
# worker expires on its own. A request is counted in the window it started in and
# released from that same window; IA requests time out well within a window, so
# everything in flight is in the current window or the one before it.
WINDOW_SECONDS = 30


class IABulkheadFull(Exception):
    """Raised instead of making an IA request when the concurrency cap is reached."""


@functools.cache
def _memcache() -> memcache.Client | None:
    # A plain client, not cache.get_memcache(): that one compresses/JSON-encodes
    # values, and memcached's incr/decr only work on plain integers.
    servers = config.get("memcache_servers")
    return memcache.Client(servers) if servers else None


def _key(window: int) -> str:
    return f"ia_bulkhead:{window}"


@contextmanager
def ia_request_slot(name: Literal["availability", "groundtruth"]) -> Iterator[None]:
    """Hold one of the global IA request slots for the duration of the block.

    Raises IABulkheadFull, without running the block, when every slot is taken.
    Fails open (runs the block) when memcache is unavailable.
    """
    if (mc := _memcache()) is None:
        yield
        return

    window = int(time.time()) // WINDOW_SECONDS
    key = _key(window)
    try:
        mc.add(key, 0, time=2 * WINDOW_SECONDS)
        # python-memcached returns None rather than raising when memcache is down
        if (in_flight := mc.incr(key)) is not None:
            in_flight += int(mc.get(_key(window - 1)) or 0)
    except Exception:
        logger.exception("IA bulkhead could not reach memcache; allowing the request")
        in_flight = None

    if in_flight is None:
        yield
        return

    try:
        if in_flight > config.get("ia_max_concurrent_requests", DEFAULT_MAX_CONCURRENT):
            stats.increment(f"ol.ia_bulkhead.skipped.{name}")
            raise IABulkheadFull(name)
        yield
    finally:
        try:
            mc.decr(key)
        except Exception:
            logger.exception("IA bulkhead could not release its slot")
