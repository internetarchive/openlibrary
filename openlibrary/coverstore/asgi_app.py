"""ASGI entry point for the coverstore server.

The route handlers are deliberately sync ``def``: FastAPI runs those in a
threadpool, so the blocking web.py database and filesystem calls underneath
stay safe without being rewritten as async.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

logger = logging.getLogger("openlibrary.coverstore.asgi_app")


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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "OPTIONS"],
        max_age=3600 * 24,
    )

    # Needed so request.url.scheme reflects the nginx X-Forwarded-Proto, which the
    # archive.org redirect URLs are built from.
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

    Instrumentator(
        should_group_status_codes=False,
        excluded_handlers=["/health", "/metrics"],
    ).instrument(app).expose(app, include_in_schema=False)

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(code.router)

    return app
