"""Handler for deprecated web.py endpoints.

Redirects deprecated endpoints to port 18080 in dev environment,
or raises a loud error in production.
This is temporary while we migrate to fastapi and have two containers running.
"""

import httpx
import web

import infogami
from infogami.utils import delegate


def handle_deprecated_request():
    """Handle the deprecated endpoint request."""
    # Check if we're in dev environment
    if "dev" in infogami.config.features:
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

    encoding = "json"

    def GET(self, *args):
        return handle_deprecated_request()

    def POST(self, *args):
        return handle_deprecated_request()

    def DELETE(self, *args):
        return handle_deprecated_request()


# List of deprecated paths (all json)
DEPRECATED_PATHS = [
    "/search",
    "/search/lists",
    "/search/subjects",
    "/search/authors",
    "/search/inside",
    "/languages",
    "/reading-goal",
    "(/subjects/[^/]+)",
    "(/publishers/[^/]+)",
    "(/partials/[^/]+)",
]
