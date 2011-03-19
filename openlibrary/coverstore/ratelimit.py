"""Ratelimit implementation for coverstore.

Adopted from https://github.com/simonw/ratelimitcache
"""
import functools
import memcache
import datetime
import web

from openlibrary.coverstore import config

class ratelimit(object):
    "Instances of this class can be used as decorators"
    
    # This class is designed to be sub-classed
    minutes = 5 # The time period
    requests = 100 # Number of allowed requests in that time period
    
    prefix = 'rl-' # Prefix for memcache key
    
    def __init__(self, **options):
        for key, value in options.items():
            setattr(self, key, value)
            
        self._cache = None
            
    def get_cache(self):
        if self._cache is None:
            self._cache = memcache.Client(config.ol_memcache_servers)
        return self._cache
            
    def __call__(self, fn):
        def wrapper(*args, **kwargs):
            return self.view_wrapper(fn, *args, **kwargs)
        functools.update_wrapper(wrapper, fn)
        return wrapper
    
    def view_wrapper(self, fn, *args, **kwargs):
        if not self.should_ratelimit():
            return fn(*args, **kwargs)
        
        counts = self.get_counters().values()
        
        # Have they failed?
        if sum(counts) >= self.requests:
            return self.disallowed()
        else:
            # Increment rate limiting counter
            self.cache_incr(self.current_key())        
        
        return fn(*args, **kwargs)
    
    def cache_get_many(self, keys):
        keys = [web.safestr(key) for key in keys]
        return self.get_cache().get_multi(keys)
    
    def cache_incr(self, key):
        key = web.safestr(key)
        # add first, to ensure the key exists
        self.get_cache().incr(key, 1) or self.get_cache().set(key, 1, time=self.expire_after())
    
    def should_ratelimit(self):
        # ratelimit only if memcache is enabled
        return bool(config.get("memcache_servers"))
    
    def get_counters(self):
        return self.cache_get_many(self.keys_to_check())
    
    def keys_to_check(self):
        now = datetime.datetime.now()
        return [
            '%s%s-%s' % (
                self.prefix,
                web.ctx.ip,
                (now - datetime.timedelta(minutes = minute)).strftime('%Y%m%d%H%M')
            ) for minute in range(self.minutes + 1)
        ]
    
    def current_key(self):
        return '%s%s-%s' % (
            self.prefix,
            web.ctx.ip,
            datetime.datetime.now().strftime('%Y%m%d%H%M')
        )
        
    def disallowed(self):
        "Over-ride this method if you want to log incidents"
        raise web.Forbidden('Rate limit exceeded')
    
    def expire_after(self):
        "Used for setting the memcached cache expiry"
        return (self.minutes + 1) * 60
