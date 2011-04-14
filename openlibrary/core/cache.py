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
from infogami.utils import stats

__all__ = [
    "cached_property",
    "Cache", "MemoryCache", "MemcacheCache", "RequestCache",
    "memoize", "memcache_memoize"
]

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
        
        if not self.memcache.add(key, "true"):
            # already somebody else is computing this value.
            return
        
        try:
            self.update(*args, **kw)            
        finally:
            # Remove current thread from active threads
            self.active_threads.pop(threading.currentThread().getName(), None)
            
            # remove the flag
            self.memcache.delete(key)

    def update(self, *args, **kw):
        """Computes the value and adds it to memcache.

        Returns the computed value.
        """
        value = self.f(*args, **kw)
        t = time.time()
        
        self.memcache_set(args, kw, value, t)
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
                
    def memcache_set(self, args, kw, value, time):
        """Adds value and time to memcache. Key is computed from the arguments.
        """
        key = self.compute_key(args, kw)
        json = self.json_encode([value, time])

        stats.begin("memcache.set", key=key)
        self.memcache.set(key, json)
        stats.end()
        
    def memcache_get(self, args, kw):
        """Reads the value from memcahe. Key is computed from the arguments.
        
        Returns (value, time) when the value is available, None otherwise.
        """
        key = self.compute_key(args, kw)

        stats.begin("memcache.get", key=key)
        json = self.memcache.get(key)
        stats.end(hit=bool(json))
        
        return json and self.json_decode(json)
        
####

def cached_property(name, getter):
    """Decorator like `property`, but the value is computed on first call and cached.
    
    class Foo:
        def create_memcache_client(self):
            ...
        memcache_client = cache_property("memcache_client", create_memcache_client)
    """
    def g(self):
        if name in self.__dict__:
            return self.__dict__[name]
            
        value = getter(self)
        self.__dict__[name] = value
        return value
    return property(g)

class Cache(object):
    """Cache interface."""
    def get(self, key):
        """Returns the value for given key. Returns None if that key is not present in the cache.
        """
        raise NotImplementedError()
    
    def set(self, key, value, expires=0):
        """Sets a value in the cache. 
        If expires is non-zero, the cache may delete that entry from the cache after expiry.
        The implementation can choose to ignore the expires argument.
        """
        raise NotImplementedError()
        
    def add(self, key, value, expires=0):
        """Adds a new entry in the cache. Nothing is done if there is already an entry with the same key.
        
        Returns True if a new entry is added to the cache.
        """
        raise NotImplementedError()
        
    def delete(self, key):
        """Deletes an entry from the cache. No error is raised if there is no entry in present in the cache with that key.
        
        Returns True if the key is deleted.
        """
        raise NotImplementedError()


class MemoryCache(Cache):
    """Cache implementation in memory.
    """
    def __init__(self):
        self.d = {}
        
    def get(self, key):
        return self.d.get(key)
        
    def set(self, key, value, expires=0):
        self.d[key] = value
    
    def add(self, key, value, expires=0):
        return self.d.setdefault(key, value) is value
    
    def delete(self, key):
        return self.d.pop(key, None) is not None


class MemcacheCache(Cache):
    """Cache implementation using memcache.
    
    Expects that the memcache servers are specified in web.config.memcache_servers.
    """
    def load_memcache(self):
        servers = web.config.get("memcache_servers", [])
        return memcache.Client(servers)
    
    memcache = cached_property("memcache", load_memcache)
    
    def get(self, key):
        return self.memcache.get(key)
        
    def set(self, key, value, expires=0):
        return self.memcache.set(key, value, expires)
        
    def add(self, key, value, expires=0):
        return self.memcache.add(key, value, expires)
        
    def delete(self, key):
        return self.memcache.delete(key)


class RequestCache(Cache):
    """Request-Local cache.
    
    The values are cached only in the context of the current request.
    """
    def get_d(self):
        return web.ctx.setdefault("request-local-cache", {})
    
    d = property(get_d)

    def get(self, key):
        return self.d.get(key)
        
    def set(self, key, value, expires=0):
        self.d[key] = value
    
    def add(self, key, value, expires=0):
        return self.d.setdefault(key, value) is value
    
    def delete(self, key):
        return self.d.pop(key, None) is not None

memory_cache = MemoryCache()
memcache_cache = MemcacheCache()
request_cache = RequestCache()

def _get_cache(engine):
    d = {
        "memory": memory_cache,
        "memcache": memcache_cache,
        "memcache+memory": memcache_cache,
        "request": request_cache
    }
    return d.get(engine)


