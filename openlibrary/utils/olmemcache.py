"""Memcache interface to store data in memcached."""

import memcache
import web
from prometheus_client import Histogram

from openlibrary.utils.olcompress import OLCompressor

# A sync client, so each call blocks its thread, or FastAPI's event loop
CALL_SECONDS = Histogram(
    "ol_memcache_call_seconds",
    "Duration of memcache calls, by operation.",
    ("op",),
    buckets=(0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5),
)


class Client:
    """Wrapper to memcache Client to enable OL specific compression and unicode keys.
    Compatible with memcache Client API.
    """

    def __init__(self, servers):
        self._client = memcache.Client(servers)
        compressor = OLCompressor()
        self.compress = compressor.compress
        self.decompress = compressor.decompress

    def get(self, key):
        try:
            with CALL_SECONDS.labels("get").time():
                value = self._client.get(web.safestr(key))
        except memcache.Client.MemcachedKeyError:
            return None

        return value and self.decompress(value)

    def get_multi(self, keys):
        keys = [web.safestr(k) for k in keys]
        with CALL_SECONDS.labels("get_multi").time():
            d = self._client.get_multi(keys)
        return {str(k): self.decompress(v) for k, v in d.items()}

    def set(self, key, val, time=0):
        val = self.compress(val)
        with CALL_SECONDS.labels("set").time():
            return self._client.set(web.safestr(key), val, time=time)

    def set_multi(self, mapping, time=0):
        mapping = {web.safestr(k): self.compress(v) for k, v in mapping.items()}
        with CALL_SECONDS.labels("set_multi").time():
            return self._client.set_multi(mapping, time=time)

    def add(self, key, val, time=0):
        val = self.compress(val)
        with CALL_SECONDS.labels("add").time():
            return self._client.add(web.safestr(key), val, time=time)

    def delete(self, key):
        key = web.safestr(key)
        with CALL_SECONDS.labels("delete").time():
            return self._client.delete(key)

    def delete_multi(self, keys, time=0):
        keys = [web.safestr(k) for k in keys]
        with CALL_SECONDS.labels("delete_multi").time():
            return self._client.delete_multi(keys, time=time)
