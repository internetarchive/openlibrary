"""
FastAPI endpoint for /books/{key}/borrow.

This is a parallel implementation alongside the legacy web.py version in
openlibrary/plugins/upstream/borrow.py, which stays in place until this one
is fully validated in production. Both share the handle_borrow_async() outcome
logic; only the redirect/flash/cookie/404 handling differs per framework.
"""

from __future__ import annotations

import json
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from infogami import config
from openlibrary.plugins.upstream.borrow import (
    BorrowNotFound,
    BorrowParams,
    BorrowRedirect,
    handle_borrow_async,
)

router = APIRouter()


def _borrow_params_from_request(request: Request) -> BorrowParams:
    """FastAPI dependency: builds BorrowParams from the request's query
    params, the same way openlibrary.fastapi.models.SolrInternalsParams is
    built via its own from_request()."""
    return BorrowParams.model_validate(request.query_params)


@router.get("/books/{olid}/{slug}/borrow")
@router.post("/books/{olid}/{slug}/borrow")
async def borrow(
    request: Request,
    olid: str,
    slug: str,
    params: Annotated[BorrowParams, Depends(_borrow_params_from_request)],
) -> Response:
    """Called when the user wants to borrow the edition. Mirrors the legacy
    web.py borrow.GET/POST handler, passing fastapi=True so the interstitial
    render branch knows to render itself for a standalone page (no site
    stylesheet/JS bundle loaded) rather than for the web.py request cycle.
    """
    key = f"/books/{olid}"
    result = await handle_borrow_async(key, params, s3_cookie=request.cookies.get("s3"), fastapi=True)

    match result:
        case BorrowNotFound():
            raise HTTPException(status_code=404)
        case BorrowRedirect():
            response = RedirectResponse(
                url=result.url,
                status_code=301 if result.permanent else 303,
            )
            if result.clear_login_cookie:
                response.delete_cookie(config.login_cookie_name)
            if result.flash:
                flash_type, flash_message = result.flash
                flash_json = json.dumps([{"type": flash_type, "message": flash_message}])
                # web.py's flash cookie reader (infogami.utils.flash / web.cookies())
                # unconditionally percent-decodes the raw cookie value, symmetric with
                # web.setcookie()'s percent-encoding on write. Starlette's default
                # cookie quoting instead backslash-escapes values containing commas
                # (RFC 2109 style), which web.py's decoder can't reverse -- so the
                # flash message would silently vanish unless we percent-encode it
                # ourselves here to match web.py's wire format.
                response.set_cookie("flash", quote(flash_json, safe=""))
            return response
        case _:
            # The interstitial render_template() result, returned as-is --
            # its own inline style/script (from fastapi=True above) is all
            # the presentation it gets, since no site stylesheet/JS bundle
            # is loaded here.
            return HTMLResponse(str(result))
