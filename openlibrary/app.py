"""Utilities to build the app.
"""
import simplejson

from infogami.infobase.client import Thing
from infogami.utils import app as _app
from infogami.utils.view import render, public
from infogami.utils.macro import macro
import uuid

from openlibrary.core.cache import MemcacheCache


class view(_app.page):
    """A view is a class that defines how a page or a set of pages
    identified by a regular expression are rendered.

    Here is a sample view::

        from openlibrary import app

        class hello(app.view):
            path = "/hello/(.*)"

            def GET(self, name):
                return app.render_template("hello", name)
    """
    # In infogami, the class with this functionality is called page.
    # We are redefining with a slightly different terminology to make
    # things more readable.
    pass

# view is just a base class.
# Defining a class extending from _app.page auto-registers it inside infogami.
# Undoing that.
del _app.pages['/view']

class subview(_app.view):
    """Subviews are views that work an object in the database.

    Each subview URL will have two parts, the prefix identifying the key
    of the document in the database to work on and the suffix iden identifying
    the action.

    For example, the in the subview with URL "/works/OL123W/foo/identifiers",
    "identifiers" is the action and "/works/OL123W" is the key of the document.
    The middle part "foo" is added by a middleware to make the URLs readable
    and not that is transparent to this.

    Here is a sample subview:

        class work_identifiers(delegate.view):
            suffix = "identifiers"
            types = ["/type/edition"]
    """
    # In infogami, the class with this functionality is called a view.
    # We are redefining with a slightly different terminology to make
    # things more readable.

    # Tell infogami not to consider this as a view class
    suffix = None
    types = None

@macro
@public
def render_template(name, *a, **kw):
    if "." in name:
        name = name.rsplit(".", 1)[0]
    return render[name](*a, **kw)


mc_cache = MemcacheCache()

@macro
@public
def render_macro_lazy(name, *args, **kw):
    if "." in name:
        name = name.rsplit(".", 1)[0]

    args = [
        {'thing_key': a.key} if isinstance(a, Thing) else a
        for a in args
    ]
    data = {
        'name': name,
        'args': args,
        'kwargs': kw,
    }
    guid = str(uuid.uuid4())
    key = "render_macro_lazy_" + guid
    mc_cache.set(key, simplejson.dumps(data), expires=20)
    return render['lazy_template'](key)


@macro
@public
def render_template_lazy(name, *args, **kw):
    if "." in name:
        name = name.rsplit(".", 1)[0]

    args = [
        {'thing_key': a.key} if isinstance(a, Thing) else a
        for a in args
    ]
    data = {
        'name': name,
        'args': args,
        'kwargs': kw,
    }
    guid = str(uuid.uuid4())
    key = "render_template_lazy_" + guid
    mc_cache.set(key, simplejson.dumps(data), expires=20)
    return render['lazy_template'](key)