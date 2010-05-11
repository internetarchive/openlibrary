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

from openlibrary.api import OpenLibrary, marshal
from optparse import OptionParser

__version__ = "0.1"

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
    return parser.parse_args()

class Disk:
    def __init__(self, root):
        self.root = root

    def get_many(self, keys):
        return [{
                    "key": k, 
                    "type": {"key": "/type/template"}, 
                    "body": {
                        "type": "/type/text", 
                        "value": open(self.root + k.replace(".tmpl", ".html")).read()}}
                for k in keys]

    def save_many(self, docs, comment=None):
        def write(path, text):
            dir = os.path.dirname(path)
            if not os.path.exists(dir):
                os.makedirs(dir)

            try:
                print "writing", path
                f = open(path, "w")
                f.write(text)
                f.close()
            except IOError:
                print "failed", path

        for doc in marshal(docs):
            path = os.path.join(self.root, doc['key'][1:])
            write(path, simplejson.dumps(doc))
    
def main():
    options, args = parse_args()

    if options.src.startswith("http://"):
        src = OpenLibrary(options.src)
    else:
        src = Disk(options.src)

    if options.dest.startswith("http://"):
        dest = OpenLibrary(options.dest)
        dest.autologin()
    else:
        dest = Disk(options.dest)

    keys = args
    keys = list(expand(src, keys))
    docs = src.get_many(keys)
    print dest.save_many(docs, comment=options.comment)
    
if __name__ == '__main__':
    main()

