"""Memcache interface to store data in memcached."""

import memcache
from olcompress import OLCompressor
import web

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
            value = self._client.get(web.safestr(key))
        except memcache.Client.MemcachedKeyError:
            return None
        
        return value and self.decompress(value)
        
    def get_multi(self, keys):
        keys = [web.safestr(k) for k in keys]
        d = self._client.get_multi(keys)
        return dict((web.safeunicode(k), self.decompress(v)) for k, v in d.items())
        
    def set(self, key, val, time=0):
        return self._client.set(web.safestr(key), self.compress(val), time=time)
    
    def set_multi(self, mapping, time=0):
        mapping = dict((web.safestr(k), self.compress(v)) for k, v in mapping.items())
        return self._client.set_multi(mapping, time=time)
        
    def add(self, key, val, time=0):
        return self._client.add(web.safestr(key), self.compress(val), time=time)

    def delete(self, key, time=0):
        key = web.safestr(key)
        return self._client.delete(key, time=time)
        
    def delete_multi(self, keys, time=0):
        keys = [web.safestr(k) for k in keys]
        return self._client.delete_multi(keys, time=time)