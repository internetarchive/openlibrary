#! /usr/bin/env python
"""Script to fix redirects in OL database.

In OL database the redirects are still using the old keys. This script fixes them all.
    
USAGE:

    python fix_redirects.py openlibrary.yml infobase.yml
"""

import sys
import simplejson
import yaml
import memcache

import _init_path
from infogami.infobase.server import parse_db_parameters
from openlibrary.data import db

def read_config(filename):
    return yaml.safe_load(open(filename).read())
    
def setup_mc(ol_config_file):
    config = read_config(ol_config_file)
    servers = config.get("memcache_servers")
    return memcache.Client(servers)

def setup_db(infobase_config_file):
    config = read_config(infobase_config_file)
    db_parameters = parse_db_parameters(config['db_parameters'])
    db.setup_database(**db_parameters)
    
def get_type_redirect():
    return db.db.query("SELECT id FROM thing WHERE key='/type/redirect'")[0].id
    
def longquery(query, vars, callback):
    for chunk in db.longquery(query, vars=vars):
        t = db.db.transaction()
        try:
            db.db.query("CREATE TEMP TABLE data_redirects (thing_id int, revision int, data text, UNIQUE(thing_id, revision))")
        except:
            t.rollback()
            raise
        else:
            t.commit()
            
def fix_doc(doc):
    if 'location' in doc and (doc['location'].startswith("/a/") or doc['location'].startswith("/b/")):
        doc['location'] = doc['location'].replace('/a/', '/authors/').replace('/b/', '/books/')
    return doc

def fix_json(json):
    doc = simplejson.loads(json)
    doc = fix_doc(doc)
    return simplejson.dumps(doc)
            
def fix_redirects(rows):
    rows = [dict(thing_id=r.thing_id, revision=r.revision, data=fix_json(r.data)) for r in rows]
    
    db.db.query("CREATE TEMP TABLE data_redirects (thing_id int, revision int, data text, UNIQUE(thing_id, revision))")
    db.db.multiple_insert('data_redirects', rows)

def main(ol_config_file, infobase_config_file):
    setup_mc(ol_config_file)
    setup_db(infobase_config_file)
    
    type_redirect = get_type_redirect()
    
    query = "SELECT data.* FROM thing, data WHERE thing.type=$type_redirect AND thing.id=data.thing_id"
    longquery(query, vars=locals(), callback=fix_redirects)
    
def test_fix_doc():
    assert fix_doc({}) == {}
    assert fix_doc({'location': '/a/foo'}) == {'location': '/authors/foo'}
    assert fix_doc({'location': '/b/foo'}) == {'location': '/books/foo'}
    assert fix_doc({'location': '/c/foo'}) == {'location': '/c/foo'}

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])