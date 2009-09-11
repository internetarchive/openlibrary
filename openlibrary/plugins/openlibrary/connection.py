"""Open Library extension to provide a new kind of client connection with caching support.
"""
from infogami import config
from infogami.infobase import client, lru
import web
import simplejson

default_cache_prefixes = ["/type/", "/l/", "/index.", "/about", "/css/", "/js/"]

class ConnectionProcessor:
    """Wrapper over Infobase connection to add additional functionality."""
    def request(self, super, sitename, path, method, data):
        if path == '/get':
            return self.get(super, sitename, data)
        elif path == '/write':
            return self.write(super, sitename, data)
        elif path.startswith('/save/'):
            return self.save(super, sitename, path, data)
        elif path == '/save_many':
            return self.save_many(super, sitename, data)
        else:
            return super.request(sitename, path, method, data)
            
    def get(self, super, sitename, data):
        return super.get(sitename, data)
        
    def write(self, super, sitename, data):
        return super.write(sitename, data)

    def save(self, super, sitename, path, data):
        return super.save(sitename, path, data)

    def save_many(self, super, sitename, data):
        return super.save_many(sitename, data)
        
class CacheProcessor(ConnectionProcessor):
    """Connection Processor to provide local cache."""
    def __init__(self, cache_prefixes, cache_size=10000, memcache_servers=None):
        self.cache_prefixes = cache_prefixes
        self.cache = cache = lru.LRU(cache_size)
        
        if memcache_servers:
            import memcache
            self.memcache = memcache.Client(memcache_servers)
        else:
            self.memcache = {}
        
        class hook(client.hook):
            def on_new_version(self, page):
                if page.key in cache:
                    cache.delete(page.key)
    
    def get(self, super, sitename, data):
        key = data.get('key')
        revision = data.get('revision')

        if revision is None and self.cachable(key):
            response = self.cache.get(key) or self.memcache.get(web.safestr(key))
            if not response:
                response = super.get(sitename, data)
                self.cache[key] = response
        else:
            response = super.get(sitename, data)
        return response
        
    def write(self, super, sitename, data):
        response_str = super.write(sitename, data)
        
        result = simplejson.loads(response_str)
        modified = result['created'] + result['updated']
        keys = [k for k in modified if self.cachable(k)]
        self.cache.delete_many(keys)

        return response_str

    def save(self, super, sitename, path, data):
        response_str = super.save(sitename, path, data)
        result = simplejson.loads(response_str)
        if result:
            self.cache.delete(result['key'])

        return response_str

    def save_many(self, super, sitename, data):
        response_str = super.save_many(sitename, data)
        result = simplejson.loads(response_str)
        keys = [r['key'] for r in result]
        self.cache.delete_many(keys)
        return response_str
        
    def cachable(self, key):
        """Tests if key is cacheable."""
        for prefix in self.cache_prefixes:
            if key.startswith(prefix):
                return True
        return False
        
class ConnectionProxy(client.Connection):
    """Creates a new connection by attaching a processor to an existing connection."""
    def __init__(self, conn, processor):
        self.conn = conn
        self.processor = processor

    def get_auth_token(self):
        return self.conn.get_auth_token()

    def set_auth_token(self, token):
        self.conn.set_auth_token(token)
        
    def request(self, sitename, path, method='GET', data=None):
        class Super:
            def request(self, sitename, path, method='GET', data=None):
                return conn.request(sitename, path, method, data)
                
            def get(self, sitename, data):
                return conn.request(sitename, '/get', 'GET', data=data)

            def write(self, sitename, data):
                return conn.request(sitename, '/write', 'POST', data=data)

            def save(self, sitename, path, data):
                return conn.request(sitename, path, 'POST', data=data)

            def save_many(self, sitename, data):
                return conn.request(sitename, '/save_many', 'POST', data=data)
                
        conn = self.conn
        super = Super()
        return self.processor.request(super, sitename, path, method, data)

conn_processors = None
def get_processors(): 
    def f():
        cache_prefixes = config.get("cache_prefixes", default_cache_prefixes)
        if cache_prefixes :
            yield CacheProcessor(cache_prefixes, memcache_servers=config.get('memcache_servers'))
        
    global conn_processors
    if conn_processors is None:
        conn_processors = list(f())
    return conn_processors       

class OLConnection(client.Connection):
    """Open Library connection with customizable processor support.    
    """
    def __init__(self):
        client.Connection.__init__(self)
        
        self.conn = self.create_connection()
        processors = get_processors()
        for p in processors:
            self.conn = ConnectionProxy(self.conn, p)
    
    def create_connection(self):
        if config.get('infobase_server'):
            return client.connect(type='remote', base_url=config.infobase_server)
        elif config.get('db_parameters'):
            return client.connect(type='local', **config.db_parameters)
        else:
            raise Exception("db_parameters are not specified in the configuration")
                
    def request(self, sitename, path, method='GET', data=None):
        return self.conn.request(sitename, path, method, data)

    def get_auth_token(self):
        return self.conn.get_auth_token()

    def set_auth_token(self, token):
        self.conn.set_auth_token(token)

