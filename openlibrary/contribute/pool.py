"""A cached list that no request ever builds.

``get`` serves what memcache has, fresh or stale. An expired or missing entry starts one rebuild on a
background thread, held to one across workers by a lock; a cold cache serves nothing meanwhile, which the
page shows as placeholders until its script finds the new list. The feed pool and the Solr picks use this.
"""

import logging
import threading
import time
from collections.abc import Callable

from openlibrary.core import cache as olcache

logger = logging.getLogger("openlibrary.contribute.pool")

# By default a stale entry outlives its TTL by this many, so a later failed rebuild still has something to serve.
KEEP = 6


def thread_name(key: str) -> str:
    return f"{key}.refresh"


def lock_key(key: str) -> str:
    return f"{key}.lock"


def get(key: str, ttl: int, rebuild: Callable[[], list], lock_ttl: int = 120, keep: int | None = None) -> list | None:
    """The cached list, fresh or stale, or None while a cold cache is being filled.

    ``lock_ttl`` must outlast a rebuild. ``keep`` is how long an entry is served at all, ``ttl * KEEP`` by default.
    """
    mc = olcache.get_memcache()
    # Anything not in this module's shape (an older format under the same key) counts as a miss.
    if not (isinstance(entry := mc.get(key), dict) and "value" in entry):
        entry = None
    if entry and time.time() - entry["at"] < ttl:
        return entry["value"]
    if mc.add(lock_key(key), time.time(), expires=lock_ttl):
        threading.Thread(target=refresh, args=(key, ttl, rebuild, keep), name=thread_name(key), daemon=True).start()
    return entry["value"] if entry else None


def refresh(key: str, ttl: int, rebuild: Callable[[], list], keep: int | None = None) -> None:
    """Rebuild and cache the list, then release the lock.

    An empty result is cached too, so "nothing to show" is an answer rather than another rebuild, but it never
    replaces a non-empty list. A failure keeps the lock until it expires, so a broken backend is retried once per ``lock_ttl``.
    """
    mc = olcache.get_memcache()
    try:
        value = rebuild()
    except Exception:
        logger.exception("Could not rebuild %s", key)
        return
    old = mc.get(key)
    if value or not (isinstance(old, dict) and old.get("value")):
        mc.set(key, {"at": time.time(), "value": value}, expires=keep or ttl * KEEP)
    mc.delete(lock_key(key))
