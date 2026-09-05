"""
FastAPI endpoint for /books/{key}/borrow.

This is a parallel implementation alongside the legacy web.py version in
openlibrary/plugins/upstream/borrow.py, which stays in place until this one
is fully validated in production. Both share the handle_borrow_async() outcome
logic; only the redirect/flash/cookie/404 handling differs per framework.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from infogami import config
from openlibrary.fastapi.utils import set_flash_cookie
from openlibrary.plugins.upstream.borrow import (
    BorrowNotFound,
    BorrowParams,
    BorrowRedirect,
    handle_borrow_async,
)
from openlibrary.utils.request_context import site

router = APIRouter()


def _borrow_params_from_request(request: Request) -> BorrowParams:
    """FastAPI dependency: builds BorrowParams from the request's query
    params, the same way openlibrary.fastapi.models.SolrInternalsParams is
    built via its own from_request()."""
    return BorrowParams.model_validate(request.query_params)


def _resolve_ocaid_to_olid(ocaid: str) -> str | None:
    """Resolves an IA identifier to its canonical OL edition OLID, or None
    if there's no such edition."""
    ia_edition = site.get().get(f"/books/ia:{ocaid}")
    if not ia_edition:
        return None
    edition = site.get().get(ia_edition.location)
    return edition.key.removeprefix("/books/")


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
                set_flash_cookie(response, *result.flash)
            return response
        case _:
            # The interstitial render_template() result, returned as-is --
            # its own inline style/script (from fastapi=True above) is all
            # the presentation it gets, since no site stylesheet/JS bundle
            # is loaded here.
            return HTMLResponse(str(result))


@router.get("/borrow/ia/{ocaid}")
async def checkout_with_ocaid_get(ocaid: str, request: Request) -> Response:
    """Redirect shim: translates an IA identifier into the canonical OL
    /borrow URL. Mirrors the legacy web.py checkout_with_ocaid.GET, which
    redirects rather than forwarding in-process -- unlike POST below, this
    is browser-navigable, so it should land on (and become bookmarkable at)
    the canonical URL rather than staying on this one.
    """
    olid = _resolve_ocaid_to_olid(ocaid)
    if olid is None:
        raise HTTPException(status_code=404)
    url = f"/books/{olid}/x/borrow"
    query = str(request.query_params)
    if query:
        url += f"?{query}"
    return RedirectResponse(url=url, status_code=303)


@router.post("/borrow/ia/{ocaid}")
async def checkout_with_ocaid_post(ocaid: str, request: Request) -> Response:
    """Forwards a borrow request to the canonical /borrow route above.
    Mirrors the legacy web.py checkout_with_ocaid.POST, which does the same
    in-process (calling borrow().POST(...) directly) rather than
    redirecting -- a POST isn't bookmarked, so there's nothing to gain by
    round-tripping through the browser first.
    """
    olid = _resolve_ocaid_to_olid(ocaid)
    if olid is None:
        raise HTTPException(status_code=404)
    return await borrow(request, olid=olid, slug="x", params=_borrow_params_from_request(request))
