#! /usr/bin/env python
"""Script to copy docs from one OL instance to another. 
Typically used to copy templates, macros, css and js from 
openlibrary.org to dev instance.

USAGE: 
    ./scripts/copydocs.py --src http://openlibrary.org --dest http://0.0.0.0:8080 /templates/*

This script can also be used to copy books and authors from OL to dev instance. 

    ./scripts/copydocs.py /authors/OL113592A 
    ./scripts/copydocs.py /works/OL1098727W
"""

import _init_path
import sys
import os
import simplejson
import web

from openlibrary.api import OpenLibrary, marshal, unmarshal
from optparse import OptionParser

__version__ = "0.2"

def find(server, prefix):
    q = {'key~': prefix, 'limit': 1000}
    
    # until all properties and backreferences are deleted on production server
    if prefix == '/type':
        q['type'] = '/type/type'
    
    return [unicode(x) for x in server.query(q)]
    
def expand(server, keys):
    if isinstance(server, Disk):
        for k in keys:
            yield k
    else:
        for key in keys:
            if key.endswith('*'):
                for k in find(server, key):
                    yield k
            else:
                yield key


desc = """Script to copy docs from one OL instance to another.
Typically used to copy templates, macros, css and js from
openlibrary.org to dev instance. paths can end with wildcards.
"""
def parse_args():
    parser = OptionParser("usage: %s [options] path1 path2" % sys.argv[0], description=desc, version=__version__)
    parser.add_option("-c", "--comment", dest="comment", default="", help="comment")
    parser.add_option("--src", dest="src", metavar="SOURCE_URL", default="http://openlibrary.org/", help="URL of the source server (default: %default)")
    parser.add_option("--dest", dest="dest", metavar="DEST_URL", default="http://0.0.0.0:8080/", help="URL of the destination server (default: %default)")
    parser.add_option("-r", "--recursive", dest="recursive", action='store_true', default=False, help="Recursively fetch all the referred docs.")
    return parser.parse_args()

class Disk:
    def __init__(self, root):
        self.root = root

    def get_many(self, keys):
        def f(k):
            return {
                "key": k, 
                "type": {"key": "/type/template"}, 
                "body": {
                    "type": "/type/text", 
                    "value": open(self.root + k.replace(".tmpl", ".html")).read()
                }
            }
        return dict((k, f(k)) for k in keys)

    def save_many(self, docs, comment=None):
        def write(path, text):
            dir = os.path.dirname(path)
            if not os.path.exists(dir):
                os.makedirs(dir)

            if isinstance(text, dict):
                text = text['value']

            try:
                print "writing", path
                f = open(path, "w")
                f.write(text)
                f.close()
            except IOError:
                print "failed", path

        for doc in marshal(docs):
            path = os.path.join(self.root, doc['key'][1:])
            if doc['type']['key'] == '/type/template':
                path = path.replace(".tmpl", ".html")
                write(path, doc['body'])
            elif doc['type']['key'] == '/type/macro':
                path = path + ".html"
                write(path, doc['macro'])
                
def read_lines(filename):
    try:
        return [line.strip() for line in open(filename)]
    except IOError:
        return []
        
def get_references(doc, result=None):
    if result is None:
        result = []

    if isinstance(doc, list):
        for v in doc:
            get_references(v, result)
    elif isinstance(doc, dict):
        if 'key' in doc and len(doc) == 1:
            result.append(doc['key'])

        for k, v in doc.items():
            get_references(v, result)
    return result
    
def copy(src, dest, keys, comment, recursive=False, saved=None, cache=None):
    if saved is None:
        saved = set()
    if cache is None:
        cache = {}
        
    def fetch(keys):
        docs = []
        
        for k in keys:
            if k in cache:
                docs.append(cache[k])
                
        keys = [k for k in keys if k not in cache]
        if keys:
            print "fetching", keys
            docs2 = marshal(src.get_many(keys).values())
            cache.update((doc['key'], doc) for doc in docs2)
            docs.extend(docs2)
        return docs
        
    keys = [k for k in keys if k not in saved]
    docs = fetch(keys)
    
    if recursive:
        refs = get_references(docs)
        refs = [r for r in list(set(refs)) if not r.startswith("/type/")]
        if refs:
            print "found references", refs
            copy(src, dest, refs, comment, recursive=True, saved=saved, cache=cache)
    
    docs = [doc for doc in docs if doc['key'] not in saved]
    
    keys = [doc['key'] for doc in docs]
    print "saving", keys
    print dest.save_many(docs, comment=comment)
    saved.update(keys)
            
def main():
    options, args = parse_args()

    if options.src.startswith("http://"):
        src = OpenLibrary(options.src)
    else:
        src = Disk(options.src)

    if options.dest.startswith("http://"):
        dest = OpenLibrary(options.dest)
        section = "[%s]" % web.lstrips(options.dest, "http://").strip("/")
        if section in read_lines(os.path.expanduser("~/.olrc")):
            dest.autologin()
        else:
            dest.login("admin", "admin123")
    else:
        dest = Disk(options.dest)

    keys = args
    keys = list(expand(src, keys))
    
    copy(src, dest, keys, comment=options.comment, recursive=options.recursive)
    
if __name__ == '__main__':
    main()

