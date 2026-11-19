import asyncio
import inspect
import json
import threading
import time

import pytest

from openlibrary.core import cache
from openlibrary.mocks import mock_memcache
from openlibrary.utils import server_timing


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
        assert m.active_threads == {}

    def test_contended_refresh_removes_thread_without_deleting_flag(self):
        m = self.square_memoize()
        flag = m.compute_key((20,), {}) + "/flag"
        m.memcache.add(flag, "another worker")

        m.update_async(20)
        m.join_threads()

        assert m.active_threads == {}
        assert m.memcache.get(flag) == "another worker"
        assert m.memcache_get((20,), {}) is None

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

    @pytest.mark.asyncio
    async def test_call_many_async_empty(self):
        m = self.square_memoize()

        async def square_async(x):
            return x * x

        assert await m.call_many_async([], square_async) == []
        assert m.stats.calls == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("operation", ["get_multi", "set_multi"])
    @pytest.mark.parametrize("fails", [False, True])
    async def test_bulk_memcache_stats_are_balanced_in_worker(self, monkeypatch, operation, fails):
        m = self.square_memoize()
        calls = []

        def begin(name, **kwargs):
            with pytest.raises(RuntimeError, match="no running event loop"):
                asyncio.get_running_loop()
            calls.append(("begin", name, threading.get_ident()))

        def end(**kwargs):
            calls.append(("end", kwargs, threading.get_ident()))

        monkeypatch.setattr(cache.stats, "begin", begin)
        monkeypatch.setattr(cache.stats, "end", end)
        if fails:

            def fail(*args):
                raise RuntimeError("memcache unavailable")

            monkeypatch.setattr(m.memcache, operation, fail)

        if operation == "get_multi":
            assert await asyncio.to_thread(m._memcache_get_multi, [(2,)]) == {}
        else:
            await asyncio.to_thread(m._memcache_set_multi, {(2,): (4, time.time())})

        assert len(calls) == 2
        assert calls[0][:2] == ("begin", f"memcache.{operation}")
        assert calls[1][0] == "end"
        assert calls[0][2] == calls[1][2]

    @pytest.mark.asyncio
    async def test_call_many_async_records_request_memcache_timings(self):
        m = self.square_memoize()
        server_timing.install_legacy_bridge()
        timings, token = server_timing.start_request()

        async def square_async(x):
            return x * x

        try:
            assert await m.call_many_async([(2,)], square_async) == [4]
            assert await m.call_many_async([(2,)], square_async) == [4]
            metrics = timings.snapshot()
            assert metrics["memcache"][0] == 3  # cold get/set, then warm get
            assert "blocking" not in metrics
        finally:
            server_timing.end_request(token)

    @pytest.mark.asyncio
    async def test_call_many_async_failure_cancels_and_awaits_siblings(self):
        m = self.square_memoize()
        sibling_started = asyncio.Event()
        sibling_finished = asyncio.Event()
        completed = []
        sibling_tasks = []
        failure = ValueError("unexpected computation failure")

        async def compute(x):
            if x == 1:
                completed.append(x)
                return x * x
            if x == 2:
                await sibling_started.wait()
                raise failure
            sibling_tasks.append(asyncio.current_task())
            sibling_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                sibling_finished.set()

        try:
            with pytest.raises(ValueError, match="unexpected computation failure") as exc:
                await m.call_many_async([(1,), (2,), (3,)], compute)
            assert exc.value is failure
            assert completed == [1]
            assert sibling_finished.is_set()
            assert all(task.cancelled() for task in sibling_tasks)
            assert m.memcache.get(m.compute_key((1,), {})) is None
        finally:
            for task in sibling_tasks:
                task.cancel()
            await asyncio.gather(*sibling_tasks, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_call_many_async_invalid_concurrency(self):
        m = self.square_memoize()

        async def square_async(x):
            return x * x

        with pytest.raises(ValueError, match="max_concurrency must be at least 1"):
            await m.call_many_async([(1,)], square_async, max_concurrency=0)

    @pytest.mark.asyncio
    async def test_call_many_async_miss_hit_stale(self, monkeytime):
        m = self.square_memoize()
        m.timeout = 0.1
        s = m.stats

        computed = []

        async def square_async(x):
            computed.append(x)
            return x * x

        # 1. Cache misses
        result = await m.call_many_async([(2,), (3,), (2,)], square_async)
        assert result == [4, 9, 4]
        assert sorted(computed) == [2, 3]  # deduplicated in computation
        assert [s.calls, s.hits, s.updates, s.async_updates] == [3, 0, 3, 0]

        # 2. Cache hits
        computed.clear()
        result = await m.call_many_async([(2,), (3,)], square_async)
        assert result == [4, 9]
        assert computed == []
        assert [s.calls, s.hits, s.updates, s.async_updates] == [5, 2, 3, 0]

        # 3. Cache stale
        await asyncio.sleep(0.12)
        computed.clear()
        result = await m.call_many_async([(2,)], square_async)
        assert result == [4]  # Returns stale value immediately
        assert [s.calls, s.hits, s.updates, s.async_updates] == [6, 3, 3, 1]

        # Wait for background refresh
        await cache.wait_for_background_tasks()
        assert computed == [2]

    @pytest.mark.asyncio
    async def test_call_many_async_concurrency_bounding(self):
        m = self.square_memoize()
        in_flight = 0
        max_in_flight = 0

        async def worker_async(x):
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0.02)
            in_flight -= 1
            return x * 10

        args_list = [(i,) for i in range(12)]
        results = await m.call_many_async(args_list, worker_async, max_concurrency=3)
        assert results == [i * 10 for i in range(12)]
        assert max_in_flight == 3

    @pytest.mark.asyncio
    async def test_call_many_async_stale_refresh_flag_contention(self):
        m = self.square_memoize()
        # Seed stale value
        m.memcache_set((5,), {}, 25, time.time() - 3600)

        # Another worker is already refreshing it (flag set)
        flag = m.compute_key((5,), {}) + "/flag"
        m.memcache.add(flag, "other_worker")

        refreshed = False

        async def square_async(x):
            nonlocal refreshed
            refreshed = True
            return x * x

        res = await m.call_many_async([(5,)], square_async)
        assert res == [25]

        await cache.wait_for_background_tasks()
        assert not refreshed  # skipped because flag was acquired by someone else
        assert m.memcache.get(flag) == "other_worker"  # did not delete someone else's flag

    @pytest.mark.asyncio
    async def test_call_many_async_stale_refresh_cancellation_cleans_flag(self):
        m = self.square_memoize()
        m.memcache_set((5,), {}, 25, time.time() - 3600)
        flag = m.compute_key((5,), {}) + "/flag"

        started = asyncio.Event()

        async def hung_async(x):
            started.set()
            await asyncio.sleep(100)
            return x * x

        semaphore = asyncio.Semaphore(1)
        task = asyncio.create_task(m._refresh_async([(5,)], hung_async, semaphore))
        await started.wait()
        # Flag is held by the task
        assert m.memcache.get(flag) == "true"

        # Cancel the task
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # Flag must be cleaned up in finally block
        assert m.memcache.get(flag) is None

    @pytest.mark.asyncio
    async def test_call_many_async_stale_refresh_cancellation_during_flag_add(self):
        m = self.square_memoize()
        m.memcache_set((5,), {}, 25, time.time() - 3600)
        flag = m.compute_key((5,), {}) + "/flag"

        add_started = threading.Event()
        can_finish_add = threading.Event()

        orig_add = m._memcache_add_flag

        def slow_add_flag(f):
            add_started.set()
            assert can_finish_add.wait(timeout=5), "Timed out waiting for test to release add_flag"
            return orig_add(f)

        m._memcache_add_flag = slow_add_flag

        async def square_async(x):
            return x * x

        semaphore = asyncio.Semaphore(1)
        task = asyncio.create_task(m._refresh_async([(5,)], square_async, semaphore))

        # Wait until the worker thread is blocked inside _memcache_add_flag
        await asyncio.to_thread(add_started.wait, 5)

        # Cancel the task while add_flag is blocked in the worker thread
        task.cancel()

        # Release the worker thread so it finishes acquiring the flag
        can_finish_add.set()

        # Await the task - it should catch cancellation, determine the flag was acquired, and delete it
        with pytest.raises(asyncio.CancelledError):
            await task

        # The flag must NOT remain in memcache indefinitely
        assert m.memcache.get(flag) is None

    @pytest.mark.asyncio
    async def test_call_many_async_cache_failures_resilience(self):
        m = self.square_memoize()

        async def square_async(x):
            return x * x

        # 1. Corrupted JSON in cache for one key
        key1 = m.compute_key((1,), {})
        m.memcache.set(key1, "not-valid-json{{{")

        # 2. Malformed envelope (not a 2-item list)
        key2 = m.compute_key((2,), {})
        m.memcache.set(key2, json.dumps("not-a-list"))

        # 3. Malformed envelope (timestamp not numeric)
        key3 = m.compute_key((3,), {})
        m.memcache.set(key3, json.dumps([9, "invalid-timestamp"]))

        # 4. Valid cached byte string
        key4 = m.compute_key((4,), {})
        m.memcache.set(key4, json.dumps([16, time.time()]).encode("utf-8"))

        res = await m.call_many_async([(1,), (2,), (3,), (4,)], square_async)
        assert res == [1, 4, 9, 16]

    @pytest.mark.asyncio
    async def test_call_many_async_invalid_utf8_treated_as_miss(self):
        m = self.square_memoize()

        async def square_async(x):
            return x * x

        # Key 1 has invalid UTF-8 bytes in memcache
        key1 = m.compute_key((1,), {})
        m.memcache.set(key1, b"\xff\xfe\x80")

        # Key 2 has valid cached data
        key2 = m.compute_key((2,), {})
        m.memcache.set(key2, json.dumps([4, time.time()]))

        res = await m.call_many_async([(1,), (2,)], square_async)
        assert res == [1, 4]

    @pytest.mark.asyncio
    async def test_call_many_async_get_multi_failure_treated_as_miss(self, monkeypatch):
        m = self.square_memoize()

        async def square_async(x):
            return x * x

        # When get_multi raises an exception, it should be logged and treated as misses
        def bad_get_multi(keys):
            raise RuntimeError("memcache connection failure")

        monkeypatch.setattr(m.memcache, "get_multi", bad_get_multi)
        res = await m.call_many_async([(2,), (3,)], square_async)
        assert res == [4, 9]

    @pytest.mark.asyncio
    async def test_call_many_async_set_multi_failure_returns_results(self, monkeypatch):
        m = self.square_memoize()

        async def square_async(x):
            return x * x

        def bad_set_multi(mapping):
            raise RuntimeError("memcache write failure")

        monkeypatch.setattr(m.memcache, "set_multi", bad_set_multi)
        # Should log exception and still return fetched results without throwing
        res = await m.call_many_async([(5,)], square_async)
        assert res == [25]

    @pytest.mark.asyncio
    async def test_call_many_async_negative_caching(self):
        m = cache.memcache_memoize(lambda x: {}, key_prefix="negative")
        m._memcache = mock_memcache.Client([])

        call_count = 0

        async def fetch_empty(x):
            nonlocal call_count
            call_count += 1
            return {}

        res1 = await m.call_many_async([("item",)], fetch_empty)
        assert res1 == [{}]
        assert call_count == 1

        # Second call should hit cache (empty dict is valid)
        res2 = await m.call_many_async([("item",)], fetch_empty)
        assert res2 == [{}]
        assert call_count == 1


def test_background_refresh_tasks_are_scoped_per_loop():
    m = cache.memcache_memoize(lambda x: x, key_prefix="loop-isolation")
    m._memcache = mock_memcache.Client([])
    m.memcache_set((1,), {}, 1, time.time() - 3600)

    async def start_refresh():
        started = asyncio.Event()
        release = asyncio.Event()

        async def compute(x):
            started.set()
            await release.wait()
            return x + 1

        assert await m.call_many_async([(1,)], compute) == [1]
        await started.wait()
        return release

    async def finish_refresh(release):
        release.set()
        await cache.wait_for_background_tasks()

    with asyncio.Runner() as first, asyncio.Runner() as second:
        release = first.run(start_refresh())
        try:
            second.run(cache.wait_for_background_tasks())
            assert m.memcache_get((1,), {})[0] == 1
        finally:
            first.run(finish_refresh(release))
        assert m.memcache_get((1,), {})[0] == 2


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
        assert inspect.iscoroutinefunction(msquare)
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
