"""web.py application processors for Open Library.
"""

import re
from datetime import datetime

import web

from infogami.core.code import logout as infogami_logout
from openlibrary.accounts import get_current_user
from openlibrary.core import helpers as h
from openlibrary.core.processors import (
    ReadableUrlProcessor,  # noqa: F401 side effects may be needed
)

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
    """Processor to handle unauthorized patron preference reads"""

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


cutoff = '2024-11-07T18:00:00'
stale_date = datetime.fromisoformat(cutoff)


class RequireLogoutProcessor:

    def __call__(self, handler):
        if session_cookie := web.cookies().get("session"):
            split_cookie = session_cookie.split(",")
            create_date = datetime.fromisoformat(split_cookie[1])

            if create_date < stale_date:
                infogami_logout().POST()

        return handler()


if __name__ == "__main__":
    import doctest

    doctest.testmod()
