import time

from .. import cache
from ...mocks import mock_memcache

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

    def test_timeout(self):
        m = self.square_memoize()
        m.timeout = 0.1
        s = m.stats
        
        assert m(10) == 100
        time.sleep(0.1)
        
        assert m(10) == 100
        assert [s.calls, s.hits, s.updates, s.async_updates] == [2, 1, 1, 1]
        
    def test_delete(self):
        m = self.square_memoize()
        
        m(10)
        m(10)
        assert m.stats.updates == 1

        # this should clear the cache and the next call should update the cache.
        m(10, _cache="delete")

        m(10)
        assert m.stats.updates == 2