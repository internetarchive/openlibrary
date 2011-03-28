"""Open Library extension to provide a new kind of client connection with caching support.
"""
from infogami import config
from infogami.infobase import client, lru
from infogami.utils import stats

import web
import simplejson

default_cache_prefixes = ["/type/", "/languages/", "/index.", "/about", "/css/", "/js/", "/config/"]

class ConnectionMiddleware:
    def __init__(self, conn):
        self.conn = conn
        
    def get_auth_token(self):
        return self.conn.get_auth_token()

    def set_auth_token(self, token):
        self.conn.set_auth_token(token)

    def request(self, sitename, path, method='GET', data=None):
        if path == '/get':
            return self.get(sitename, data)
        elif path == '/get_many':
            return self.get_many(sitename, data)
        elif path == '/write':
            return self.write(sitename, data)
        elif path.startswith('/save/'):
            return self.save(sitename, path, data)
        elif path == '/save_many':
            return self.save_many(sitename, data)
        elif path.startswith("/_store/") and not path.startswith("/_store/_"):
            if method == 'GET':
                return self.store_get(sitename, path)
            elif method == 'PUT':
                return self.store_put(sitename, path, data)
            elif method == 'DELETE':
                return self.store_delete(sitename, path, data)
                
        return self.conn.request(sitename, path, method, data)

    def get(self, sitename, data):
        return self.conn.request(sitename, '/get', 'GET', data)

    def get_many(self, sitename, data):
        return self.conn.request(sitename, '/get_many', 'GET', data)

    def write(self, sitename, data):
        return self.conn.request(sitename, '/write', 'POST', data)

    def save(self, sitename, path, data):
        return self.conn.request(sitename, path, 'POST', data)

    def save_many(self, sitename, data):
        return self.conn.request(sitename, '/save_many', 'POST', data)
        
    def store_get(self, sitename, path):
        return self.conn.request(sitename, path, 'GET')
        
    def store_put(self, sitename, path, data):
        return self.conn.request(sitename, path, 'PUT', data)
    
    def store_delete(self, sitename, path, data):
        return self.conn.request(sitename, path, 'DELETE', data)
        
_memcache = None
        
class MemcacheMiddleware(ConnectionMiddleware):
    def __init__(self, conn, memcache_servers):
        ConnectionMiddleware.__init__(self, conn)
        self.memcache = self.get_memcache(memcache_servers)
        
    def get_memcache(self, memcache_servers):
        global _memcache
        if _memcache is None:
            from openlibrary.utils import olmemcache
            _memcache = olmemcache.Client(memcache_servers)
        return _memcache

    def get(self, sitename, data):
        key = data.get('key')
        revision = data.get('revision')
        
        if revision is None:
            stats.begin("memcache.get", key=key)
            result = self.memcache.get(key)
            stats.end(hit=bool(result))
        else:
            result = None
            
        return result or ConnectionMiddleware.get(self, sitename, data)
    
    def get_many(self, sitename, data):
        keys = simplejson.loads(data['keys'])
        
        stats.begin("memcache.get_multi")
        result = self.memcache.get_multi(keys)
        stats.end(found=len(result))
        
        keys2 = [k for k in keys if k not in result]
        if keys2:
            data['keys'] = simplejson.dumps(keys2)
            result2 = ConnectionMiddleware.get_many(self, sitename, data)
            result.update(simplejson.loads(result2))
        
        #@@ too many JSON conversions
        for k in result:
            if isinstance(result[k], basestring):
                result[k] = simplejson.loads(result[k])
                
        return simplejson.dumps(result)

    def mc_get(self, key):
        stats.begin("memcache.get", key=key)
        result = self.memcache.get(key)
        stats.end(hit=bool(result))
        return result
    
    def mc_delete(self, key):
        stats.begin("memcache.delete", key=key)
        self.memcache.delete(key)
        stats.end()
        
    def mc_add(self, key, value):
        stats.begin("memcache.add", key=key)
        self.memcache.add(key, value)
        stats.end()

    def store_get(self, sitename, key):
        result = self.mc_get(key)

        if result is None:
            result = ConnectionMiddleware.store_get(self, sitename, key)
            if result:
                self.mc_add(key, result)
        return result

    def store_put(self, sitename, key, data):
        # deleting before put to make sure the entry is deleted even if the
        # process dies immediately after put.
        # Still there is very very small chance of invalid cache if someone else
        # updates memcache after stmt-1 and this process dies after stmt-2.
        self.mc_delete(key)
        result = ConnectionMiddleware.store_put(self, sitename, key, data)
        self.mc_delete(key)
        return result
        
    def store_delete(self, sitename, key, data):
        # see comment in store_put
        self.mc_delete(key)
        result = ConnectionMiddleware.store_delete(self, sitename, key, data)
        self.mc_delete(key)
        return result
        
