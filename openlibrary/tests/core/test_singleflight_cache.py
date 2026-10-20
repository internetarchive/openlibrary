"""Unit tests for the fleet-wide single-flight cache helper.

Patches ``cache.get_memcache`` with an in-memory stub that reproduces the
one guarantee the helper builds on: ``add`` fails when the key exists, so
exactly one concurrent acquirer wins — the memcached server's own atomicity,
stubbed locally.
"""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from openlibrary.core.cache import invalidate, singleflight_cache


class MemcacheStub:
    """In-memory memcache semantics: add fails when the key exists."""

    def __init__(self):
        self.store: dict = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, expires=0):
        self.store[key] = value
        return True

    def add(self, key, value, expires=0):
        if key in self.store:
            return False
        self.store[key] = value
        return True

    def delete(self, key):
        return self.store.pop(key, None) is not None


@pytest.fixture
def mc():
    stub = MemcacheStub()
    with patch("openlibrary.core.cache.get_memcache", return_value=stub):
        yield stub


@pytest.mark.asyncio
async def test_fresh_entry_is_served_without_compute_or_lock(mc):
    mc.set("k", {"v": 0, "at": time.time(), "value": "cached"})
    compute = AsyncMock(return_value="computed")

    assert await singleflight_cache("k", compute, ttl=5) == "cached"

    compute.assert_not_awaited()
    assert "k.lock" not in mc.store


@pytest.mark.asyncio
async def test_missing_entry_computes_publishes_and_releases(mc):
    compute = AsyncMock(return_value="fresh")

    assert await singleflight_cache("k", compute, ttl=5) == "fresh"

    compute.assert_awaited_once()
    assert mc.store["k"]["value"] == "fresh"
    assert "k.lock" not in mc.store  # the lease is released
    # And a second call inside the TTL is a pure cache hit.
    assert await singleflight_cache("k", compute, ttl=5) == "fresh"
    compute.assert_awaited_once()


@pytest.mark.asyncio
async def test_concurrent_callers_on_one_worker_share_a_single_compute(mc):
    async def slow_compute():
        await asyncio.sleep(0.05)  # long enough for every caller to pile onto the local lock
        return "value"

    compute = AsyncMock(side_effect=slow_compute)

    results = await asyncio.gather(*(singleflight_cache("k", compute, ttl=5) for _ in range(5)))

    assert results == ["value"] * 5
    compute.assert_awaited_once()


@pytest.mark.asyncio
async def test_waiter_adopts_another_workers_value(mc):
    """Losing the add() race means waiting, not computing."""
    assert mc.add("k.lock", 1)  # a worker elsewhere holds the lease
    compute = AsyncMock(return_value="should-never-run")

    waiter = asyncio.create_task(singleflight_cache("k", compute, ttl=5, poll=0.01))
    await asyncio.sleep(0.03)  # the waiter is polling
    # The holder publishes and releases.
    mc.set("k", {"v": 0, "at": time.time(), "value": "winners-value"})
    mc.delete("k.lock")

    assert await asyncio.wait_for(waiter, timeout=1) == "winners-value"
    compute.assert_not_awaited()


@pytest.mark.asyncio
async def test_waiter_takes_over_when_the_lease_lapses(mc):
    """A dead holder's lease (lock_ttl) frees the waiter to compute itself."""
    assert mc.add("k.lock", 1)  # a holder that will never publish
    compute = AsyncMock(return_value="mine-now")

    waiter = asyncio.create_task(singleflight_cache("k", compute, ttl=5, poll=0.01))
    await asyncio.sleep(0.03)
    mc.delete("k.lock")  # the lease expires server-side

    assert await asyncio.wait_for(waiter, timeout=1) == "mine-now"
    compute.assert_awaited_once()


@pytest.mark.asyncio
async def test_expired_entry_recomputes(mc):
    mc.set("k", {"v": 0, "at": time.time() - 60, "value": "stale"})
    compute = AsyncMock(return_value="fresh")

    assert await singleflight_cache("k", compute, ttl=5) == "fresh"

    compute.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalidate_forces_a_recompute_despite_a_fresh_ttl(mc):
    mc.set("k", {"v": 3, "at": time.time(), "value": "cached"})
    compute = AsyncMock(return_value="fresh")

    invalidate("k")  # a mutation landed somewhere in the fleet

    assert await singleflight_cache("k", compute, ttl=5) == "fresh"
    compute.assert_awaited_once()
    # invalidate bumped a missing version key to 1; the winner published
    # under that version, so the next reader finds it fresh.
    assert mc.store["k"]["v"] == 1


@pytest.mark.asyncio
async def test_none_is_a_cacheable_value(mc):
    """A cached None must not read as a missing key (which would recompute)."""
    compute = AsyncMock(return_value=None)

    assert await singleflight_cache("k", compute, ttl=5) is None
    assert await singleflight_cache("k", compute, ttl=5) is None

    compute.assert_awaited_once()


@pytest.mark.asyncio
async def test_raising_compute_releases_the_lease_and_propagates(mc):
    compute = AsyncMock(side_effect=ValueError("upstream down"))

    with pytest.raises(ValueError, match="upstream down"):
        await singleflight_cache("k", compute, ttl=5)

    assert "k.lock" not in mc.store
    # The next caller retries — a failed refresh poisons nothing.
    compute.side_effect = None
    compute.return_value = "ok"
    assert await singleflight_cache("k", compute, ttl=5) == "ok"


@pytest.mark.asyncio
async def test_a_bump_during_compute_leaves_the_entry_stale_for_readers(mc):
    """The stale-set guard: a winner that raced a mutation publishes an entry
    stamped with its pre-mutation version, which no reader treats as current."""

    async def compute():
        invalidate("k")  # the mutation lands while this compute is in flight
        return "computed-before-the-bump"

    assert await singleflight_cache("k", compute, ttl=5) == "computed-before-the-bump"

    after = AsyncMock(return_value="recomputed")
    assert await singleflight_cache("k", after, ttl=5) == "recomputed"
    after.assert_awaited_once()
