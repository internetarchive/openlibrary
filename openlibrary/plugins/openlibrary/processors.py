"""web.py application processors for Open Library.
"""
import web

from openlibrary.core.processors import ReadableUrlProcessor
import six

from openlibrary.core import helpers as h

urlsafe = h.urlsafe
_safepath = h.urlsafe

class ProfileProcessor:
    """Processor to profile the webpage when ?_profile=true is added to the url.
    """
    def __call__(self, handler):
        i = web.input(_method="GET", _profile="")
        if i._profile.lower() == "true":
            out, result = web.profile(handler)()
            if isinstance(out, web.template.TemplateResult):
                out.__body__ = out.get('__body__', '') + '<pre class="profile">' + web.websafe(result) + '</pre>'
                return out
            elif isinstance(out, six.string_types):
                return out + '<br/>' + '<pre class="profile">' + web.websafe(result) + '</pre>'
            else:
                # don't know how to handle this.
                return out
        else:
            return handler()

class CORSProcessor:
    """Processor to handle OPTIONS method to support
    Cross Origin Resurce Sharing.
    """
    def __call__(self, handler):
        if web.ctx.path.startswith("/api/") or web.ctx.path.endswith(".json"):
            self.add_cors_headers()
        if web.ctx.method == "OPTIONS":
            raise web.ok("")
        else:
            return handler()

    def add_cors_headers(self):
        # Allow anyone to access GET and OPTIONS requests
        allowed = "GET, OPTIONS"
        # unless the path is /account/* or /admin/*
        for p in ["/account", "/admin"]:
            if web.ctx.path.startswith(p):
                allowed = "OPTIONS"

        web.header("Access-Control-Allow-Origin", "*")
        web.header("Access-Control-Allow-Method", allowed)
        web.header("Access-Control-Max-Age", 3600*24) # one day

if __name__ == "__main__":
    import doctest
    doctest.testmod()
