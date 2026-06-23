"""Various web.py application processors used in OL."""

import logging
import os
import re
import urllib
from urllib.parse import quote_plus

import web

from infogami import config
from infogami.utils.view import render
from openlibrary.core import helpers as h

logger = logging.getLogger("openlibrary.readableurls")

_AUTHOR_EXCLUSIONS: frozenset[str] | None = None


def _get_author_exclusions() -> frozenset[str]:
    """Returns the set of excluded author OLIDs from config.

    Reads ``author_exclusions`` from openlibrary.yml (a list of bare OLIDs
    such as ``["OL123A", "OL456A"]``).  Initialized once per process since
    config is static per-deploy; a restart is required to pick up changes.
    """
    global _AUTHOR_EXCLUSIONS
    if _AUTHOR_EXCLUSIONS is None:
        _AUTHOR_EXCLUSIONS = frozenset(config.get("author_exclusions") or [])
    return _AUTHOR_EXCLUSIONS


def is_exclusion(thing) -> bool:
    """Returns True if *thing* should be excluded from public view.

    A thing is excluded when it is an author whose OLID is in the
    ``author_exclusions`` config list, or when it is a book/work whose
    first resolvable author is in that list.
    """
    if not thing or not thing.key:
        return False
    try:
        _, _type, key = thing.key.split("/")
    except ValueError:
        return False
    exclusions = _get_author_exclusions()
    if _type == "authors":
        return key in exclusions
    elif _type in ("books", "works"):
        for a in thing.get("authors") or []:
            akey = getattr(a, "key", None) or getattr(getattr(a, "author", None), "key", None)
            if akey:
                return akey.split("/")[-1] in exclusions
    return False


class ReadableUrlProcessor:
    """Open Library code works with urls like /books/OL1M and
    /books/OL1M/edit. This processor seamlessly changes the urls to
    /books/OL1M/title and /books/OL1M/title/edit.

    The changequery function is also customized to support this.
    """

    patterns = (
        (r"/\w+/OL\d+M", "/type/edition", "title", "untitled"),
        (r"/\w+/ia:[a-zA-Z0-9_\.-]+", "/type/edition", "title", "untitled"),
        (r"/\w+/OL\d+A", "/type/author", "name", "noname"),
        (r"/\w+/OL\d+W", "/type/work", "title", "untitled"),
        (r"[/\w\-]*/lists/OL\d+L", "/type/list", "name", "unnamed"),
        (r"/series/OL\d+L", "/type/series", "name", "unnamed"),
        (r"/\w+/OL\d+T", "/type/tag", "name", "untitled"),
    )

    def __call__(self, handler):
        # temp hack to handle languages and users during upstream-to-www migration
        if web.ctx.path.startswith("/l/"):
            raise web.seeother("/languages/" + web.ctx.path[len("/l/") :])

        if web.ctx.path.startswith("/user/") and not web.ctx.site.get(web.ctx.path):
            raise web.seeother("/people/" + web.ctx.path[len("/user/") :])

        real_path, readable_path = get_readable_path(web.ctx.site, web.ctx.path, self.patterns, encoding=web.ctx.encoding)

        # @@ web.ctx.path is either quoted or unquoted depends on whether the application is running
        # @@ using builtin-server. That is probably a bug in web.py.
        # @@ take care of that case here till that is fixed.
        # @@ Also, the redirection must be done only for GET requests.
        if readable_path != web.ctx.path and readable_path != urllib.parse.quote(web.safestr(web.ctx.path)) and web.ctx.method == "GET":
            raise web.redirect(str(readable_path) + str(web.ctx.query))

        web.ctx.readable_path = readable_path
        web.ctx.path = real_path
        web.ctx.fullpath = web.ctx.path + web.ctx.query
        out = handler()

        # Exclude noindex items
        if web.ctx.get("exclude"):
            web.ctx.status = "404 Not Found"
            return render.notfound(web.ctx.path)

        return out


def _get_object(site, key):
    """Returns the object with the given key.

    If the key has an OLID and no object is found with that key, it tries to
    find object with the same OLID. OL database makes sures that OLIDs are
    unique.
    """
    obj = site.get(key)

    if obj is None and key.startswith("/a/"):
        key = "/authors/" + key[len("/a/") :]
        obj = key and site.get(key)

    if obj is None and key.startswith("/b/"):
        key = "/books/" + key[len("/b/") :]
        obj = key and site.get(key)

    if obj is None and key.startswith("/user/"):
        key = "/people/" + key[len("/user/") :]
        obj = key and site.get(key)

    basename = key.split("/")[-1]

    # redirect all /.*/ia:foo to /books/ia:foo
    if obj is None and basename.startswith("ia:"):
        key = "/books/" + basename
        obj = site.get(key)

    # redirect all /.*/OL123W to /works/OL123W
    if obj is None and basename.startswith("OL") and basename.endswith("W"):
        key = "/works/" + basename
        obj = site.get(key)

    # redirect all /.*/OL123M to /books/OL123M
    if obj is None and basename.startswith("OL") and basename.endswith("M"):
        key = "/books/" + basename
        obj = site.get(key)

    # redirect all /.*/OL123A to /authors/OL123A
    if obj is None and basename.startswith("OL") and basename.endswith("A"):
        key = "/authors/" + basename
        obj = site.get(key)

    # Disabled temporarily as the index is not ready the db

    # if obj is None and re.compile(r"/.*/OL\d+[A-Z]"):
    #    olid = web.safestr(key).split("/")[-1]
    #    key = site._request("/olid_to_key", data={"olid": olid}).key
    #    obj = key and site.get(key)
    return obj


def get_readable_path(site, path, patterns, encoding=None):
    """Returns real_path and readable_path from the given path.

    The patterns is a list of (path_regex, type, property_name, default_value)
    tuples.
    """

    def match(path):
        for pat, _type, _property, default_title in patterns:
            m = re.compile("^" + pat).match(path)
            if m:
                prefix = m.group()
                extra = path.removeprefix(prefix)
                tokens = extra.split("/", 2)

                # `extra` starts with "/". So first token is always empty.
                middle = web.listget(tokens, 1, "")
                suffix = web.listget(tokens, 2, "")
                if suffix:
                    suffix = "/" + suffix

                return _type, _property, default_title, prefix, middle, suffix
        return None, None, None, None, None, None

    _type, _property, default_title, prefix, middle, suffix = match(path)

    if _type is None:
        path = str(path)
        return (path, path)

    if encoding is not None or path.endswith((".json", ".rdf", ".yml")):
        key, ext = os.path.splitext(path)

        thing = _get_object(site, key)
        if thing:
            path = thing.key + ext
        path = str(path)
        return (path, path)

    thing = _get_object(site, prefix)

    # get_object may handle redirections.
    if thing:
        prefix = thing.key

    if thing and thing.type.key == _type:
        title = thing.get(_property) or default_title
        middle = "/" + quote_plus(h.urlsafe(title.strip()))
    else:
        middle = ""

    if is_exclusion(thing):
        web.ctx.exclude = True

    prefix = str(prefix)
    middle = str(middle)
    suffix = str(suffix)

    return (prefix + suffix, prefix + middle + suffix)
