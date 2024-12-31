"""Library to mock memcache functionality.
"""

import memcache
import pytest


class Client:
    """Mock memcache client."""

    def __init__(self, servers=None):
        servers = servers or []
        self.servers = servers
        self.cache = {}

    def set(self, key, value):
        self.cache[key] = value

    def get(self, key):
        return self.cache.get(key)

    def add(self, key, value):
        if key not in self.cache:
            self.cache[key] = value
            return True
        else:
            return False

    def delete(self, key):
        self.cache.pop(key, None)


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

    yield mock_memcache

    m.undo()