_cache = None
        
class LocalCacheMiddleware(ConnectionMiddleware):
    def __init__(self, conn, cache_prefixes, cache_size=10000):
        ConnectionMiddleware.__init__(self, conn)
        self.cache_prefixes = cache_prefixes
        self.cache = self.get_cache(cache_size)
        
    def get_cache(self, cache_size):
        global _cache
        if _cache is None:
            _cache = lru.LRU(cache_size)

            class hook(client.hook):
                def on_new_version(self, page):
                    if page.key in _cache:
                        _cache.delete(page.key)
            
        return _cache
    
    def get(self, sitename, data):
        key = data.get('key')
        revision = data.get('revision')

        def _get():
            return ConnectionMiddleware.get(self, sitename, data)

        if revision is None and self.cachable(key):
            response = self.cache.get(key)
            if not response:
                response = _get()
                self.cache[key] = response
        else:
            response = _get()
        return response
        
    def write(self, sitename, data):
        response_str = ConnectionMiddleware.write(self, sitename, data)

        result = simplejson.loads(response_str)
        modified = result['created'] + result['updated']
        keys = [k for k in modified if self.cachable(k)]
        self.cache.delete_many(keys)
        return response_str

    def save(self, sitename, path, data):
        response_str = ConnectionMiddleware.save(self, sitename, path, data)
        result = simplejson.loads(response_str)
        if result:
            self.cache.delete(result['key'])
        return response_str

    def save_many(self, sitename, data):
        response_str = ConnectionMiddleware.save_many(self, sitename, data)
        result = simplejson.loads(response_str)
        keys = [r['key'] for r in result]
        self.cache.delete_many(keys)
        return response_str

    def cachable(self, key):
        """Tests if key is cacheable."""
        for prefix in self.cache_prefixes:
            if key and key.startswith(prefix):
                return True
        return False
        
class MigrationMiddleware(ConnectionMiddleware):
    """Temporary middleware to handle upstream to www migration."""
    def _process_key(self, key):
        mapping = (
            "/l/", "/languages/",
            "/a/", "/authors/",
            "/b/", "/books/",
            "/user/", "/people/"
        )
        
        if "/" in key and key.split("/")[1] in ['a', 'b', 'l', 'user']:
            for old, new in web.group(mapping, 2):
                if key.startswith(old):
                    return new + key[len(old):]
        return key
    
    def exists(self, key):
        try:
            d = ConnectionMiddleware.get(self, "openlibrary.org", {"key": key})
            return True
        except client.ClientException, e:
            return False
    
    def _process(self, data):
        if isinstance(data, list):
            return [self._process(d) for d in data]
        elif isinstance(data, dict):
            if 'key' in data:
                data['key'] = self._process_key(data['key'])
            return dict((k, self._process(v)) for k, v in data.iteritems())
        else:
            return data
    
    def get(self, sitename, data):
        if web.ctx.get('path') == "/api/get" and 'key' in data:
            data['key'] = self._process_key(data['key'])
            
        response = ConnectionMiddleware.get(self, sitename, data)
        if response:
            data = simplejson.loads(response)
            data = self._process(data)
            data = data and self.fix_doc(data)
            response = simplejson.dumps(data)
        return response
        
    def fix_doc(self, doc):
        type = doc.get("type", {}).get("key") 
        
        if type == "/type/work":
            if doc.get("authors"):
                # some record got empty author records because of an error
                # temporary hack to fix 
                doc['authors'] = [a for a in doc['authors'] if 'author' in a]
        elif type == "/type/edition":
            # get rid of title_prefix.
            if 'title_prefix' in doc:
                title = doc['title_prefix'].strip() + ' ' + doc.get('title', '')
                doc['title'] = title.strip()
                del doc['title_prefix']
        return doc
        
    def get_many(self, sitename, data):
        response = ConnectionMiddleware.get_many(self, sitename, data)
        if response:
            data = simplejson.loads(response)
            data = self._process(data)
            data = dict((key, self.fix_doc(doc)) for key, doc in data.items())
            response = simplejson.dumps(data)
        return response

def OLConnection():
    """Create a connection to Open Library infobase server."""
    def create_connection():
        if config.get('infobase_server'):
            return client.connect(type='remote', base_url=config.infobase_server)
        elif config.get('db_parameters'):
            return client.connect(type='local', **config.db_parameters)
        else:
            raise Exception("db_parameters are not specified in the configuration")

    conn = create_connection()

    if config.get('memcache_servers'):
        conn = MemcacheMiddleware(conn, config.get('memcache_servers'))
    
    cache_prefixes = config.get("cache_prefixes", default_cache_prefixes)
    if cache_prefixes :
        conn = LocalCacheMiddleware(conn, cache_prefixes)

    if config.get('upstream_to_www_migration'):
        conn = MigrationMiddleware(conn)

    return conn

