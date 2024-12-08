"""Caching utilities.
"""

import functools
import hashlib
import json
import random
import string
import threading
import time
from collections.abc import Callable
from typing import Any, Literal, cast

import memcache
import web

from infogami import config
from infogami.infobase.client import Nothing
from infogami.utils import stats
from openlibrary.core.helpers import NothingEncoder
from openlibrary.utils import olmemcache
from openlibrary.utils.dateutil import MINUTE_SECS

__all__ = [
    "cached_property",
    "Cache",
    "MemoryCache",
    "MemcacheCache",
    "RequestCache",
    "memoize",
    "memcache_memoize",
    "get_memcache",
]

DEFAULT_CACHE_LIFETIME = 2 * MINUTE_SECS


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
    :param prethread: Function to call on the new thread to set it up
    """

    def __init__(
        self,
        f: Callable,
        key_prefix: str | None = None,
        timeout: int = MINUTE_SECS,
        prethread: Callable | None = None,
        hash_args: bool = False,
    ):
        """Creates a new memoized function for ``f``."""
        self.f = f
        self.key_prefix = key_prefix or self._generate_key_prefix()
        self.timeout = timeout

        self._memcache = None

        self.stats = web.storage(calls=0, hits=0, updates=0, async_updates=0)
        self.active_threads: dict = {}
        self.prethread = prethread
        self.hash_args = hash_args

    def _get_memcache(self):
        if self._memcache is None:
            servers = config.get("memcache_servers")
            if servers:
                self._memcache = memcache.Client(servers)
            else:
                web.debug(
                    "Could not find memcache_servers in the configuration. Used dummy memcache."
                )
                try:
                    import mockcache  # Only supports legacy Python

                    self._memcache = mockcache.Client()
                except ImportError:  # Python 3
                    from pymemcache.test.utils import MockMemcacheClient

                    self._memcache = MockMemcacheClient()

        return self._memcache

    memcache = property(_get_memcache)

    def _generate_key_prefix(self):
        try:
            prefix = self.f.__name__ + "_"
        except (AttributeError, TypeError):
            prefix = ""

        return prefix + self._random_string(10)

    def _random_string(self, n):
        chars = string.ascii_letters + string.digits
        return "".join(random.choice(chars) for i in range(n))

    def __call__(self, *args, **kw):
        """Memoized function call.

        Returns the cached value when available. Computes and adds the result
        to memcache when not available. Updates asynchronously after timeout.
        """
        _cache = kw.pop("_cache", None)
        if _cache == "delete":
            self.memcache_delete(args, kw)
            return None

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
        """Starts the update process asynchronously."""
        t = threading.Thread(target=self._update_async_worker, args=args, kwargs=kw)
        self.active_threads[t.name] = t
        t.start()

    def _update_async_worker(self, *args, **kw):
        key = self.compute_key(args, kw) + "/flag"

        if not self.memcache.add(key, "true"):
            # already somebody else is computing this value.
            return

        try:
            if self.prethread:
                self.prethread()
            self.update(*args, **kw)
        finally:
            # Remove current thread from active threads
            self.active_threads.pop(threading.current_thread().name, None)

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
        for name, thread in list(self.active_threads.items()):
            thread.join()

    def encode_args(self, args, kw=None):
        """Encodes arguments to construct the memcache key."""
        kw = kw or {}

        # strip [ and ] from key
        a = self.json_encode(list(args))[1:-1]

        if kw:
            a = a + "-" + self.json_encode(kw)
        if self.hash_args:
            return f"{hashlib.md5(a.encode('utf-8')).hexdigest()}"
        return a

    def compute_key(self, args, kw):
        """Computes memcache key for storing result of function call with given arguments."""
        key = self.key_prefix + "$" + self.encode_args(args, kw)
        return key.replace(
            " ", "_"
        )  # XXX: temporary fix to handle spaces in the arguments

    def json_encode(self, value):
        """json.dumps without extra spaces.

        memcache doesn't like spaces in the key.
        """
        return json.dumps(
            [] if isinstance(value, Nothing) else value,
            separators=(",", ":"),
            cls=NothingEncoder,
        )

    def memcache_set(self, args, kw, value, time):
        """Adds value and time to memcache. Key is computed from the arguments."""
        key = self.compute_key(args, kw)
        json_data = self.json_encode([value, time])

        stats.begin("memcache.set", key=key)
        self.memcache.set(key, json_data)
        stats.end()

    def memcache_delete(self, args, kw):
        key = self.compute_key(args, kw)
        stats.begin("memcache.delete", key=key)
        self.memcache.delete(key)
        stats.end()

    def memcache_get(self, args, kw):
        """Reads the value from memcache. Key is computed from the arguments.

        Returns (value, time) when the value is available, None otherwise.
        """
        key = self.compute_key(args, kw)
        stats.begin("memcache.get", key=key)
        json_str = self.memcache.get(key)
        stats.end(hit=bool(json_str))

        return json_str and json.loads(json_str)


####


def cached_property(getter):
    """Decorator like `property`, but the value is computed on first call and cached.

    class Foo:

        @cached_property
        def memcache_client(self):
            ...
    """
    name = getter.__name__

    def g(self):
        if name in self.__dict__:
            return self.__dict__[name]

        value = getter(self)
        self.__dict__[name] = value
        return value

    return property(g)


class Cache:
    """Cache interface."""

    def get(self, key):
        """Returns the value for given key. Returns None if that key is not present in the cache."""
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
    """Cache implementation in memory."""

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

    def clear(self):
        self.d.clear()


class MemcacheCache(Cache):
    """Cache implementation using memcache.

    The values are json-encoded before adding to memcache and json-decoded on get.

    Expects that the memcache servers are specified in web.config.memcache_servers.
    """

    @cached_property
    def memcache(self):
        if servers := config.get("memcache_servers", None):
            return olmemcache.Client(servers)
        else:
            web.debug(
                "Could not find memcache_servers in the configuration. Used dummy memcache."
            )
            try:
                import mockcache

                return mockcache.Client()
            except ImportError:
                from pymemcache.test.utils import MockMemcacheClient

                return MockMemcacheClient()

    def _encode_key(self, key: str) -> str:
        return cast(str, web.safestr(key))

    def get(self, key: str) -> Any:
        key = self._encode_key(key)
        stats.begin("memcache.get", key=key)
        value = self.memcache.get(key)
        stats.end(hit=value is not None)
        return value and json.loads(value)

    def get_multi(self, keys: list[str]) -> dict[str, Any]:
        keys = [self._encode_key(k) for k in keys]
        stats.begin("memcache.get_multi")
        d = self.memcache.get_multi(keys)
        stats.end(hit=bool(d))
        return {k: json.loads(v) for k, v in d.items()}

    def set_multi(self, mapping: dict[str, Any], expires=0):
        mapping = {self._encode_key(k): json.dumps(v) for k, v in mapping.items()}
        stats.begin("memcache.set_multi")
        d = self.memcache.set_multi(mapping, expires)
        stats.end()
        return d

    def set(self, key: str, value: Any, expires=0):
        key = cast(str, web.safestr(key))
        value = json.dumps(value)
        stats.begin("memcache.set", key=key)
        value = self.memcache.set(key, value, expires)
        stats.end()
        return value

    def add(self, key, value, expires=0):
        key = web.safestr(key)
        value = json.dumps(value)
        stats.begin("memcache.add", key=key)
        value = self.memcache.add(key, value, expires)
        stats.end()
        return value

    def delete(self, key):
        key = web.safestr(key)
        stats.begin("memcache.delete", key=key)
        value = self.memcache.delete(key)
        stats.end()
        return value


class RequestCache(Cache):
    """Request-Local cache.

    The values are cached only in the context of the current request.
    """

    @property
    def d(self):
        return web.ctx.setdefault("request-local-cache", {})

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


def get_memcache():
    return memcache_cache


def _get_cache(engine):
    d = {
        "memory": memory_cache,
        "memcache": memcache_cache,
        "memcache+memory": memcache_cache,
        "request": request_cache,
    }
    return d.get(engine)


class memoize:
    """Memoize decorator to cache results in various cache engines.

    Usage::

        @cache.memoize(engine="memcache")
        def some_func(args):
            pass

    Arguments::

    * engine:
        Engine to store the results. Available options are:
            * memory: stores the result in memory.
            * memcache: stores the result in memcached.
            * request: stores the result only in the context of the current request.

    * key:
        key to be used in the cache. If this is a string, arguments are append
        to it before making the cache-key. If this is a function, it's
        return-value is used as cache-key and this function is called with the
        arguments. If not specified, the default value is computed using the
        function name and module name.

    * expires:
        The amount of time in seconds the value should be cached. Pass expires=0 to cache indefinitely.
        (Not yet implemented)

    * background:
        Indicates that the value must be recomputed in the background after
        the timeout. Until the new value is ready, the function continue to
        return the same old value.
        (not yet implemented)

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

        @cache.memoize(engine="memory", key=lambda key: (key, "doc"))
        def get_page(key):
            pass
    """

    def __init__(
        self,
        engine: Literal["memory", "memcache", "request"],
        key: str | Callable[..., str | tuple],
        expires: int = 0,
        background: bool = False,
        cacheable: Callable | None = None,
    ):
        self.cache = _get_cache(engine)
        self.keyfunc = (
            key if callable(key) else functools.partial(build_memcache_key, key)
        )
        self.cacheable = cacheable
        self.expires = expires

    def __call__(self, f):
        """Returns the memoized version of f."""

        @functools.wraps(f)
        def func(*args, **kwargs):
            """The memoized function.

            If this is the first call with these arguments, function :attr:`f` is called and the return value is cached.
            Otherwise, value from the cache is returned.
            """
            key = self.keyfunc(*args, **kwargs)
            value = self.cache_get(key)
            if value is None:
                value = f(*args, **kwargs)
                self.cache_set(key, value)
            return value

        return func

    def cache_get(self, key: str | tuple):
        """Reads value of a key from the cache.

        When key is a string, this is equvivalant to::

            return cache[key]

        When key is a 2-tuple, this is equvivalant to::

            k0, k1 = key
            return cache[k0][k1]
        """
        if isinstance(key, tuple):
            k0, k1 = key
            d = self.cache.get(k0)
            return d and d.get(k1)
        else:
            return self.cache.get(key)

    def cache_set(self, key: str | tuple, value):
        """Sets a key to a given value in the cache.

        When key is a string, this is equvivalant to::

            cache[key] = value

        When key is a 2-tuple, this is equvivalant to::

            k0, k1 = key
            cache[k0][k1] = value
        """
        # When cacheable is provided, use it to determine whether or not the cache should be updated.
        if self.cacheable and self.cacheable(key, value) is False:
            return

        if isinstance(key, tuple):
            k1, k2 = key
            d = self.cache.get(k1) or {}
            d[k2] = value
            return self.cache.set(k1, d, expires=self.expires)
        else:
            return self.cache.set(key, value, expires=self.expires)


def build_memcache_key(prefix: str, *args, **kw) -> str:
    key = prefix

    if args:
        key += "-" + json.dumps(args, separators=(",", ":"), sort_keys=True)[1:-1]
    if kw:
        key += "-" + json.dumps(kw, separators=(",", ":"), sort_keys=True)

    return key


def method_memoize(f):
    """
    object-local memoize.
    Works only for functions with simple arguments; i.e. JSON serializeable
    """

    @functools.wraps(f)
    def g(self, *args, **kwargs):
        cache = self.__dict__.setdefault('_memoize_cache', {})
        key = json.dumps(
            {
                'function': f.__name__,
                'args': args,
                'kwargs': kwargs,
            },
            sort_keys=True,
        )

        if key not in cache:
            cache[key] = f(self, *args, **kwargs)
        return cache[key]

    return g
