from unittest.mock import MagicMock

from infogami import config
from openlibrary.plugins.openlibrary import connection


def middleware_types(conn) -> list[type]:
    types = []
    while isinstance(conn, connection.ConnectionMiddleware):
        types.append(type(conn))
        conn = conn.conn
    return types


def test_ol_connection_can_skip_memcache(monkeypatch):
    monkeypatch.setattr(config, "infobase_server", "localhost:7000", raising=False)
    monkeypatch.setattr(config, "memcache_servers", ["localhost:11211"], raising=False)
    monkeypatch.setattr(connection, "_memcache", MagicMock())

    assert connection.MemcacheMiddleware in middleware_types(connection.OLConnection())
    assert connection.MemcacheMiddleware not in middleware_types(connection.OLConnection(use_memcache=False))
