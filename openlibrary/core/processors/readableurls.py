"""Various web.py application processors used in OL.
"""
import os
import urllib
import web

from openlibrary.core import helpers as h

class ReadableUrlProcessor:
    """Open Library code works with urls like /books/OL1M and
    /books/OL1M/edit. This processor seemlessly changes the urls to
    /books/OL1M/title and /books/OL1M/title/edit.
    
    The changequery function is also customized to support this.    
    """
    patterns = [
        (r'/\w+/OL\d+M', '/type/edition', 'title', 'untitled'),
        (r'/\w+/ia:[a-zA-Z0-9_\.-]+', '/type/edition', 'title', 'untitled'),
        (r'/\w+/OL\d+A', '/type/author', 'name', 'noname'),
        (r'/\w+/OL\d+W', '/type/work', 'title', 'untitled'),
        (r'/[/\w]+/OL\d+L', '/type/list', 'name', 'unnamed')
    ]
        
    def __call__(self, handler):
        # temp hack to handle languages and users during upstream-to-www migration
        if web.ctx.path.startswith("/l/"):
            raise web.seeother("/languages/" + web.ctx.path[len("/l/"):])
                
        if web.ctx.path.startswith("/user/"):
            if not web.ctx.site.get(web.ctx.path):
                raise web.seeother("/people/" + web.ctx.path[len("/user/"):])
        
        real_path, readable_path = get_readable_path(web.ctx.site, web.ctx.path, self.patterns, encoding=web.ctx.encoding)

        #@@ web.ctx.path is either quoted or unquoted depends on whether the application is running
        #@@ using builtin-server or lighttpd. Thats probably a bug in web.py. 
        #@@ take care of that case here till that is fixed.
        # @@ Also, the redirection must be done only for GET requests.
        if readable_path != web.ctx.path and readable_path != urllib.quote(web.utf8(web.ctx.path)) and web.ctx.method == "GET":
            raise web.redirect(web.safeunicode(readable_path) + web.safeunicode(web.ctx.query))

        web.ctx.readable_path = readable_path
        web.ctx.path = real_path
        web.ctx.fullpath = web.ctx.path + web.ctx.query
        return handler()

def _get_object(site, key):
    """Returns the object with the given key.
    
    If the key has an OLID and no object is found with that key, it tries to
    find object with the same OLID. OL database makes sures that OLIDs are
    unique.
    """    
    obj = site.get(key)

    if obj is None and key.startswith("/a/"):
        key = "/authors/" + key[len("/a/"):]
        obj = key and site.get(key)
        
    if obj is None and key.startswith("/b/"):
        key = "/books/" + key[len("/b/"):]
        obj = key and site.get(key)

    if obj is None and key.startswith("/user/"):
        key = "/people/" + key[len("/user/"):]
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
    
    #if obj is None and web.re_compile(r"/.*/OL\d+[A-Z]"):
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
        for pat, type, property, default_title in patterns:
            m = web.re_compile('^' + pat).match(path)
            if m:
                prefix = m.group()
                extra = web.lstrips(path, prefix)
                tokens = extra.split("/", 2)
                
                # `extra` starts with "/". So first token is always empty.
                middle = web.listget(tokens, 1, "")
                suffix = web.listget(tokens, 2, "")
                if suffix:
                    suffix = "/" + suffix
                
                return type, property, default_title, prefix, middle, suffix
        return None, None, None, None, None, None

    type, property, default_title, prefix, middle, suffix = match(path)
    if type is None:
        path = web.safeunicode(path)
        return (path, path)

    if encoding is not None \
       or path.endswith(".json") or path.endswith(".yml") or path.endswith(".rdf"):
        key, ext = os.path.splitext(path)
        
        thing = _get_object(site, key)
        if thing:
            path = thing.key + ext
        path = web.safeunicode(path)
        return (path, path)

    thing = _get_object(site, prefix)
    
    # get_object may handle redirections.
    if thing:
        prefix = thing.key

    if thing and thing.type.key == type:
        title = thing.get(property) or default_title
        middle = '/' + h.urlsafe(title.strip())
    else:
        middle = ""
    
    prefix = web.safeunicode(prefix)
    middle = web.safeunicode(middle)
    suffix = web.safeunicode(suffix)
    
    return (prefix + suffix, prefix + middle + suffix)
