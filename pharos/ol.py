#!/usr/bin/env python
import sys
import os
import datetime
import urllib
import simplejson

import infogami
from infogami.infobase import client, lru, common
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
    cache_prefixes = ['/type/', '/l/', '/index.', '/about', '/css/', '/js/'], # objects with key starting with these prefixes will be cached locally.
    http_listeners=[],
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

    if ol and config.http_listeners:
        ol.add_trigger(None, http_notify)

    return ib
    
def get_object_data(site, thing):
    """Return expanded data of specified object."""
    def expand(value):
        if isinstance(value, list):
            return [expand(v) for v in value]
        elif isinstance(value, common.Reference):
            t = site.get(value)
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
        query = {'type': '/type/edition', 'authors': new.key, 'limit': 1000}
        for d in site.things(query):
            book = site.get(d['key'])
            booklogger.write('book', sitename, new.last_modified, get_object_data(site, book))

def http_notify(site, old, new):
    """Notify listeners over http."""
    data = simplejson.dumps(new.format_data())
    for url in config.http_listeners:
        try:
            urllib.urlopen(url, data)
        except:
            print >> web.debug, "failed to send http_notify", url, new.key
            import traceback
            traceback.print_exc()

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
    infogami.config.http_ext_header_uri = "http://openlibrary.org/dev/docs/api"

setup_infogami_config()
