#! /usr/bin/env python
"""Script to pull templates and macros from an openlibrary instance to repository.
"""
import _init_path

import os
import web
from optparse import OptionParser

from openlibrary.api import OpenLibrary, marshal

def parse_options(args=None):
    parser = OptionParser(args)
    parser.add_option("-s", "--server", dest="server", default="http://openlibrary.org/", help="URL of the openlibrary website (default: %default)")
    parser.add_option("--template-root", dest="template_root", default="/", help="Template root (default: %default)")
    parser.add_option("--default-plugin", dest="default_plugin", default="upstream", help="Default plugin (default: %default)")

    options, args = parser.parse_args()

    options.template_root = options.template_root.rstrip("/")    
    return options, args

def write(path, text):
    print "saving", path
    
    dir = os.path.dirname(path)
    if not os.path.exists(dir):
        os.makedirs(dir)
        
    f = open(path, "w")
    f.write(text)
    f.close()

def delete(path):
    print "deleting", path
    if os.path.exists(path):
        os.remove(path)

def make_path(doc):
    key = doc['key'].rsplit(".")[0]
    key = web.lstrips(key, options.template_root)
    
    plugin = doc.get("plugin", options.default_plugin)
    return "openlibrary/plugins/%s%s.html" % (plugin, key)

def get_value(doc, property):
    value = doc.get(property, "")
    if isinstance(value, dict) and "value" in value:
        return value['value']
    else:
        return value

def main():
    global options
    options, args = parse_options()
    ol = OpenLibrary(options.server)

    for pattern in args:
        docs = ol.query({"key~": pattern, "*": None}, limit=1000)
        for doc in marshal(docs):
            if doc['type']['key'] == '/type/template':
                write(make_path(doc), get_value(doc, 'body'))
            elif doc['type']['key'] == '/type/template':
                write(make_path(doc), get_value(doc, 'macro'))
            else:
                delete(make_path(doc))

if __name__ == "__main__":
    main()
