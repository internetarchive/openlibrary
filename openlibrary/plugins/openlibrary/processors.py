"""web.py application processors for Open Library.
"""
import web

from openlibrary.core.processors import ReadableUrlProcessor

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
            elif isinstance(out, basestring):
                return out + '<br/>' + '<pre class="profile">' + web.websafe(result) + '</pre>'
            else:
                # don't know how to handle this.
                return out
        else:
            return handler()
    
if __name__ == "__main__":
    import doctest
    doctest.testmod()
