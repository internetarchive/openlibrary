"""
utility to create and upgrade infogami database.
"""

import web
import glob

modules = []

class module:
    def __init__(self, name, schema):
        self.name = name
        self.schema = schema
        self.upgrades = []
        modules.append(self)

        if schema is not None:
            self.upgrade(self.setup)

    def get_version(self):
        try:
            name = self.name
            return web.query("SELECT * from metadata where name=$name", vars=locals())[0].version
        except:
            return 0

    def upgrade(self, f):
        self.upgrades.append(f)
        return f

    def setup(self):
        """initial setup."""
        tables = [t for t in self.schema.split(';') if t.strip() != '']
        for t in tables:
            web.query(t)

    def apply_upgrades(self):
        version = self.get_version()
        for f in self.upgrades[version:]:
            print 'applying upgrade: %s.%s (%s)' % (self.name, f.__name__, f.__doc__)
            f()

        name = self.name
        if version == 0:
            web.insert("metadata", name=name, version=len(self.upgrades))
        else:
            web.update("metadata", where="name=$name", version=len(self.upgrades), vars=locals())

schema = """
CREATE TABLE metadata (
    id serial primary key, 
    name text unique,
    version int
);
"""

upgrade = module("system", schema).upgrade

def _load():
    web.load()
    from infogami.core import schema
    for f in glob.glob('infogami/plugins/*/schema.py'):
        module = f.replace('/', '.')[:-3]
        __import__(module, globals(), locals(), ['plugins'])

def apply_upgrades():
    _load()
    try:
        web.transact()
        for m in modules:
            print 'applying upgrades for', m.name
            m.apply_upgrades()
    except:
        web.rollback()
        print 'upgrade failed.'
        raise
    else:
        web.commit()
        print 'upgrade successful.'
