#! /usr/bin/env python
"""Fetch a document and its references recursively upto specified depth from Open Library website.

USAGE: 
    
    Fetch an author and it's references upto depth 3
    
    $ python fetch.py /authors/OL23919A

    Load all the fetched documents into local instance

    $ python fetch.py --load

"""
import _init_path
import urllib
import simplejson
import os

MAX_LEVEL = 3

def get(key):
    path = "data" + key
    if os.path.exists(path):
        json = open(path).read()
    else:
        json = urllib.urlopen("http://openlibrary.org%s.json" % key).read()
    return simplejson.loads(json)

def query(**kw):
    json = urllib.urlopen("http://openlibrary.org/query.json?" + urllib.urlencode(kw)).read()
    return simplejson.loads(json)

def get_backreferences(key, limit=5):
    if key.startswith("/works"):
        return [d['key'] for d in query(type="/type/edition", works=key, limit=limit)]
    if key.startswith("/authors"):
        return [d['key'] for d in query(type="/type/edition", authors=key, limit=limit)]
    else:
        return []

def get_references(doc, result=None):
    if result is None:
        result = []

    if isinstance(doc, list):
        for v in doc:
            get_references(v, result)
    elif isinstance(doc, dict):
        if 'key' in doc:
            result.append(doc['key'])

        for k, v in doc.items():
            get_references(v, result)
    return result

def fetch(key, depth, limit):
    _fetch(key, maxlevel=depth, limit=limit)

def _fetch(key, visited=None, level=0, maxlevel=0, limit=5):
    """Fetch documents using depth-first traversal"""
    if visited is None:
        visited = set()

    if key in visited:
        return

    prefix = ("|  " * level) + "|--"
    print prefix, key

    doc = get(key)
    write(key, doc)
    visited.add(key)

    refs = get_references(doc)

    if level < maxlevel:
        refs += get_backreferences(key, limit=limit)

    for k in refs:
        if k not in visited and not k.startswith("/type/"):
            _fetch(k, visited, level=level+1, maxlevel=maxlevel, limit=limit)

def makedirs(dir):
    if not os.path.exists(dir):
        os.makedirs(dir)

def write(key, doc):
    path = "data" + key
    makedirs(os.path.dirname(path))

    f = open(path, "w")
    f.write(simplejson.dumps(doc))
    f.close()

def main(key, level=0, limit=100):
    fetch(key, int(level), int(limit))

def topological_sort(nodes, get_children):
    def visit(n):
        if n not in visited:
            visited.add(n)
            for c in get_children(n):
                visit(c)
            result.append(n)

    result = []
    visited = set()
    for n in nodes:
        visit(n)
    return result

def find(path):
    for dirname, dirnames, filenames in os.walk(path):
        for f in filenames:
            yield os.path.join(dirname, f)

def load():
    """Loads documents to http://0.0.0.0:8080"""
    documents = {}
    for f in find("data"):
        doc = simplejson.load(open(f))
        documents[doc['key']] = doc

    keys = topological_sort(documents.keys(), 
            get_children=lambda key: [k for k in get_references(documents[key]) if not k.startswith("/type/")])

    from openlibrary.api import OpenLibrary
    ol = OpenLibrary("http://0.0.0.0:8080")
    ol.autologin()
    print ol.save_many([documents[k] for k in keys], comment="documents copied from openlibrary.org")
    
if __name__ == "__main__":
    import sys
    if '--load' in sys.argv:
        load()
    else:
        main(*sys.argv[1:])
