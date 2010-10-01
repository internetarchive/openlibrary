#! /usr/bin/env python
"""Script to manage lists.

Usage: ./scripts/manage-lists.py command settings.yml args

Available commands:

index-editions  takes a list of edition keys and indexes them in the list db.
help            prints this help message.
"""
import _init_path
import sys

from openlibrary.core import lists, formats

def index_editions(settings_filename, *keys):
    settings = formats.load_yaml(open(settings_filename).read())
    engine = lists.ListsEngine(settings)
    engine.index_editions(keys)

def main(cmd=None, *args):
    if cmd == "index-editions":
        index_editions(*args)
    elif cmd is None or cmd == "help" or cmd == "--help":
        print __doc__
    else:
        print >> sys.stderr, "Unknown command %r. see '%s --help'." % (cmd, sys.argv[0])
        
if __name__ == "__main__":
    main(*sys.argv[1:])
    
