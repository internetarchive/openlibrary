"""Main entry point for openlibrary app.

Loaded from Infogami plugin mechanism.
"""
from infogami.utils import template, macro, i18n

old_plugins = ["openlibrary", "search", "worksearch", "books", "admin", "upstream", "importapi"]

def setup():
    for p in old_plugins:
        modname = "openlibrary.plugins.%s.code" % p
        print "loading", p, modname
        path = "openlibrary/plugins/" + p
        template.load_templates(path, lazy=True)
        macro.load_macros(path, lazy=True)
        i18n.load_strings(path)
        __import__(modname, globals(), locals(), ['plugins'])

setup()
