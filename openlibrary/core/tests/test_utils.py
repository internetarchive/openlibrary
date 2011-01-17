from .. import utils
from ..mocks import mock_memcache

class Test_memcache_memoize:
    def test_encode_args(self):
        m = utils.memcache_memoize(None, key="foo", servers=[])
        
        assert m.encode_args([]) == ''
        assert m.encode_args(["a"]) == '"a"'
        assert m.encode_args([1]) == '1' 
        assert m.encode_args(["a", 1]) == '"a",1'
        assert m.encode_args([{"a": 1}]) == '{"a":1}'
        assert m.encode_args([["a", 1]]) == '["a",1]'
        
    def square_memoize(self):
        def square(x):
            return x * x
            
        m = utils.memcache_memoize(square, key="foo", servers=[])
        m.memcache = mock_memcache.Client([])
        return m
        
    def test_call(self):
        m = self.square_memoize()
        s = m.stats
        
        assert m(10) == 100
        assert [s.calls, s.hits, s.updates, s.async_updates] == [1, 0, 1, 0]
        
        assert m(10) == 100
        assert [s.calls, s.hits, s.updates, s.async_updates] == [2, 1, 1, 0]
        
