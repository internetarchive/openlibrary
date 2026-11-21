"""XRPC procedures published by the ``community.lexicon.media.book`` lexicons.

Both procedures are anonymous and read-only: they project catalog data onto
``defs#editionResults`` and never touch a repository.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from openlibrary.atproto.models import ResolveEditionsRequest, SearchEditionsRequest  # noqa: TC001
from openlibrary.atproto.provider import (
    InvalidQuery,
    build_results,
    load_bundle,
    resolve_identifier_keys,
    search_edition_keys,
)

logger = logging.getLogger("openlibrary.atproto")

router = APIRouter(tags=["atproto"])

XRPC_PREFIX = "/xrpc/community.lexicon.media.book"
XRPC_PATH_PREFIX = "/xrpc/"


@router.post(f"{XRPC_PREFIX}.resolveEditions", response_model=None)
async def resolve_editions(body: ResolveEditionsRequest) -> dict:
    """Resolve editions by exact identifier equality."""
    keys = await run_in_threadpool(resolve_identifier_keys, body.identifiers)
    page = keys[body.offset : body.offset + body.limit]
    bundles = await run_in_threadpool(load_bundle, page) if page else {}
    return build_results(page, bundles, len(keys), body.offset, body.limit)


@router.post(f"{XRPC_PREFIX}.searchEditions", response_model=None)
async def search_editions(body: SearchEditionsRequest) -> dict | JSONResponse:
    """Search the catalog with free text and structured relevance hints."""
    try:
        page, total = await search_edition_keys(body)
    except InvalidQuery:
        return JSONResponse(
            status_code=400,
            content={"error": "InvalidQuery", "message": "Supply at least one nonblank q, title, author, or nonempty identifiers array."},
        )
    bundles = await run_in_threadpool(load_bundle, page) if page else {}
    return build_results(page, bundles, total, body.offset, body.limit)


def install_error_handlers(app: FastAPI) -> None:
    """Answer XRPC paths with the ``{error, message}`` body atproto clients parse.

    Everything outside ``/xrpc/`` keeps FastAPI's and Starlette's defaults.
    """

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        if not request.url.path.startswith(XRPC_PATH_PREFIX):
            return await request_validation_exception_handler(request, exc)
        problems = "; ".join(f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors())
        return JSONResponse(status_code=400, content={"error": "InvalidRequest", "message": problems or "The request body is invalid."})

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        if not request.url.path.startswith(XRPC_PATH_PREFIX):
            raise exc
        logger.error("xrpc request failed: %s", exc, exc_info=exc)
        return JSONResponse(status_code=500, content={"error": "InternalServerError", "message": "The provider failed to answer this request."})
