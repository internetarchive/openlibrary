"""
Open Library Plugin.
"""

from infogami.utils import types

types.register_type('^/a/[^/]*$', '/type/author')
types.register_type('^/b/[^/]*$', '/type/edition')
