"""Script to print documentation about all public functions available to templates.

USAGE:
    Get all docs:
        $ ./scripts/openlibary conf/openlibrary.yml runscript scripts/2011/08/oldoc.py
    
    Get docs for one single function:
        $ ./scripts/openlibary conf/openlibrary.yml runscript scripts/2011/08/oldoc.py datestr

"""
import web
import pydoc
import sys
import re

functions = web.template.Template.globals

args = sys.argv[1:]

if args:
    functions = dict((name, value) for (name, value) in functions.items() if name in args)

for name, f in sorted(functions.items()):
    if hasattr(f, "__call__"):
        try:
            doc = pydoc.text.document(f, name)
            # Remove special chars to print text as bold on the terminal
            print re.sub("\x08.", "", doc)
        except Exception:
            # ignore errors
            pass
