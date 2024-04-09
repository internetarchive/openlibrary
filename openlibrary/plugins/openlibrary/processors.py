"""web.py application processors for Open Library.
"""

import re
import web

from openlibrary.accounts import get_current_user
from openlibrary.core import cache
from openlibrary.core.processors import ReadableUrlProcessor
from openlibrary.plugins.openlibrary.home import caching_prethread
from openlibrary.utils import dateutil

from openlibrary.core import helpers as h

urlsafe = h.urlsafe
_safepath = h.urlsafe


class ProfileProcessor:
    """Processor to profile the webpage when ?_profile=true is added to the url."""

    def __call__(self, handler):
        i = web.input(_method="GET", _profile="")
        if i._profile.lower() == "true":
            out, result = web.profile(handler)()
            if isinstance(out, web.template.TemplateResult):
                out.__body__ = (
                    out.get('__body__', '')
                    + '<pre class="profile">'
                    + web.websafe(result)
                    + '</pre>'
                )
                return out
            elif isinstance(out, str):
                return (
                    out
                    + '<br/>'
                    + '<pre class="profile">'
                    + web.websafe(result)
                    + '</pre>'
                )
            else:
                # don't know how to handle this.
                return out
        else:
            return handler()


class CORSProcessor:
    """Processor to handle OPTIONS method to support
    Cross Origin Resource Sharing.
    """

    def __init__(self, cors_prefixes=None):
        self.cors_prefixes = cors_prefixes

    def __call__(self, handler):
        if self.is_cors_path():
            self.add_cors_headers()
        if web.ctx.method == "OPTIONS":
            raise web.ok("")
        else:
            return handler()

    def is_cors_path(self):
        if self.cors_prefixes is None or web.ctx.path.endswith(".json"):
            return True
        return any(
            web.ctx.path.startswith(path_segment) for path_segment in self.cors_prefixes
        )

    def add_cors_headers(self):
        # Allow anyone to access GET and OPTIONS requests
        allowed = "GET, OPTIONS"
        # unless the path is /account/* or /admin/*
        for p in ["/account", "/admin"]:
            if web.ctx.path.startswith(p):
                allowed = "OPTIONS"

        if (
            web.ctx.path == "/account/login.json"
            and web.input(auth_provider="").auth_provider == "archive"
        ):
            allowed += ", POST"
            web.header('Access-Control-Allow-Credentials', 'true')
            web.header("Access-Control-Allow-Origin", "https://archive.org")
        else:
            web.header("Access-Control-Allow-Origin", "*")

        web.header("Access-Control-Allow-Method", allowed)
        web.header("Access-Control-Max-Age", 3600 * 24)  # one day


class PreferenceProcessor:
    """Processor to handle unauthorized patron preferece reads"""

    def __init__(self):
        self.pref_pattern = re.compile(r'^\/people\/([^/]+)\/preferences(.json|.yml)?$')

    def __call__(self, handler):
        if self.pref_pattern.match(web.ctx.path):
            user = get_current_user()
            if not user:
                # Must be logged in to see preferences
                raise web.Unauthorized()

            username = web.ctx.path.split('/')[2]
            if username != user.get_username() and not user.is_admin():
                # Can only view preferences if page owner or admin
                raise web.Forbidden()

        return handler()


class CacheablePathsProcessor:
    """Processor for caching Infogami pages.

    This processor determines if the current path matches any of the
    patterns in the `paths_and_expiries` dictionary, and if so, it
    attempts to return the page from cache.  If no cached page is found,
    it will fetch the page using the usual handler.
    """

    # Maps paths of cacheable pages to the pages' expiry times
    paths_and_expiries: dict[str, int] = {
        '/collections': 10 * dateutil.MINUTE_SECS,
        '/collections/([^/]+)': 5 * dateutil.MINUTE_SECS,
    }

    def __call__(self, handler):
        # XXX : Caches `GET` calls to edit pages (and other modes)
        # XXX : Page encoding not taken into account
        # XXX : Page language not taken into account
        def get_page() -> dict:
            """Fetches the page using the usual handler.
            In order to cache the page, it is returned as a dictionary.
            """
            _page = handler()
            return dict(_page)

        def get_cached_page(path: str) -> dict:
            """Returns the page located at the given path.
            Attempts to return a cached page, if one exists. The full
            path is used as the cache key for the page.
            """
            mc = cache.memcache_memoize(get_page, path, self.paths_and_expiries[match], prethread=caching_prethread())
            _page = mc()

            if not _page:
                mc(_cache='delete')

            return _page

        if web.ctx.method != 'GET':
            # Don't cache non-GET requests
            handler()

        # Determine if current path matches a cacheable path pattern
        match = None
        for pattern in self.paths_and_expiries:
            if re.match(pattern, web.ctx.path):
                match = pattern
                break

        if not match:
            # No match found, continue processing as per usual
            return handler()

        page = get_cached_page(web.ctx.fullpath)

        return web.template.TemplateResult(page)


if __name__ == "__main__":
    import doctest

    doctest.testmod()
