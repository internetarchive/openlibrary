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
    
def setup_db(mod, root):
    os.system('dropdb coverstore_test; createdb coverstore_test;')
    user = os.getenv('USER')
    config.db_parameters = dict(dbn='postgres', db="coverstore_test", user=user, pw='')
    db_schema = schema.get_schema('postgres')
    db = web.database(**config.db_parameters)
    db.query(db_schema)
    db.insert('category', name='b')    
    mod.db = db
    
def setup_module(mod, db=False):
    mod.static_dir = get_static_dir()
    
    mod.root = py.test.config.ensuretemp('coverstore')
    setup_dirs(mod.root)
    
    if db:
        setup_db(mod, mod.root)
    
def teardown_module(mod):
    mod.root.remove(rec=True)
    if 'db' in mod.__dict__:
        mod.db.ctx.db.close()
        del mod.db
