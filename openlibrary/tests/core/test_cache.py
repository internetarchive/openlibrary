import time

from openlibrary.core import cache
from openlibrary.mocks import mock_memcache


class Test_memcache_memoize:
    def test_encode_args(self):
        m = cache.memcache_memoize(None, key_prefix="foo")

        assert m.encode_args([]) == ''
        assert m.encode_args(["a"]) == '"a"'
        assert m.encode_args([1]) == '1'
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

    def test_cacheable_callback(self):
        call_count = 0

        def sometimes_fails(x):
            nonlocal call_count
            call_count += 1
            if x < 0:
                return {'error': 'negative number'}
            return {'result': x * x}

        def is_cacheable(args, kwargs, value):
            return 'error' not in value

        m = cache.memcache_memoize(
            sometimes_fails,
            key_prefix="sometimes_fails",
            cacheable=is_cacheable,
        )
        m._memcache = mock_memcache.Client([])

        assert m(10) == {'result': 100}
        assert call_count == 1
        assert m(10) == {'result': 100}
        assert call_count == 1
        assert m(-5) == {'error': 'negative number'}
        assert call_count == 2
        assert m(-5) == {'error': 'negative number'}
        assert call_count == 3  # No cache hit, new call made

    def test_cacheable_callback_edge_cases(self):
        call_count = 0

        def returns_various(x):
            nonlocal call_count
            call_count += 1
            if x == 0:
                return None
            if x == 1:
                return ''
            if x == 2:
                return {}
            if x == 3:
                return {'partial': True}
            return {'complete': True, 'data': x}

        def is_cacheable(args, kwargs, value):
            if value is None or value == '' or value == {}:
                return False
            if isinstance(value, dict) and 'complete' not in value:
                return False
            return True

        m = cache.memcache_memoize(
            returns_various,
            key_prefix="edge_cases",
            cacheable=is_cacheable,
        )
        m._memcache = mock_memcache.Client([])

        assert m(0) is None
        assert call_count == 1
        assert m(0) is None
        assert call_count == 2
        assert m(1) == ''
        assert call_count == 3
        assert m(1) == ''
        assert call_count == 4
        assert m(2) == {}
        assert call_count == 5
        assert m(2) == {}
        assert call_count == 6
        assert m(3) == {'partial': True}
        assert call_count == 7
        assert m(3) == {'partial': True}
        assert call_count == 8

        assert m(100) == {'complete': True, 'data': 100}
        assert call_count == 9
        assert m(100) == {'complete': True, 'data': 100}
        assert call_count == 9

    def test_cacheable_callback_exception_handling(self):
        call_count = 0

        def simple_func(x):
            nonlocal call_count
            call_count += 1
            return {'value': x}

        def buggy_cacheable(args, kwargs, value):
            if value.get('value') == 'crash':
                raise ValueError("Intentional crash in cacheable")
            return True

        m = cache.memcache_memoize(
            simple_func,
            key_prefix="buggy_cacheable",
            cacheable=buggy_cacheable,
        )
        m._memcache = mock_memcache.Client([])

        assert m('normal') == {'value': 'normal'}
        assert call_count == 1
        assert m('normal') == {'value': 'normal'}
        assert call_count == 1 
        result = m('crash')
        assert result == {'value': 'crash'}
        call_count_after_first_crash = call_count
        result = m('crash')
        assert result == {'value': 'crash'}
        assert call_count > call_count_after_first_crash


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
        self.set('square-42', 43)
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


class Test_method_memoize:
    def test_handles_no_args(self):
        class A:
            def __init__(self):
                self.result = 0

            @cache.method_memoize
            def foo(self):
                self.result += 1
                return self.result

        a = A()
        assert a.foo() == 1
        assert a.foo() == 1
        assert a.result == 1

    def test_handles_args(self):
        class A:
            def __init__(self):
                self.result = 1

            @cache.method_memoize
            def foo(self, multiplier):
                self.result *= multiplier
                return self.result

        a = A()
        assert a.foo(2) == 2
        assert a.foo(2) == 2
        assert a.result == 2
        assert a.foo(3) == 6
        assert a.foo(2) == 2
        assert a.result == 6
