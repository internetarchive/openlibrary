from .. import mock_memcache

class Test_mock_memcache:
    def test_set(self):
        m = mock_memcache.Client([])
        
        m.set("a", 1)
        assert m.get("a") == 1
        
        m.set("a", "foo")
        assert m.get("a") == "foo"

        m.set("a", ["foo", "bar"])
        assert m.get("a") == ["foo", "bar"]
        
    def test_add(self):
        m = mock_memcache.Client([])
        
        assert m.add("a", 1) == True
        assert m.get("a") == 1
        
        assert m.add("a", 2) == False
