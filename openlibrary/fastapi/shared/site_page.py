"""HTML pages in the site shell: return a ``SitePage`` from a route on a ``SitePageRoute`` router.

.. code-block:: python

    pages = APIRouter(route_class=SitePageRoute)

    @pages.get("/advancedsearch")
    async def advancedsearch(form: Annotated[AdvancedSearchForm, Query()], nav: SearchNavDep) -> SitePage:
        body = render_jinja_template("search/advancedsearch.html.jinja", form=form, nav=nav)
        return SitePage(body, page=PageMeta(title=_("Advanced Search")))

The route class wraps the body in the shell (head, header, footer), as infogami's
``layout_processor`` does on web.py, so a route never handles the shell's inputs.
A route that needs the logged-in user takes ``CurrentUserDep``; the shell reuses it.
See ``docs/core/fastapi-pages.md``.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine, Sequence
from dataclasses import replace
from typing import TYPE_CHECKING, Annotated, Any
from urllib.parse import quote, unquote

from fastapi import Depends, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.routing import APIRoute

from openlibrary.accounts.model import check_human_cookies
from openlibrary.core.shell.context import render_site
from openlibrary.core.shell.request import FLASH_COOKIE, PageMeta, ShellRequest
from openlibrary.core.shell.user import ShellUser, load_shell_user
from openlibrary.utils.request_context import req_context

if TYPE_CHECKING:
    from fastapi.params import Depends as DependsParam
    from starlette.types import Receive, Scope, Send


def get_shell_user(request: Request) -> ShellUser | None:
    """The logged-in user, or None for a visitor. Looked up once per request.

    Not ``openlibrary.accounts.get_current_user``, which returns the full ``User``.
    Sync def, so FastAPI runs it in a worker thread: ``load_shell_user()`` blocks
    (see its TODO). ``SitePageRoute`` reuses the result for the shell, so a page
    that takes ``CurrentUserDep`` costs no second lookup.
    """
    if not hasattr(request.state, "current_user"):
        request.state.current_user = load_shell_user()
    return request.state.current_user


CurrentUserDep = Annotated[ShellUser | None, Depends(get_shell_user)]


class SitePage(HTMLResponse):
    """A page body for ``SitePageRoute`` to wrap in the site shell.

    ``page`` sets the shell's per-page values (title, CSS file, body classes,
    meta tags), as ``$var``/``$putctx`` do in Templetor; the shell escapes them
    (see ``PageMeta``). Without a title, the title is the path, as on web.py.

    It is a response, so FastAPI passes it to the route class untouched instead
    of serializing it.
    """

    def __init__(self, body: str, page: PageMeta | None = None, status_code: int = 200, headers: dict[str, str] | None = None) -> None:
        super().__init__(body, status_code=status_code, headers=headers)
        self.page_body = body
        self.page = page
        self.in_shell = False

    def wrap_in_shell(self, req: ShellRequest, user: ShellUser | None) -> None:
        page = self.page or PageMeta()
        if not page.title:
            page = replace(page, title=req.path[1:])
        self.body = self.render(render_site(self.page_body, req, page, user))
        self.headers["content-length"] = str(len(self.body))
        # Shown now, so expire them, as web.py's flash_processor does.
        if req.flash_messages:
            self.delete_cookie(FLASH_COOKIE)
        self.in_shell = True

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self.in_shell:
            raise RuntimeError("SitePage was not wrapped in the site shell: return it from a route on an APIRouter(route_class=SitePageRoute)")
        await super().__call__(scope, receive, send)


def _human_check_response(request: Request) -> Response | None:
    """web.py's ``CookieValidationProcessor``, for pages: a response that stops the request, or None.

    nginx challenges suspicious requests only when they carry no cookies, and
    leaves checking the cookies to the app, so without this a bot skips the
    challenge by sending any ``vf`` cookie. A signature check, no I/O.
    """
    if req_context.get().is_recognized_bot:
        return None
    # web.py percent-encodes cookie values and web.cookies() decodes them; Starlette doesn't.
    check = check_human_cookies({name: unquote(value) for name, value in request.cookies.items()})
    if check.verified:
        return None
    if check.spoofed:
        response = PlainTextResponse("Forbidden", status_code=403, headers={"X-Abuse": "spoofed-cookie"})
        response.delete_cookie(check.spoofed, secure=True, httponly=True)
        return response
    if request.headers.get("x-ol-verify-human") == "1":
        next_url = request.headers.get("x-request-uri") or request.url.path + (f"?{request.url.query}" if request.url.query else "")
        return RedirectResponse("/verify_human?next=" + quote(next_url), status_code=303)
    return None


async def _keep_sub_response(request: Request, response: Response) -> None:
    # FastAPI drops the headers set on its injected Response when a route returns
    # a Response itself, as page routes do; SitePageRoute copies them over.
    request.state.sub_response = response


def _copy_headers(sub_response: Response, response: Response) -> None:
    """Add the headers and cookies set on FastAPI's injected ``Response`` to the returned one.

    A header the returned response sets itself wins, except: cookies are all
    sent, the injected ones last, so a browser keeps those for a name set twice;
    and ``Vary`` values are merged, so a cache varies on all of them. The injected
    response's status code is ignored, as FastAPI does; set it on the ``SitePage``.
    """
    own_names = {name for name, _ in response.raw_headers}
    for name, value in sub_response.raw_headers:
        # Already there when FastAPI built the response itself (a route that returned data, not a Response).
        if (name, value) in response.raw_headers or name == b"content-length":
            continue
        if name == b"vary" and name in own_names:
            # Every Vary line the response has, not just the first, as one merged line.
            lines = [*response.headers.getlist("vary"), value.decode("latin-1")]
            del response.headers["vary"]
            response.headers["vary"] = ", ".join(dict.fromkeys(v.strip() for line in lines for v in line.split(",")))
        elif name == b"set-cookie" or name not in own_names:
            response.raw_headers.append((name, value))


class SitePageRoute(APIRoute):
    """Wraps a ``SitePage`` returned by the route in the site shell.

    Before the route runs, it rejects forged ``vf`` and session cookies, as
    web.py does for every page. After, it loads the user for the shell only if
    the route returned a ``SitePage`` (a redirect or an error needs none),
    reusing ``CurrentUserDep``'s if the route took it. Headers and cookies set on
    FastAPI's injected ``Response`` are added to whatever the route returns (see
    ``_copy_headers``); its status code isn't. Every
    route answers HEAD as well as GET (as web.py does) and is left out of the
    OpenAPI schema.
    """

    def __init__(self, path: str, endpoint: Callable[..., Any], *, dependencies: Sequence[DependsParam] | None = None, **kwargs: Any) -> None:
        # Including a router copies its routes through this __init__ again, adding this
        # twice; FastAPI runs a dependency once per request, so that's harmless.
        dependencies = [Depends(_keep_sub_response), *(dependencies or [])]
        # FastAPI, unlike Starlette and web.py, doesn't answer HEAD for a GET route; crawlers and uptime checks send it.
        if (methods := kwargs.get("methods")) and "GET" in methods:
            kwargs["methods"] = {*methods, "HEAD"}
        super().__init__(path, endpoint, dependencies=dependencies, **kwargs | {"include_in_schema": False})

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def site_page_handler(request: Request) -> Response:
            if (rejection := _human_check_response(request)) is not None:
                return rejection
            response = await handler(request)
            if isinstance(response, SitePage):
                if hasattr(request.state, "current_user"):
                    user = request.state.current_user
                else:
                    user = await run_in_threadpool(get_shell_user, request)
                # The shell is built from values loaded already, so it does no I/O on the event loop.
                response.wrap_in_shell(ShellRequest.from_starlette(request), user)
            if (sub_response := getattr(request.state, "sub_response", None)) is not None:
                _copy_headers(sub_response, response)
            return response

        return site_page_handler
