import asyncio
import time

import pytest

from openlibrary.core import cache
from openlibrary.mocks import mock_memcache


class Test_CircuitBreaker:
    """
    Uses MemoryCache as a stand-in for memcache so tests are fast and
    self-contained.  The circuit breaker is eventually-consistent by design
    (non-atomic counters) so we only verify the happy-path behaviour.
    """

    def make_cb(self, **kwargs):
        defaults = {
            "key_prefix": "test_cb",
            # Fresh MemoryCache so tests don't share state
            "engine": cache.MemoryCache(),
            "failure_threshold": 3,
            "cooldown_secs": 60,
        }
        return cache.CircuitBreaker(**defaults | kwargs)  # type: ignore

    def test_initially_closed(self):
        cb = self.make_cb()
        assert cb.should_skip() is False

    def test_failures_below_threshold_stay_closed(self):
        cb = self.make_cb(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.should_skip() is False

    def test_failures_at_threshold_open_circuit(self):
        cb = self.make_cb(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.should_skip() is True

    def test_success_when_closed_resets_failures(self):
        """Two failures then a success should remove the failure count so the
        circuit does not trip on the next single failure."""
        cb = self.make_cb(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()  # only 1 failure after reset
        assert cb.should_skip() is False

    def test_success_when_open_closes_circuit(self):
        cb = self.make_cb(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.should_skip() is True

        cb.record_success()
        assert cb.should_skip() is False

    def test_success_when_open_lowers_effective_threshold(self):
        """After recovering from an open circuit the failure counter is seeded
        at threshold-5, so fewer additional failures will re-open it."""
        cb = self.make_cb(failure_threshold=10)
        for _ in range(10):
            cb.record_failure()
        assert cb.should_skip() is True

        cb.record_success()
        assert cb.should_skip() is False

        # threshold-5 = 5 failures already on the books; 5 more hits threshold
        for _ in range(5):
            cb.record_failure()
        assert cb.should_skip() is True

    def test_circuit_reopens_after_cooldown(self, monkeytime):
        """should_skip() must return False once the cooldown window has elapsed."""
        cb = self.make_cb(failure_threshold=3, cooldown_secs=10)
        for _ in range(3):
            cb.record_failure()
        assert cb.should_skip() is True

        time.sleep(10)
        assert cb.should_skip() is False


class Test_memcache_memoize:
    def test_encode_args(self):
        m = cache.memcache_memoize(None, key_prefix="foo")

        assert m.encode_args([]) == ""
        assert m.encode_args(["a"]) == '"a"'
        assert m.encode_args([1]) == "1"
        assert m.encode_args(["a", 1]) == '"a",1'
        assert m.encode_args([{"a": 1}]) == '{"a":1}'
        assert m.encode_args([["a", 1]]) == '["a",1]'

    def test_generate_key_prefix(self):
        def foo():
            pass

        m = cache.memcache_memoize(foo)
        assert m.key_prefix[:4] == "foo_"

    def test_random_string(self):
        m = cache.memcache_memoize(None, "foo")
        assert m._random_string(0) == ""

        s1 = m._random_string(1)
        assert isinstance(s1, str)
        assert len(s1) == 1

        s10 = m._random_string(10)
        assert isinstance(s10, str)
        assert len(s10) == 10

    def square_memoize(self):
        def square(x):
            return x * x

        m = cache.memcache_memoize(square, key_prefix="square")
        m._memcache = mock_memcache.Client([])
        return m

    def test_call(self):
        m = self.square_memoize()
        s = m.stats

        assert m(10) == 100
        assert [s.calls, s.hits, s.updates, s.async_updates] == [1, 0, 1, 0]

        assert m(10) == 100
        assert [s.calls, s.hits, s.updates, s.async_updates] == [2, 1, 1, 0]

    def test_update_async(self):
        m = self.square_memoize()

        m.update_async(20)
        m.join_threads()

        assert m.memcache_get([20], {})[0] == 400

    def test_timeout(self, monkeytime):
        m = self.square_memoize()
        m.timeout = 0.1
        s = m.stats

        assert m(10) == 100

        time.sleep(0.1)
        assert m(10) == 100
        assert [s.calls, s.hits, s.updates, s.async_updates] == [2, 1, 1, 0]

        time.sleep(0.01)
        assert m(10) == 100
        assert [s.calls, s.hits, s.updates, s.async_updates] == [3, 2, 1, 1]

    def test_delete(self):
        m = self.square_memoize()

        m(10)
        m(10)
        assert m.stats.updates == 1

        # this should clear the cache and the next call should update the cache.
        m.memcache_delete_by_args(10)
        m(10)

        m(10)
        assert m.stats.updates == 2


class Test_memoize:
    def teardown_method(self, method):
        cache.memory_cache.clear()

    def get(self, key):
        return cache.memory_cache.get(key)

    def set(self, key, value):
        cache.memory_cache.set(key, value)

    def test_signatures(self):
        def square(x):
            """Returns square x."""
            return x * x

        msquare = cache.memoize(engine="memory", key="square")(square)
        assert msquare.__name__ == square.__name__
        assert msquare.__doc__ == square.__doc__

    def test_cache(self):
        @cache.memoize(engine="memory", key="square")
        def square(x):
            return x * x

        assert square(2) == 4
        assert self.get("square-2") == 4

        # It should read from cache instead of computing if entry is present in the cache
        self.set("square-42", 43)
        assert square(42) == 43

    def test_cache_with_tuple_keys(self):
        @cache.memoize(engine="memory", key=lambda x: (str(x), "square"))
        def square(x):
            return x * x

        @cache.memoize(engine="memory", key=lambda x: (str(x), "double"))
        def double(x):
            return x + x

        assert self.get("3") is None
        assert square(3) == 9
        assert self.get("3") == {"square": 9}
        assert double(3) == 6
        assert self.get("3") == {"square": 9, "double": 6}

    # --- ASYNC TESTS ---

    @pytest.mark.asyncio
    async def test_async_signatures(self):
        """Ensure metadata is preserved for async functions."""

        async def asquare(x):
            """Returns async square x."""
            return x * x

        msquare = cache.memoize(engine="memory", key="asquare")(asquare)

        # Check that it is still a coroutine function
        assert asyncio.iscoroutinefunction(msquare)
        assert msquare.__name__ == asquare.__name__
        assert msquare.__doc__ == asquare.__doc__

    @pytest.mark.asyncio
    async def test_async_cache_behavior(self):
        """Check that await works and caching occurs."""

        # We use a side_effect to prove the function isn't called on cache hits
        call_count = 0

        @cache.memoize(engine="memory", key="asquare")
        async def asquare(x):
            nonlocal call_count
            call_count += 1
            return x * x

        # 1. Cache Miss
        result = await asquare(2)
        assert result == 4
        assert call_count == 1
        assert self.get("asquare-2") == 4

        # 2. Cache Hit (call_count should NOT increase)
        result_2 = await asquare(2)
        assert result_2 == 4
        assert call_count == 1  # Still 1

        # 3. Manual Injection (Simulate shared cache)
        self.set("asquare-10", 1000)
        result_3 = await asquare(10)
        assert result_3 == 1000  # Should get injected value, not 100
        assert call_count == 1  # Function wasn't called

    @pytest.mark.asyncio
    async def test_async_tuple_keys(self):
        """Ensure async works with complex tuple keys."""

        @cache.memoize(engine="memory", key=lambda x: (str(x), "async_val"))
        async def get_val(x):
            return x + 1

        await get_val(5)

        # Check dictionary structure in cache
        cached_data = self.get("5")
        assert cached_data is not None
        assert cached_data["async_val"] == 6

    @pytest.mark.asyncio
    async def test_sync_vs_async_parity(self):
        """
        Crucial Test: Ensures a sync function and an async function
        produce the EXACT same cache entry if configured identically.
        This proves they can interoperate.
        """

        @cache.memoize(engine="memory", key="parity_check")
        def sync_f(x):
            return x + 1

        @cache.memoize(engine="memory", key="parity_check")
        async def async_f(x):
            return x + 1

        # 1. Run Sync, populate cache
        assert sync_f(10) == 11
        assert self.get("parity_check-10") == 11

        # 2. Run Async with same arg - should hit the cache set by Sync
        # We manually change the cache to prove Async hit it
        self.set("parity_check-10", 999)

        assert await async_f(10) == 999
