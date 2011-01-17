"""Caching utilities.
"""
import random
import string
import time
import threading

import memcache
import simplejson
import web

from infogami import config

class memcache_memoize:
    """Memoizes a function, caching its return values in memcached for each input.
    
    After the timeout, a new thread is spawned to update the value and the old
    value is used while the update is in progress.
    
    This expects that both the args and return value are json encodable.
    
    This uses the memcache servers specified in the configuration.
    
    :param f: function to be memozied
    :param key_prefix: key prefix used in memcache to store memoized results. A random value will be used if not specified.
    :param servers: list of  memcached servers, each specified as "ip:port"
    :param timeout: timeout in seconds after which the return value must be updated
    """
    def __init__(self, f, key_prefix=None, timeout=60):
        """Creates a new memoized function for ``f``.
        """
        self.f = f
        self.key_prefix = key_prefix or self._generate_key_prefix()
        self.timeout = timeout
        
        self._memcache = None
        
        self.stats = web.storage(
            calls=0,
            hits=0,
            updates=0,
            async_updates=0
        )
        self.active_threads = {}
    
    def _get_memcache(self):
        if self._memcache is None:
            servers = config.get("memcache_servers")
            if servers:
                self._memcache = memcache.Client(servers)
            else:
                web.debug("Could not find memcache_servers in the configuration. Used dummy memcache.")
                from openlibrary.mocks import mock_memcache
                self._memcache = mock_memcache.Client()
                
        return self._memcache
        
    memcache = property(_get_memcache)
        
    def _generate_key_prefix(self):
        try:
            prefix = self.f.__name__ + "_"
        except AttributeError, TypeError:
            prefix = ""
        
        return prefix + self._random_string(10)
        
    def _random_string(self, n):
        chars = string.letters + string.digits
        return "".join(random.choice(chars) for i in range(n))
        
    def __call__(self, *args, **kw):
        """Memoized function call.
        
        Returns the cached value when avaiable. Computes and adds the result
        to memcache when not available. Updates asynchronously after timeout.
        """
        self.stats.calls += 1
        
        value_time = self.memcache_get(args, kw)
        
        if value_time is None:
            self.stats.updates += 1
            value, t = self.update(*args, **kw)
        else:
            self.stats.hits += 1
            
            value, t = value_time
            if t + self.timeout < time.time():
                self.stats.async_updates += 1
                self.update_async(*args, **kw)
        
        return value
        
    def update_async(self, *args, **kw):
        """Starts the update process asynchronously.
        """
        t = threading.Thread(target=self._update_async_worker, args=args, kwargs=kw)
        self.active_threads[t.getName()] = t
        t.start()
        
    def _update_async_worker(self, *args, **kw):
        key = self.compute_key(args, kw) + "/flag"
        
        if not self.memcache.add(key, True):
            # already somebody else is computing this value.
            return
        
        try:
            self.update(*args, **kw)            
        finally:
            # Remove current thread from active threads, if it is present.
            self.active_threads.pop(threading.currentThread().getName(), None)
            
            # remove the flag
            self.memcache.delete(key)

    def update(self, *args, **kw):
        """Computes the value and adds it to memcache.

        Returns the computed value.
        """
        value = self.f(*args, **kw)
        t = time.time()
        
        self.memcache_add(args, kw, value, t)        
        return value, t
        
    def join_threads(self):
        """Waits for all active threads to finish.
        
        Used only in testing.
        """
        for name, thread in self.active_threads.items():
            thread.join()
                
    def encode_args(self, args, kw={}):
        """Encodes arguments to construct the memcache key.
        """
        # strip [ and ] from key
        a = self.json_encode(list(args))[1:-1] 
        
        if kw:
            return a + "-" + self.json_encode(kw)
        else:
            return a
        
    def compute_key(self, args, kw):
        """Computes memcache key for storing result of function call with given arguments.
        """
        return self.key_prefix + "-" + self.encode_args(args, kw)
        
    def json_encode(self, value):
        """simplejson.dumps without extra spaces.
        
        memcache doesn't like spaces in the key.
        """
        return simplejson.dumps(value, separators=(",", ":"))
        
    def json_decode(self, json):
        return simplejson.loads(json)
                
    def memcache_add(self, args, kw, value, time):
        """Adds value and time to memcache. Key is computed from the arguments.
        """
        key = self.compute_key(args, kw)
        json = self.json_encode([value, time])
        self.memcache.add(key, json)
        
    def memcache_get(self, args, kw):
        """Reads the value from memcahe. Key is computed from the arguments.
        
        Returns (value, time) when the value is available, None otherwise.
        """
        key = self.compute_key(args, kw)
        json = self.memcache.get(key)
        return json and self.json_decode(json)