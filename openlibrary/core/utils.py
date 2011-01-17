"""Generic utilities.
"""
import time

import memcache
import simplejson
import web

class memcache_memoize:
    """Memoizes a function, caching its return values in memcached for each input.
    
    After the timeout, a new thread is spawned to update the value and the old
    value is used while the update is in progress.
    
    This expects that both the args and return value are json encodable.
    """
    def __init__(self, f, key, servers, timeout=60):
        """Creates a new memoized function for ``f``.
        
        :param f: function to be memozied
        :param key: key prefix used in memcache to store memoized results
        :param servers: list of  memcached servers, each specified as "ip:port"
        :param timeout: timeout in seconds after which the return value must be updated
        """
        self.f = f
        self.key = key
        self.timeout = timeout
        self.memcache = memcache.Client(servers)
        
        self.hits = 0
        self.calls = 0
        self.stats = web.storage(
            calls=0,
            hits=0,
            updates=0,
            async_updates=0
        )
        
    def __call__(self, *args, **kw):
        self.stats.calls += 1
        
        key = self.encode_args(args, kw)
        value_time = self.memcache.get(key)
        
        if value_time is None:
            value, time = self.update(*args, **kw)
        else:
            self.hits += 1
            value, time = value_time
            if time + self.timeout > time.time():
                self.update_async(*args, **kw)
        return value
        
    def update_async(self, *args, **kw):
        self.stats.async_updates += 1
        threading.Thread(target=self.update, args=args, kwargs=kw).start()

    def update(self, *args, **kw):
        self.stats.updates += 1
        
        key = self.compute_key(args, kw)
        value = self.f(*args, **kw)
        t = time.time()
        
        json = self.json_encode([value, t])
        self.memcache.add(key, json)
        
        return value, t
                
    def encode_args(self, args, kw={}):
        # strip [ and ] from key
        a = self.json_encode(list(args))[1:-1] 
        
        if kw:
            return a + "-" + self.json_encode(kw)
        else:
            return a
            
    def compute_key(self, args, kw):
        """Computes memcache key for storeing result with given arguments.
        """
        return self.key + "-" + self.encode_args(args, kw)
        
    def json_encode(self, value):
        """simplejson.dumps without extra spaces.
        
        memcache doesn't like spaces in the key.
        """
        return simplejson.dumps(value, separators=(",", ":"))