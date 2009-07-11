import os
import web
import py.test

from openlibrary.coverstore import config, schema

def get_static_dir():
    from os.path import abspath, join, dirname, pardir
    return abspath(join(dirname(__file__), pardir, pardir, pardir, 'static'))
    
def setup_dirs(root):
    config.data_root = root.strpath

    # make sure everything is deleted
    root.remove(rec=True)
    os.mkdir(root.strpath)

    # create dirs for localdisk and items
    os.mkdir(root.join('items').strpath)
    os.mkdir(root.join('localdisk').strpath)
    
def setup_db(root):
    dbfile = root.join('coverstore.db').strpath
    
    config.db_parameters = dict(dbn='sqlite', db=dbfile)

    # get schema for sqlite
    db_schema = schema.get_schema('sqlite')
    
    # create tables.
    # XXX: sqlite doesn't allow executing more than one query at a time. 
    # split the schema by ; to get individual queries and run them in a transaction
    db = web.database(**config.db_parameters)
    t = db.transaction()
    for q in db_schema.split(';'):
        db.query(q)
    db.insert('category', name='b')
    t.commit()

def setup_module(mod, db=False):
    mod.static_dir = get_static_dir()
    
    mod.root = py.test.config.ensuretemp('coverstore')
    setup_dirs(mod.root)
    
    if db:
        setup_db(mod.root)
    
def teardown_module(mod):
    mod.root.remove(rec=True)
