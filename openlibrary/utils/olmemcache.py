"""Memcache interface to store data in memcached."""

import memcache
import web

from openlibrary.utils.olcompress import OLCompressor
from openlibrary.utils.saturation_metrics import MEMCACHE_CALL


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
            with MEMCACHE_CALL.labels("get").time():
                value = self._client.get(web.safestr(key))
        except memcache.Client.MemcachedKeyError:
            return None

        return value and self.decompress(value)

    def get_multi(self, keys):
        keys = [web.safestr(k) for k in keys]
        with MEMCACHE_CALL.labels("get_multi").time():
            d = self._client.get_multi(keys)
        return {str(k): self.decompress(v) for k, v in d.items()}

    def set(self, key, val, time=0):
        val = self.compress(val)
        with MEMCACHE_CALL.labels("set").time():
            return self._client.set(web.safestr(key), val, time=time)

    def set_multi(self, mapping, time=0):
        mapping = {web.safestr(k): self.compress(v) for k, v in mapping.items()}
        with MEMCACHE_CALL.labels("set_multi").time():
            return self._client.set_multi(mapping, time=time)

    def add(self, key, val, time=0):
        val = self.compress(val)
        with MEMCACHE_CALL.labels("add").time():
            return self._client.add(web.safestr(key), val, time=time)

    def delete(self, key):
        key = web.safestr(key)
        with MEMCACHE_CALL.labels("delete").time():
            return self._client.delete(key)

    def delete_multi(self, keys, time=0):
        keys = [web.safestr(k) for k in keys]
        with MEMCACHE_CALL.labels("delete_multi").time():
            return self._client.delete_multi(keys, time=time)
