import threading

from openlibrary.contribute import pool
from openlibrary.core.cache import MemoryCache

KEY = "contribute.test_pool"


def use_memory_cache(monkeypatch):
    mc = MemoryCache()
    monkeypatch.setattr(pool.olcache, "get_memcache", lambda: mc)
    return mc


def join_refreshes():
    for t in threading.enumerate():
        if t.name == pool.thread_name(KEY):
            t.join()


def test_cold_cache_serves_nothing_while_a_thread_builds_it(monkeypatch):
    mc = use_memory_cache(monkeypatch)
    assert pool.get(KEY, 60, lambda: [1, 2]) is None
    join_refreshes()
    assert mc.get(KEY)["value"] == [1, 2]
    assert mc.get(pool.lock_key(KEY)) is None
    assert pool.get(KEY, 60, lambda: 1 / 0) == [1, 2]


def test_stale_entry_is_served_while_a_thread_rebuilds_it(monkeypatch):
    mc = use_memory_cache(monkeypatch)
    mc.set(KEY, {"at": 0, "value": [1]})
    assert pool.get(KEY, 60, lambda: [2]) == [1]
    join_refreshes()
    assert mc.get(KEY)["value"] == [2]
    assert mc.get(pool.lock_key(KEY)) is None


def test_an_empty_rebuild_keeps_the_old_entry_and_releases_the_lock(monkeypatch):
    mc = use_memory_cache(monkeypatch)
    mc.set(KEY, {"at": 0, "value": [1]})
    assert pool.get(KEY, 60, list) == [1]
    join_refreshes()
    assert mc.get(KEY)["value"] == [1]
    assert mc.get(pool.lock_key(KEY)) is None


def test_an_empty_rebuild_on_a_cold_cache_is_cached(monkeypatch):
    mc = use_memory_cache(monkeypatch)
    assert pool.get(KEY, 60, list) is None
    join_refreshes()
    assert pool.get(KEY, 60, lambda: 1 / 0) == []
    assert mc.get(pool.lock_key(KEY)) is None


def test_a_failed_rebuild_keeps_the_old_entry_and_holds_the_lock(monkeypatch):
    mc = use_memory_cache(monkeypatch)
    mc.set(KEY, {"at": 0, "value": [1]})
    assert pool.get(KEY, 60, lambda: 1 / 0) == [1]
    join_refreshes()
    assert mc.get(KEY)["value"] == [1]
    assert mc.get(pool.lock_key(KEY)) is not None


def test_an_entry_in_another_shape_is_a_miss(monkeypatch):
    mc = use_memory_cache(monkeypatch)
    mc.set(KEY, {"at": 0, "rows": [1]})
    assert pool.get(KEY, 60, lambda: [2]) is None
    join_refreshes()
    assert mc.get(KEY)["value"] == [2]


def test_only_one_rebuild_runs_at_a_time(monkeypatch):
    mc = use_memory_cache(monkeypatch)
    mc.add(pool.lock_key(KEY), 1)
    assert pool.get(KEY, 60, lambda: [1]) is None
    assert not any(t.name == pool.thread_name(KEY) for t in threading.enumerate())
    assert mc.get(KEY) is None
