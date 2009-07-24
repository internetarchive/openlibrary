"""web.py application processors for Open Library.
"""
import web
import urllib

class ReadableUrlProcessor:
    """Open Library code works with urls like /books/OL1M and /books/OL1M/cover.
    This processor seemlessly changes the urls to /books/OL1M/title and /books/OL1M/title/cover.
    
    The changequery function is also customized to support this.    
    """
    patterns = [
        (r'/books/OL\d+M', '/type/edition', 'title', 'untitled'),
        (r'/authors/OL\d+A', '/type/author', 'name', 'noname'),
        (r'/works/OL\d+W', '/type/work', 'title', 'untitled')
    ]
    
    def __call__(self, handler):
        real_path, readable_path = self.get_readable_path(web.ctx.path, encoding=web.ctx.encoding)

        #@@ web.ctx.path is either quoted or unquoted depends on whether the application is running
        #@@ using builtin-server or lighttpd. Thats probably a bug in web.py. 
        #@@ take care of that case here till that is fixed.
        # @@ Also, the redirection must be done only for GET requests.
        if readable_path != web.ctx.path and readable_path != urllib.quote(web.utf8(web.ctx.path)) and web.ctx.method == "GET":
            raise web.seeother(readable_path.encode('utf-8') + web.ctx.query.encode('utf-8'))

        web.ctx.readable_path = readable_path
        web.ctx.path = real_path
        web.ctx.fullpath = web.ctx.path + web.ctx.query
        return handler()

    def get_object(self, key):
        return web.ctx.site.get(key)

    def _split(self, path):
        """Splits the path as required by the get_readable_path.
        
            >>> _split = ReadableUrlProcessor()._split

            >>> _split('/books/OL1M')
            ('/books/OL1M', '', '')
            >>> _split('/books/OL1M/foo')
            ('/books/OL1M', 'foo', '')
            >>> _split('/books/OL1M/foo/cover')
            ('/books/OL1M', 'foo', '/cover')
            >>> _split('/books/OL1M/foo/cover/bar')
            ('/books/OL1M', 'foo', '/cover/bar')
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
            >>> fakes['/books/OL1M'] = web.storage(title='fake', name='fake', type=web.storage(key='/type/edition'))
            >>> fakes['/authors/OL1A'] = web.storage(title='fake', name='fake', type=web.storage(key='/type/author'))
            >>> def fake_get_object(key): return fakes[key]
            ...
            >>> get_readable_path = ReadableUrlProcessor().get_readable_path

            >>> get_readable_path('/books/OL1M', get_object=fake_get_object)
            ('/books/OL1M', '/books/OL1M/fake')
            >>> get_readable_path('/books/OL1M/foo', get_object=fake_get_object)
            ('/books/OL1M', '/books/OL1M/fake')
            >>> get_readable_path('/books/OL1M/fake', get_object=fake_get_object)
            ('/books/OL1M', '/books/OL1M/fake')

            >>> get_readable_path('/books/OL1M/foo/cover', get_object=fake_get_object)
            ('/books/OL1M/cover', '/books/OL1M/fake/cover')

            >>> get_readable_path('/authors/OL1A/foo/cover', get_object=fake_get_object)
            ('/authors/OL1A/cover', '/authors/OL1A/fake/cover')

        When requested for .json nothing should be changed.

            >>> get_readable_path('/books/OL1M.json')
            ('/books/OL1M.json', '/books/OL1M.json')
        """
        def match(path):    
            for pat, type, property, default_title in self.patterns:
                if web.re_compile('^' + pat).match(path):
                    return type, property, default_title
            return None, None, None

        type, property, default_title = match(path)

        if not type \
           or encoding is not None \
           or path.endswith(".json"):
            return (path, path)

        prefix, middle, suffix = self._split(path)
        get_object = get_object or self.get_object
        thing = get_object(prefix)

        if not thing or thing.type.key != type:
            return (path,path)

        title = thing.get(property).strip() or default_title
        middle = '/' + title.replace(' ', '_').replace('/', '_').encode('utf-8')
        return (prefix + suffix, prefix + middle + suffix)

class ProfileProcessor:
    """Processor to profile the webpage when ?profile=true is added to the url.
    """
    def __call__(self, handler):
        i = web.input(_method="GET", _profile="")
        if i._profile.lower() == "true":
            out, result = web.profile(handler)()
            if isinstance(out, web.template.TemplateResult):
                out.__body__ = out.get('__body__', '') + '<pre>' + web.websafe(result) + '</pre>'
                return out
            elif isinstance(out, basestring):
                return out + '<pre>' + web.websafe(result) + '</pre>'
            else:
                # don't know how to handle this.
                return out
        else:
            return handler()

if __name__ == "__main__":
    import doctest
    doctest.testmod()