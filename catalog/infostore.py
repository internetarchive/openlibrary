from infogami.infobase import cache
import infogami, sys, web
from read_rc import read_rc

def get_infobase(rc):
    from infogami.infobase import infobase, dbstore
    import web
    web.config.db_parameters = infogami.config.db_parameters
    web.config.db_printing = False
    web.load()

    schema = dbstore.Schema()
    schema.add_table_group('type', '/type/type')
    schema.add_table_group('type', '/type/property')
    schema.add_table_group('type', '/type/backreference')
    schema.add_table_group('user', '/type/user')
    schema.add_table_group('user', '/type/usergroup')
    schema.add_table_group('user', '/type/permission')

    schema.add_table_group('edition', '/type/edition')
    schema.add_table_group('author', '/type/author')
    schema.add_table_group('scan', '/type/scan_location')
    schema.add_table_group('scan', '/type/scan_record')

    schema.add_seq('/type/edition', '/b/OL%dM')
    schema.add_seq('/type/author', '/a/OL%dA')

    store = dbstore.DBStore(schema)
    secret_key = rc['secret_key']
    return infobase.Infobase(store, secret_key)

def get_site():
    if 'site' in web.ctx:
        return web.ctx.site
    rc = read_rc()

    infogami.config.db_parameters = dict(dbn='postgres', db=rc['db'], user=rc['user'], pw=rc['pw'], host=rc['host'])
    infogami.config.db_printing = False

    ib = get_infobase(rc)
    web.ctx.site = ib.get('openlibrary.org')
    cache.loadhook()
    return web.ctx.site
