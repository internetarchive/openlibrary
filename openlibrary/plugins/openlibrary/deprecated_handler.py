"""Handler for deprecated web.py endpoints.

Redirects deprecated endpoints to port 18080 in dev environment,
or raises a loud error in production.
This is temporary while we migrate to fastapi and have two containers running.
"""

import sys as _sys
import traceback as _tb

import httpx
import web

from infogami.utils import delegate
from openlibrary.core.env import get_ol_env

_orig_rawinput = web.webapi.rawinput


def _traced_rawinput(method=None):
    if web.ctx.get("env", {}).get("REQUEST_METHOD") == "POST":
        print("[RAWINPUT] method=%r\n%s" % (method, "".join(_tb.format_stack()[-12:])), file=_sys.stderr, flush=True)
    return _orig_rawinput(method)


web.webapi.rawinput = _traced_rawinput
web.rawinput = _traced_rawinput


def handle_deprecated_request():
    """Handle the deprecated endpoint request."""
    # Check if we're in dev environment
    if get_ol_env().LOCAL_DEV:
        return proxy_to_fastapi()
    else:
        # Raise a loud error in production
        error_msg = f"DEPRECATED ENDPOINT ACCESSED: {web.ctx.path}. This endpoint has been migrated to FastAPI and should not be accessed in production."
        raise web.internalerror(error_msg)


def proxy_to_fastapi():
    """Proxy the current request to the FastAPI container."""
    # Internal Docker URL for fast_web service
    base_url = "http://fast_web:8080"
    url = base_url + web.ctx.fullpath

    # Forward headers (excluding Host which should be set by httpx)
    headers = {k[5:].replace("_", "-").title(): v for k, v in web.ctx.environ.items() if k.startswith("HTTP_") and k != "HTTP_HOST"}
    # Content-Type and Content-Length are usually not prefixed with HTTP_
    if "CONTENT_TYPE" in web.ctx.environ:
        headers["Content-Type"] = web.ctx.environ["CONTENT_TYPE"]

    import sys

    print(
        f"[PROXYDEBUG] ct={web.ctx.environ.get('CONTENT_TYPE')!r} cl={web.ctx.environ.get('CONTENT_LENGTH')!r} datalen={len(web.data())} has_fieldstorage={'_fieldstorage' in web.ctx} ctxdata={'data' in web.ctx}",
        file=sys.stderr,
        flush=True,
    )
    try:
        with httpx.Client(follow_redirects=False, timeout=60.0) as client:
            resp = client.request(
                method=web.ctx.method,
                url=url,
                headers=headers,
                content=web.data(),
                cookies=web.cookies(),
            )
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        raise web.internalerror(f"Proxy request failed: {e}")

    # Set response headers
    for k, v in resp.headers.items():
        if k.lower() not in (
            "content-encoding",
            "transfer-encoding",
            "content-length",
        ):
            web.header(k, v)

    # Set a custom header to indicate this was proxied through web.py
    web.header("x-proxied-by", "web.py")

    # Set response status code
    web.ctx.status = f"{resp.status_code} {resp.reason_phrase}"

    return delegate.RawText(resp.content)


class DeprecatedEndpointHandler(delegate.page):
    """Catches all deprecated endpoints and redirects them."""

    def GET(self, *args):
        return handle_deprecated_request()

    def POST(self, *args):
        return handle_deprecated_request()

    def DELETE(self, *args):
        return handle_deprecated_request()


class DeprecatedJSONEndpointHandler(DeprecatedEndpointHandler):
    encoding = "json"


# List of deprecated paths and encodings
DEPRECATED_PATHS: list[tuple[str, str | None]] = [
    (r"/search", "json"),
    (r"/search/lists", "json"),
    (r"/search/subjects", "json"),
    (r"/search/authors", "json"),
    (r"/search/inside", "json"),
    (r"/languages", "json"),
    (r"/reading-goal", "json"),
    (r"(/subjects/[^/]+)", "json"),
    (r"(/publishers/[^/]+)", "json"),
    (r"(/partials/[^/]+)", "json"),
    (r"/books-display", "json"),
    (r"/books-display/user-state", "json"),
    (r"/api/books", "json"),
    (r"/api/books", None),
    # Simplified regex
    (r"/api/volumes/(.+)", "json"),
    (r"/api/volumes/(.+)", None),
    (r"/prices", "json"),
    (r"/works/OL(\d+)W/awards", "json"),
    (r"/works/OL\d+W/ratings", "json"),
    (r"/awards/count", "json"),
    (r"/cdn/archive.org/(.+)", None),
    (r"/check-ins/(\d+)", None),
    # FastAPI /status/testing.json (testing-environment status)
    (r"/status/testing", "json"),
    (r"/people/[^/]+/follows", "json"),
    # `pages` is keyed by the regex text, so this has to match lists.py's path
    # string exactly; an equivalent spelled differently registers alongside the
    # old GET-only handler instead of replacing it.
    (r"(/(?:people|books|works|authors|subjects)/[^/]+)/lists", "json"),
    (r"/people/[^/]+/lists/OL\d+L", "json"),
    (r"/lists/OL\d+L", "json"),
    (r"/series/OL\d+L", "json"),
    (r"/people/[^/]+/lists/OL\d+L/delete", "json"),
    (r"/lists/OL\d+L/delete", "json"),
    (r"/people/[^/]+/lists/OL\d+L/editions", "json"),
    (r"/lists/OL\d+L/editions", "json"),
    (r"/series/OL\d+L/editions", "json"),
    (r"/authors/merge", "json"),
    (r"/import/preview", "json"),
    (r"/people/[^/]+/books/(?:want-to-read|currently-reading|already-read|stopped-reading)", "json"),
    (r"/people/[^/]+/lists/OL\d+L/seeds", "json"),
    (r"/lists/OL\d+L/seeds", "json"),
    (r"/series/OL\d+L/seeds", "json"),
    (r"/people/[^/]+/lists/OL\d+L/subjects", "json"),
    (r"/lists/OL\d+L/subjects", "json"),
    (r"/series/OL\d+L/subjects", "json"),
    # Works endpoints migrated to FastAPI
    (r"/works/OL(\d+)W/check-ins", "json"),
    (r"/works/OL(\d+)W/bookshelves", "json"),
    (r"(/works/OL\d+W)/editions", "json"),
    (r"(/authors/OL\d+A)/works", "json"),
    (r"/hide_banner", None),
    (r"/api/link", "json"),
    (r"/api/monthly_logins", "json"),
    (r"/qrcode", None),
]
