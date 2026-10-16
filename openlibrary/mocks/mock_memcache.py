"""Library to mock memcache functionality."""

import memcache
import pytest


class Client:
    """Mock memcache client."""

    def __init__(self, servers=None):
        servers = servers or []
        self.servers = servers
        self.cache = {}

    def set(self, key, value, time=0):
        self.cache[key] = value

    def get(self, key):
        return self.cache.get(key)

    def add(self, key, value, time=0):
        if key not in self.cache:
            self.cache[key] = value
            return True
        else:
            return False

    def delete(self, key):
        self.cache.pop(key, None)

    def incr(self, key, delta=1):
        # Like memcached: None for a missing key, never below zero
        if key not in self.cache:
            return None
        self.cache[key] = max(int(self.cache[key]) + delta, 0)
        return self.cache[key]

    def decr(self, key, delta=1):
        return self.incr(key, -delta)


@pytest.fixture
def mock_memcache(request, monkeypatch):
    """This patches all the existing memcache connections to use mock memcache instance."""
    m = monkeypatch

    mock_memcache = Client()

    def proxy(name):
        method = getattr(mock_memcache, name)

        def f(self, *a, **kw):
            return method(*a, **kw)

        return f

    m.setattr(memcache.Client, "get", proxy("get"))
    m.setattr(memcache.Client, "set", proxy("set"))
    m.setattr(memcache.Client, "add", proxy("add"))
    m.setattr(memcache.Client, "incr", proxy("incr"))
    m.setattr(memcache.Client, "decr", proxy("decr"))

    yield mock_memcache

    m.undo()
