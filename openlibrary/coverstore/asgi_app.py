"""ASGI entry point for the coverstore server.

Handlers that make outbound HTTP calls are ``async def`` so those calls don't
hold a worker; the web.py database and filesystem calls they also make are
still blocking, and run on the event loop. Keeping the worker count modest is
what bounds the cost of that -- see the covers service in
compose.production.yaml.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

logger = logging.getLogger("openlibrary.coverstore.asgi_app")

# Kept in sync with the allow_* arguments to CORSMiddleware below.
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
    "Access-Control-Max-Age": str(3600 * 24),
}


def create_app(configfile: str | None = None) -> FastAPI:
    from openlibrary.coverstore import code, server

    if configfile := configfile or os.getenv("COVERSTORE_CONFIG"):
        server.setup(configfile)

    app = FastAPI(
        title="Open Library Covers API",
        description="Serves and stores the book, author and work cover images behind covers.openlibrary.org.",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        strict_content_type=False,  # See: https://fastapi.tiangolo.com/advanced/strict-content-type/
    )

    @app.middleware("http")
    async def cors_everything(request: Request, call_next):
        """Fill the two gaps between CORSProcessor(cors_everything=True) and CORSMiddleware.

        CORSMiddleware only acts on requests carrying an Origin, but web.py answered
        every request with `Access-Control-Allow-Origin: *`. Sending it unconditionally
        also keeps caches honest: a response stored from an Origin-less request would
        otherwise be replayed, without the header, to a cross-origin one.
        """
        if request.method == "OPTIONS":
            # CORSMiddleware has already answered anything shaped like a preflight.
            return Response(status_code=200, headers=CORS_HEADERS)

        response = await call_next(request)
        for header, value in CORS_HEADERS.items():
            response.headers.setdefault(header, value)
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "HEAD", "OPTIONS"],
        max_age=3600 * 24,
    )

    # Needed so request.url.scheme reflects the nginx X-Forwarded-Proto, which the
    # archive.org redirect URLs are built from.
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

    Instrumentator(
        should_group_status_codes=False,
        excluded_handlers=["/health", "/metrics"],
    ).instrument(app).expose(app, include_in_schema=False)

    @app.api_route("/health", methods=["GET", "HEAD"], include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(code.router)

    return app
