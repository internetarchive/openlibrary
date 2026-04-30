"""web.py application processors for Open Library."""

import re
from typing import ClassVar, cast

import web
from infogami import config

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
                out.__body__ = out.get("__body__", "") + '<pre class="profile">' + web.websafe(result) + "</pre>"
                return out
            elif isinstance(out, str):
                return out + "<br/>" + '<pre class="profile">' + web.websafe(result) + "</pre>"
            else:
                # don't know how to handle this.
                return out
        else:
            return handler()


class CORSProcessor:
    """Processor to handle OPTIONS method to support
    Cross Origin Resource Sharing.
    """

    def __init__(
        self,
        cors_paths: set[str] | None = None,
        cors_prefixes: set[str] | None = None,
        cors_everything: bool = False,
    ):
        self.cors_paths = cors_paths or set()
        self.cors_prefixes = cors_prefixes or set()
        self.cors_everything = cors_everything

    def __call__(self, handler):
        if self.is_cors_path():
            self.add_cors_headers()
        if web.ctx.method == "OPTIONS":
            raise web.ok("")
        else:
            return handler()

    def is_cors_path(self):
        path = cast(str, web.ctx.path)
        return (
            self.cors_everything
            or path.endswith(".json")
            or path in self.cors_paths
            or any(web.ctx.path.startswith(path_segment) for path_segment in self.cors_prefixes)
        )

    def add_cors_headers(self):
        # Allow anyone to access GET and OPTIONS requests
        allowed = "GET, OPTIONS"
        # unless the path is /account/* or /admin/*
        for p in ["/account", "/admin"]:
            if web.ctx.path.startswith(p):
                allowed = "OPTIONS"

        if web.ctx.path == "/account/login.json" and web.input(auth_provider="").auth_provider == "archive":
            allowed += ", POST"
            web.header("Access-Control-Allow-Credentials", "true")
            web.header("Access-Control-Allow-Origin", "https://archive.org")
        else:
            web.header("Access-Control-Allow-Origin", "*")

        web.header("Access-Control-Allow-Method", allowed)
        web.header("Access-Control-Max-Age", 3600 * 24)  # one day


class PreferenceProcessor:
    """Processor to handle unauthorized patron preference reads"""

    def __init__(self):
        self.pref_pattern = re.compile(r"^\/people\/([^/]+)\/preferences(.json|.yml)?$")

    def __call__(self, handler):
        if self.pref_pattern.match(web.ctx.path):
            user = get_current_user()
            if not user:
                # Must be logged in to see preferences
                raise web.Unauthorized

            username = web.ctx.path.split("/")[2]
            if username != user.get_username() and not user.is_admin():
                # Can only view preferences if page owner or admin
                raise web.Forbidden

        return handler()


class CookieValidationProcessor:
    """Processor: enforce human verification based on nginx signals and cookie integrity.

    Checks cookie integrity before allowing requests through. Skipped on the
    verification endpoint itself. Trigger conditions (evaluated in order):
    1. Valid vf cookie — pass through immediately.
    2. Valid session cookie — pass through immediately.
    3. Spoofed vf or session cookie — purge the cookie, return 403 + X-Abuse header.
    4. nginx sets X-OL-Verify-Human — redirect to /verify_human with next= URL.
    """

    EXEMPT_PATHS: ClassVar[set[str]] = {"/verify_human"}

    @staticmethod
    def _reject_spoofed_cookie(name: str) -> None:
        """Purge a forged cookie and raise 403 with an abuse signal header."""
        web.setcookie(name, "", expires=-1, secure=True, httponly=True)
        web.header("X-Abuse", "spoofed-cookie")
        raise web.HTTPError("403 Forbidden")

    def __call__(self, handler):
        # We don't want to bounce identified crawlers that index us
        from openlibrary.plugins.openlibrary.code import is_recognized_bot

        if web.ctx.path not in self.EXEMPT_PATHS and not is_recognized_bot():
            from openlibrary.accounts.model import (
                verify_session_cookie,
                verify_verification_cookie,
            )

            if cookie_value := web.cookies().get("vf"):
                if verify_verification_cookie(cookie_value):
                    return handler()
                self._reject_spoofed_cookie("vf")

            session_cookie_name = config.get("login_cookie_name", "session")
            if session_value := web.cookies().get(session_cookie_name):
                if verify_session_cookie(session_value):
                    return handler()
                self._reject_spoofed_cookie(session_cookie_name)

            if web.ctx.env.get("HTTP_X_OL_VERIFY_HUMAN") == "1":
                next_url = web.ctx.env.get("REQUEST_URI") or web.ctx.env.get("HTTP_X_REQUEST_URI") or web.ctx.path
                raise web.seeother("/verify_human?next=" + web.urlquote(next_url))

        return handler()


if __name__ == "__main__":
    import doctest

    doctest.testmod()
