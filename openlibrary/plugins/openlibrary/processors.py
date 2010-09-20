"""web.py application processors for Open Library.
"""
import web
import urllib
import re
import os

class ReadableUrlProcessor:
    """Open Library code works with urls like /b/OL1M and /b/OL1M/cover.
    This processor seemlessly changes the urls to /b/OL1M/title and /b/OL1M/title/cover.
    
    The changequery function is also customized to support this.    
    """
    
    patterns = [
        (r'/\w+/OL\d+M', '/type/edition', 'title', 'untitled'),
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
        
        real_path, readable_path = self.get_readable_path(web.ctx.path, encoding=web.ctx.encoding)

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

    def get_object(self, key):
        obj = web.ctx.site.get(key)
        if obj is None and key.startswith("/a/"):
            key = "/authors/" + key[len("/a/"):]
            obj = key and web.ctx.site.get(key)
            
        if obj is None and key.startswith("/b/"):
            key = "/books/" + key[len("/b/"):]
            obj = key and web.ctx.site.get(key)
        
        if obj is None and web.re_compile(r"/.*/OL\d+[A-Z]"):
            olid = web.safestr(key).split("/")[-1]
            key = web.ctx.site._request("/olid_to_key", data={"olid": olid}).key
            obj = key and web.ctx.site.get(key)
        return obj

    def _split(self, path):
        """Splits the path as required by the get_readable_path.
        
            >>> _split = ReadableUrlProcessor()._split

            >>> _split('/b/OL1M')
            ('/b/OL1M', '', '')
            >>> _split('/b/OL1M/foo')
            ('/b/OL1M', 'foo', '')
            >>> _split('/b/OL1M/foo/cover')
            ('/b/OL1M', 'foo', '/cover')
            >>> _split('/b/OL1M/foo/cover/bar')
            ('/b/OL1M', 'foo', '/cover/bar')
        """
        tokens = path.split('/', 4)

        prefix = '/'.join(tokens[:3])
        middle = web.listget(tokens, 3, '')
        suffix = '/'.join(tokens[4:])

        if suffix:
            suffix = '/' + suffix

        return prefix, middle, suffix
        
    def get_readable_path(self, path, get_object=None, encoding=None):
        """ Returns (real_url, readable_url) for the given url.

            >>> fakes = {}
            >>> fakes['/b/OL1M'] = web.storage(title='fake', name='fake', type=web.storage(key='/type/edition'))
            >>> fakes['/a/OL1A'] = web.storage(title='fake', name='fake', type=web.storage(key='/type/author'))
            >>> def fake_get_object(key): return fakes[key]
            ...
            >>> get_readable_path = ReadableUrlProcessor().get_readable_path

            >>> get_readable_path('/b/OL1M', get_object=fake_get_object)
            (u'/b/OL1M', u'/b/OL1M/fake')
            >>> get_readable_path('/b/OL1M/foo', get_object=fake_get_object)
            (u'/b/OL1M', u'/b/OL1M/fake')
            >>> get_readable_path('/b/OL1M/fake', get_object=fake_get_object)
            (u'/b/OL1M', u'/b/OL1M/fake')

            >>> get_readable_path('/b/OL1M/foo/cover', get_object=fake_get_object)
            (u'/b/OL1M/cover', u'/b/OL1M/fake/cover')

            >>> get_readable_path('/a/OL1A/foo/cover', get_object=fake_get_object)
            (u'/a/OL1A/cover', u'/a/OL1A/fake/cover')

        When requested for .json nothing should be changed.

            >>> get_readable_path('/b/OL1M.json')
            (u'/b/OL1M.json', u'/b/OL1M.json')
        
        For deleted pages, the readable_path must be same as the real path. 
            
            >>> fakes['/a/OL2A'] = web.storage(title='fake', name='fake', type=web.storage(key='/type/delete'))
            >>> get_readable_path('/a/OL2A', get_object=fake_get_object)
            (u'/a/OL2A', u'/a/OL2A')
            >>> get_readable_path('/a/OL2A/foo', get_object=fake_get_object)
            (u'/a/OL2A', u'/a/OL2A')
        """
        def match(path):    
            for pat, type, property, default_title in self.patterns:
                m = web.re_compile('^' + pat).match(path)
                if m:
                    prefix = m.group()
                    tokens = web.lstrips(path, prefix).split("/", 1)
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
            
            get_object = get_object or self.get_object
            thing = get_object(key)
            if thing:
                path = thing.key + ext
            path = web.safeunicode(path)
            return (path, path)

        #prefix, middle, suffix = self._split(path)
        get_object = get_object or self.get_object
        thing = get_object(prefix)
        
        # get_object may handle redirections.
        if thing:
            prefix = thing.key

        if thing and thing.type.key == type:
            title = thing.get(property) or default_title
            middle = '/' + _safepath(title.strip())
        else:
            middle = ""
        
        prefix = web.safeunicode(prefix)
        middle = web.safeunicode(middle)
        suffix = web.safeunicode(suffix)
        
        return (prefix + suffix, prefix + middle + suffix)
                
def _safepath(path):
    return get_safepath_re().sub('_', path).strip('_')
    
def urlsafe(path):
    return _safepath(path)

@web.memoize
def get_safepath_re():
    """Make regular expression that matches all unsafe chars."""
    # unsafe chars according to RFC 2396
    reserved = ";/?:@&=+$,"
    delims = '<>#%"'
    unwise = "{}|\\^[]`"
    space = ' \n\r'
    
    unsafe = reserved + delims + unwise + space
    pattern = '[%s]+' % "".join(re.escape(c) for c in unsafe)
    return re.compile(pattern)

class ProfileProcessor:
    """Processor to profile the webpage when ?profile=true is added to the url.
    """
    def __call__(self, handler):
        i = web.input(_method="GET", _profile="")
        if i._profile.lower() == "true":
            out, result = web.profile(handler)()
            if isinstance(out, web.template.TemplateResult):
                out.__body__ = out.get('__body__', '') + '<pre class="profile">' + web.websafe(result) + '</pre>'
                return out
            elif isinstance(out, basestring):
                return out + br + '<pre class="profile">' + web.websafe(result) + '</pre>'
            else:
                # don't know how to handle this.
                return out
        else:
            return handler()
    
if __name__ == "__main__":
    import doctest
    doctest.testmod()
