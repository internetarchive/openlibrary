#!/usr/bin/env python
import sys
import os
import datetime

import infogami
from infogami.infobase import client, lru
from infogami.infobase.logger import Logger
import web

import schema

if not hasattr(web, 'load'):
    web.load = lambda: None

config = web.storage(
    db_parameters = None,
    infobase_server = None,
    writelog = 'log',
    booklog = 'booklog',
    errorlog = 'errors',
    memcache_servers = None,
    cache_prefixes = ['/type/', '/l/', '/index.', '/about'], # objects with key starting with these prefixes will be cached locally.
)

def write(path, data):
    dir = os.path.dirname(path)
    if not os.path.exists(dir):
        os.makedirs(dir)
    f = open(path, 'w')
    f.write(data)
    f.close()
    
def save_error(dir, prefix):
    try:
        import traceback
        traceback.print_exc()

        error = web.djangoerror()
        now = datetime.datetime.utcnow()
        path = '%s/%d-%d-%d/%s-%d%d%d.%d.html' % (dir, \
            now.year, now.month, now.day, prefix,
            now.hour, now.minute, now.second, now.microsecond)
        print >> web.debug, 'Error saved to', path
        write(path, web.safestr(error))
    except:
        import traceback
        traceback.print_exc()
    
infogami.infobase.common.record_exception = lambda: save_error(config.errorlog, 'infobase')

class ConnectionProcessor:
    """Wrapper over Infobase connection to add additional functionality."""
    def request(self, super, sitename, path, method, data):
        if path == '/get':
            return self.get(super, sitename, data)
        elif path == '/write':
            return self.write(super, sitename, data)
        elif path == '/save':
            return self.save(super, sitename, data)
        elif path == '/save_many':
            return self.save_many(super, sitename, data)
        else:
            return super.request(sitename, path, method, data)
            
    def get(self, super, sitename, data):
        return super.get(sitename, data)
        
    def write(self, super, sitename, data):
        return super.write(sitename, data)

    def save(self, super, sitename, data):
        return super.save(sitename, data)

    def save_many(self, super, sitename, data):
        return super.save_many(sitename, data)
        
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
                # update cache only on success
                if '"status": "ok"' in response:
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
            keys = [k for k in modified if self.cachable(k)]
            self.cache.delete_many(keys)

        return response_str

    def save(self, super, sitename, data):
        import simplejson
        response_str = super.save(sitename, data)
        response = simplejson.loads(response_str)
        if response['status'] == 'ok':
            result = response['result']
            if result:
                self.cache.delete(result['key'])

        return response_str

    def save_many(self, super, sitename, data):
        import simplejson
        response_str = super.save_many(sitename, data)
        response = simplejson.loads(response_str)
        if response['status'] == 'ok':
            result = response['result']
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

            def save(self, sitename, data):
                return conn.request(sitename, '/save', 'POST', data=data)

            def save_many(self, sitename, data):
                return conn.request(sitename, '/save_many', 'POST', data=data)
                
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

    def get_auth_token(self):
        return self.conn.get_auth_token()

    def set_auth_token(self, token):
        self.conn.set_auth_token(token)
        
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

    if config.writelog:
        ib.add_event_listener(Logger(config.writelog))

    ol = ib.get('openlibrary.org')
    if ol and config.booklog:
        global booklogger
        booklogger = Logger(config.booklog)
        ol.add_trigger('/type/edition', write_booklog)
        ol.add_trigger('/type/author', write_booklog2)

    return ib
    
def get_object_data(site, thing):
    """Return expanded data of specified object."""
    def expand(value):
        if isinstance(value, list):
            return [expand(v) for v in value]
        elif isinstance(value, dict) and 'key' in value:
            t = site.get(value['key'])
            return t and t._get_data()
        else:
            return value

    d = thing._get_data()
    for k, v in d.iteritems():
        # save some space by not expanding type
        if k != 'type':
            d[k] = expand(v)
    return d

booklogger = None

def write_booklog(site, old, new):
    """Log modifications to book records."""
    sitename = site.sitename
    if new.type.key == '/type/edition':
        booklogger.write('book', sitename, new.last_modified, get_object_data(site, new))
    else:
        booklogger.write('delete', sitename, new.last_modified, {'key': new.key})
        
def write_booklog2(site, old, new):
    """This function is called when any author object is changed.
    to log all books of the author if name is changed.
    """
    sitename = site.sitename
    if old and old.type.key == new.type.key == '/type/author' and old.name != new.name:
        query = {'type': '/type/edition', 'authors': new.key}
        for key in site.things(query):
            book = site.get(key)
            booklogger.write('book', sitename, new.last_modified, get_object_data(site, book))
            
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
        server._infobase.create('openlibrary.org')
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
        server._infobase.create('openlibrary.org')
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
