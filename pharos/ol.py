#!/usr/bin/env python
import sys

import schema

import infogami
from infogami.infobase import client
import web

config = web.storage(
    db_parameters = None,
    infobase_server = None,
    writelog = None,
    booklog = None,
    errorlog = None,
    memcache_servers = None,
)


def get_infobase():
    """Creates infobase object."""
    from infogami.infobase import infobase, dbstore, cache
    params = infogami.config.infobase_parameters.copy()
    assert params.pop('type') == 'local'
    web.config.db_parameters = params
    infogami.config.db_parameters = params
    web.config.db_printing = True
    web.load()

    # hack to make cache work for local infobase connections
    cache.loadhook()
    web.ctx.ip = '127.0.0.1'

    store = dbstore.DBStore(schema.get_schema())
    return infobase.Infobase(store, infobase.config.secret_key)

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
    infogami.config.infobase_parameters = dict(type='remote', base_url=config.infobase_server)
    infogami.run()
    
def run_server():
    """Run Infobase server."""
    infogami.config.infobase_parameters = dict(type='local', **config.db_parameters)
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
    infogami.config.infobase_parameters = dict(type='local', **config.db_parameters)
    web.config.db_parameters = config.db_parameters
    web.load()

    from infogami.infobase import server
    server._infobase = get_infobase()
    
    if '--create' in sys.argv:
        server._infobase.create()
    else:
        infogami.run()
        
run = run_standalone
    
infogami.config.site = 'openlibrary.org'
infogami.config.admin_password = "admin123"
infogami.config.login_cookie_name = "ol_session"

infogami.config.plugin_path += ['plugins']
infogami.config.plugins += ['openlibrary', 'i18n', 'api', 'sync', 'books', 'scod', 'search']
