#!/usr/bin/env python
import sys
import schema

import infogami
from infogami.infobase import client, lru
import web

config = web.storage(
    db_parameters = None,
    infobase_server = None,
    writelog = None,
    booklog = None,
    errorlog = None,
    memcache_servers = None,
    cache_prefixes = ['/type/', '/l/', '/index.', '/about'], # objects with key starting with these prefixes will be cached locally.
)

class ConnectionProcessor:
    """Wrapper over Infobase connection to add additional functionality."""
    def request(self, super, sitename, path, method, data):
        if path == '/get':
            return self.get(super, sitename, data)
        elif path == '/write':
            return self.write(super, sitename, data)
        else:
            return super.request(sitename, path, method, data)
            
    def get(self, super, sitename, data):
        return super.get(sitename, data)
        
    def write(self, super, sitename, data):
        return super.write(sitename, data)
        
class CacheProcessor(ConnectionProcessor):
    """Connection Processor to provide local cache."""
    def __init__(self, cache_prefixes, cache_size=10000):
        self.cache_prefixes = cache_prefixes
        self.cache = lru.LRU(cache_size)
        
    def get(self, super, sitename, data):
        key = data.get('key')
        revision = data.get('revision')
        
        if revision is None and self.cachable(key):
            response = self.cache.get(key)
            if not response:
                response = super.get(sitename, data)
                self.cache[key] = response
        else:
            response = super.get(sitename, data)
        return response
        
    def write(self, super, sitename, data):
        import simplejson
        response_str = super.write(sitename, data)
        
        response = simplejson.loads(response_str)
        if response['status'] == 'ok':
            result = response['result']
            modified = result['created'] + result['updated']
            for k in modified:
                if self.cachable(k):
                    del self.cache[k]
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
        
    def request(self, sitename, path, method='GET', data=None):
        class Super:
            def request(self, sitename, path, method='GET', data=None):
                return conn.request(sitename, path, method, data)
                
            def get(self, sitename, data):
                return conn.request(sitename, '/get', 'GET', data=data)

            def write(self, sitename, data):
                return conn.request(sitename, '/write', 'POST', data=data)
                
        conn = self.conn
        super = Super()
        return self.processor.request(super, sitename, path, method, data)

conn_processors = None
def get_processors(): 
    def f():
        if config.cache_prefixes:
            yield CacheProcessor(config.cache_prefixes)
        
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
        if config.infobase_server:
            return client.connect(type='remote', base_url=config.infobase_server)
        else:
            return client.connect(type='local', **config.db_parameters)
                
    def request(self, sitename, path, method='GET', data=None):
        return self.conn.request(sitename, path, method, data)
        
client._connection_types['ol'] = OLConnection

def get_infobase():
    """Creates infobase object."""
    from infogami.infobase import infobase, dbstore, cache
    web.config.db_printing = True
    web.load()

    # hack to make cache work for local infobase connections
    cache.loadhook()
    web.ctx.ip = '127.0.0.1'

    store = dbstore.DBStore(schema.get_schema())

    ib = infobase.Infobase(store, infobase.config.secret_key)
    return ib
    
def run():
    import infogami.infobase.server
    infogami.infobase.server._infobase = get_infobase()
    infogami.run()

def create(site='openlibrary.org'):
    get_infobase().create(site)
    
def run_client():
    """Run OpenLibrary as client.
    Requires a separate infobase server to be running.
    """
    assert config.infobase_server is not None, "Please specify ol.config.infobase_server"
    infogami.run()
    
def run_server():
    """Run Infobase server."""
    web.config.db_parameters = config.db_parameters
    web.load()   
    
    from infogami.infobase import server
    server._infobase = get_infobase()

    if '--create' in sys.argv:
        server._infobase.create()
    else:
        server.run()
    
def run_standalone():
    """Run OL in standalone mode.
    No separate infobase server is required.
    """
    infogami.config.db_parameters = web.config.db_parameters = config.db_parameters
    config.infobase_server = None
    web.load()

    from infogami.infobase import server
    server._infobase = get_infobase()
    
    if '--create' in sys.argv:
        server._infobase.create()
    else:
        infogami.run()

def run():
    import sys
    if '--server' in sys.argv:
        sys.argv.remove('--server')
        run_server()
    elif '--client' in sys.argv:
        sys.argv.remove('--client')
        run_client()
    else:
        run_standalone()

def setup_infogami_config():    
    infogami.config.site = 'openlibrary.org'
    infogami.config.admin_password = "admin123"
    infogami.config.login_cookie_name = "ol_session"

    infogami.config.plugin_path += ['plugins']
    infogami.config.plugins += ['openlibrary', 'i18n', 'api', 'sync', 'books', 'scod', 'search']

    infogami.config.infobase_parameters = dict(type='ol')

setup_infogami_config()