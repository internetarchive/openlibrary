"""
FastAPI endpoints for import preview.
"""

from __future__ import annotations

from typing import Annotated

import web
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status

from openlibrary.accounts import get_current_user
from openlibrary.fastapi.auth import AuthenticatedUser, require_authenticated_user
from openlibrary.plugins.importapi.import_ui import ImportPreviewRequest
from openlibrary.utils.request_context import site, web_ctx_ip

router = APIRouter(tags=["import"])


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host
    return "127.0.0.1"


def _build_preview_response(
    source: str | None,
    provider: str | None,
    identifier: str | None,
    save: bool,
    request: Request,
) -> dict:
    web.ctx.site = site.get()

    try:
        req = ImportPreviewRequest.from_input(
            {
                "source": source,
                "provider": provider,
                "identifier": identifier,
                "save": "true" if save else "false",
            }
        )
    except ValueError as e:
        return {"success": False, "error": str(e)}

    with web_ctx_ip(_client_ip(request)):
        return dict(req.metadata_provider.do_import(req.identifier, req.save))


@router.get("/import/preview.json")
def import_preview_json_get(
    request: Request,
    _: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    source: Annotated[
        str | None,
        Query(
            description="Source in format 'provider:identifier' (e.g. 'amazon:ASIN')",
        ),
    ] = None,
    provider: Annotated[
        str | None,
        Query(
            description="Metadata provider: amazon, ia, or marc",
        ),
    ] = None,
    identifier: Annotated[
        str | None,
        Query(
            description="Identifier for the given provider",
        ),
    ] = None,
) -> dict:
    """
    Preview import metadata without saving.

    Requires admin, librarian, or super-librarian role.
    """
    user = get_current_user()
    if not (user and (user.is_admin() or user.is_librarian() or user.is_super_librarian())):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return _build_preview_response(source, provider, identifier, save=False, request=request)


@router.post("/import/preview.json")
def import_preview_json_post(
    request: Request,
    _: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    source: Annotated[str | None, Form()] = None,
    provider: Annotated[str | None, Form()] = None,
    identifier: Annotated[str | None, Form()] = None,
    save: Annotated[bool, Form()] = False,
) -> dict:
    """
    Import metadata, optionally saving it.

    Requires admin, librarian, or super-librarian role.
    """
    user = get_current_user()
    if not (user and (user.is_admin() or user.is_librarian() or user.is_super_librarian())):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return _build_preview_response(source, provider, identifier, save=save, request=request)
