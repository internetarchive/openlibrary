"""Reindex work_ref table.

USAGE: python reindex.py dbname work_keys.txt

TODO: generalize this to work with any table.
"""
import web
import simplejson
import os

def read_keys(keysfile):
    """Returns all keys in the keys file."""
    for line in open(keysfile):
        yield line.strip()
        
def get_docs(keys):
    """Returns docs for the specified keys."""
    for key in keys:
        result = db.query("SELECT thing.id, data.data FROM data, thing WHERE data.thing_id=thing.id AND data.revision=thing.latest_revision and thing.key=$key", vars=locals())
        d = result[0]
        doc = simplejson.loads(d.data)
        d['id'] = d.id
        yield doc

def read_refs(thing_id):
    rows = db.query("SELECT * FROM work_ref WHERE thing_id=$thing_id", vars=locals())
    for r in rows:
        name = get_property_name(r.key_id)
        value = r.value
        yield name, value

def get_thing_id(key):
    return db.query("SELECT id FROM thing WHERE key=$key", vars=locals())[0].id

@web.memoize
def get_property_id(type, name):
    type_id = get_thing_id(type)
    return db.query("SELECT id FROM property WHERE type=$type_id AND name=$name", vars=locals())[0].id
    
@web.memoize
def get_property_name(key_id):
    return db.query("SELECT name FROM property WHERE id=$key_id", vars=locals())[0].name

def flat_items(d):
    """
        >>> flat_items({"a": {"b": "c"}, "x": [1, 2]})
        [('a.b', 'c'), ('x', 1), ('x', 2)]
    """
    items = []
    sep = "."
    
    def process(key, value):
        if isinstance(value, dict):
            for k, v in value.items():
                process(key + sep + k, v)
        elif isinstance(value, list):
            for v in value:
                process(key, v)
        else:
            items.append((key, value))
    
    for k, v in d.items():
        process(k, v)
    return items
    
def find_references(doc):
    """Find the references to be indexed from the given doc.
    
        >>> refs = find_references({"title": "foo", "authors": [{"key": "/a/OL1A"}]})
        >>> list(refs)
        [('authors', '/a/OL1A')]
    """
    for k, v in flat_items(doc):
        if k.endswith(".key") and not k.endswith("type.key") and not k.startswith("excerpts."):
            yield k[:-len(".key")], v

def make_index(docs):
    for doc in docs:
        doc["_refs"] = [(name, get_thing_id(value)) for name, value in find_references(doc)]
        yield doc

def filter_index(docs):
    for doc in docs:
        refs = list(read_refs(doc["id"]))
        #print refs, doc['_refs']
        if refs != doc["_refs"]:
            yield doc
    
def write_index(docs):
    for chunk in web.group(docs, 1000):
        chunk = list(chunk)
        
        thing_ids = [doc['id'] for doc in chunk]
        
        t = db.transaction()
        db.query("DELETE FROM work_ref WHERE thing_id IN $thing_ids", vars=locals())
        
        data = []
        for doc in chunk:
            thing_id = doc['id']
            type = doc['type']['key']
            if type == "/type/work":
                for name, value in doc['_refs']:
                    key_id = get_property_id(type, name)
                    data.append(dict(thing_id=thing_id, key_id=key_id, value=value))
        
        if data:
            db.multiple_insert("work_ref", data, seqname=False)
        
        t.commit()

def reindex(keys):
    pass
    
def pipe(*funcs):
    def g(arg):
        for f in funcs:
            arg = f(arg)
        return arg
    return g
    
def display(data):
    for row in data:
        print row
    
def main(dbname, keysfile):
    global db
    db = web.database(dbn="postgres", db=dbname, user=os.getenv("USER"), pw="")
    
    f = pipe(read_keys, get_docs, make_index, filter_index, write_index)
    f(keysfile)
    
if __name__ == "__main__":
    import sys
    main(sys.argv[1], sys.argv[2])
