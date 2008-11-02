#!/usr/bin/env python

import schema
import infogami
import web

def get_infobase():
    from infogami.infobase import infobase, dbstore, cache
    params = infogami.config.infobase_parameters.copy()
    params.pop('type') == 'local'
    web.config.db_parameters = params
    infogami.config.db_parameters = params
    web.config.db_printing = True
    web.load()

    print >> web.debug, web.config.db_parameters

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
