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

# A stale entry outlives its TTL by this many, so a later failed rebuild still has something to serve.
KEEP = 6


def thread_name(key: str) -> str:
    return f"{key}.refresh"


def lock_key(key: str) -> str:
    return f"{key}.lock"


def get(key: str, ttl: int, rebuild: Callable[[], list], lock_ttl: int = 120) -> list | None:
    """The cached list, fresh or stale, or None while a cold cache is being filled. ``lock_ttl`` must outlast a rebuild."""
    mc = olcache.get_memcache()
    entry = mc.get(key)
    if entry and time.time() - entry["at"] < ttl:
        return entry["value"]
    if mc.add(lock_key(key), time.time(), expires=lock_ttl):
        threading.Thread(target=refresh, args=(key, ttl, rebuild), name=thread_name(key), daemon=True).start()
    return entry["value"] if entry else None


def refresh(key: str, ttl: int, rebuild: Callable[[], list]) -> None:
    """Rebuild and cache the list, then release the lock. A failed or empty rebuild leaves the old entry in place."""
    mc = olcache.get_memcache()
    try:
        if value := rebuild():
            mc.set(key, {"at": time.time(), "value": value}, expires=ttl * KEEP)
    except Exception:
        logger.exception("Could not rebuild %s", key)
    finally:
        mc.delete(lock_key(key))