def memoize(engine="memory", expires=0, background=False, key=None, cacheable=None):
    """Memoize decorator to cache results in various cache engines.
    
    Usage:
        
        @cache.memoize(engine="memcache")
        def some_func(args):
            pass
    
    Arguments:
    
    * engine:
        Engine to store the results. Available options are:
        
            * memory: stores the result in memory.
            * memcache: stores the result in memcached.
            * request: stores the result only in the context of the current request.
    
    * expires:
        The amount of time in seconds the value should be cached. Pass expires=0 to cache indefinitely.
        
    * background:
        Indicates that the value must be recomputed in the background after
        the timeout. Until the new value is ready, the function continue to
        return the same old value.
        
    * key:
        key to be used in the cache. If this is a string, arguments are append
        to it before making the cache-key. If this is a function, it's
        return-value is used as cache-key and this function is called with the
        arguments. If not specified, the default value is computed using the
        function name and module name.
        
    * cacheable:
        Function to determine if the returned value is cacheable. Sometimes it
        is desirable to not cache return values generated due to error
        conditions. The cacheable function is called with (key, value) as
        arguments.
        
    Advanced Usage:
    
    Sometimes, it is desirable to store results of related functions in the
    same cache entry to reduce memory usage. It can be achieved by making the
    ``key`` function return a tuple of two values. (Not Implemented yet)
    
        @cache.memoize(engine="memcache", key=lambda page: (page.key, "history"))
        def get_history(page):
            pass
            
        @cache.memoize(engine="memoize", key=lambda key: (key, "doc"))
        def get_page(key):
            pass
    """
    cache = _get_cache(engine)
    if cache is None:
        raise ValueError("Invalid cache engine: %r" % engine)
        
    def decorator(f):
        keyfunc = _make_key_func(key, f)
        return MemoizedFunction(f, cache, keyfunc, cacheable=cacheable)
    
    return decorator

def _make_key_func(key, f):
    key = key or (f.__module__ + "." + f.__name__)
    if isinstance(key, basestring):
        return PrefixKeyFunc(key)
    else:
        return key
    
class PrefixKeyFunc:
    """A function to generate cache keys using a prefix and arguments.
    """
    def __init__(self, prefix):
        self.prefix = prefix
    
    def __call__(self, *a, **kw):
        return self.prefix + "-" + self.encode_args(a, kw)
        
    def encode_args(self, args, kw={}):
        """Encodes arguments to construct the memcache key.
        """
        # strip [ and ] from key
        a = self.json_encode(list(args))[1:-1] 

        if kw:
            return a + "-" + self.json_encode(kw)
        else:
            return a
    
    def json_encode(self, value):
        """simplejson.dumps without extra spaces and consistant ordering of dictionary keys.

        memcache doesn't like spaces in the key.
        """
        return simplejson.dumps(value, separators=(",", ":"), sort_keys=True)
    
class MemoizedFunction:
    def __init__(self, f, cache, keyfunc, expires=0, background=False, cacheable=None):
        self.f = f
        self.cache = cache
        self.keyfunc = keyfunc
        self.expires = expires
        self.background = background
        self.cacheable = cacheable
        
    def __call__(self, *args, **kwargs):
        key = self.keyfunc(*args, **kwargs)
        value_time = self.cache.get(key)
        
        # value is not found in cache
        if value_time is None:
            value, t = self.update(key, args, kwargs)
        else:
            value, t = value_time
            
            # value is found in cache, but it is expired
            if self.expires and t + self.expires < time.time():
                # update the value
                if self.background:
                    self.update_async(key, args, kwargs)
                else:
                    value, t = self.update(key, args, kwargs)
        return value
        
    def update(self, key, args, kwargs):
        value = self.f(*args, **kwargs)
        t = time.time()

        if self.background:
            # Give more time to compute the value in background after expiry
            expires = 2*self.expires
        else:
            expires = self.expires
        
        if self.cacheable is None or self.cacheable(key, value):
            self.cache.set(key, [value, t], expires)
        return value, t

    def update_async(self, key, args, kwargs):
        """Starts the update process asynchronously.
        """
        t = threading.Thread(target=self._update_async_worker, args=(key, args, kwargs))
        t.start()

    def _update_async_worker(self, key, args, kwargs):
        flag_key = key + "/flag"

        # set a flag to tell indicate that this value is being computed
        if not self.cache.add(flag_key, "true", self.expires):
            # ignore if someone else has already started the compuration
            return

        try:
            self.update(key, args, kwargs)
        finally:
            # remove the flag
            self.cache.delete(flag_key)
            
    def __repr__(self):
        return "<Memoized %r>" % self.f
