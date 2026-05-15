"""
FastAPI endpoints for import preview.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, status

from openlibrary.accounts import get_current_user
from openlibrary.plugins.importapi.import_ui import ImportPreviewRequest

router = APIRouter(tags=["import"])


def check_import_permission() -> None:
    """Check that the current user has admin/librarian/super-librarian role."""
    user = get_current_user()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    if not (user.is_admin() or user.is_librarian() or user.is_super_librarian()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )


def _build_preview_response(
    source: str | None,
    provider: str | None,
    identifier: str | None,
    save: bool,
) -> dict:
    """Shared logic for GET and POST import preview handlers."""
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

    return dict(req.metadata_provider.do_import(req.identifier, req.save))


@router.get("/import/preview.json")
def import_preview_json_get(
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
    _: Annotated[None, Depends(check_import_permission)] = None,
) -> dict:
    """
    Preview import metadata without saving.

    Requires admin, librarian, or super-librarian role.
    """
    return _build_preview_response(source, provider, identifier, save=False)


@router.post("/import/preview.json")
def import_preview_json_post(
    source: Annotated[str | None, Form()] = None,
    provider: Annotated[str | None, Form()] = None,
    identifier: Annotated[str | None, Form()] = None,
    save: Annotated[bool, Form()] = False,
    _: Annotated[None, Depends(check_import_permission)] = None,
) -> dict:
    """
    Import metadata, optionally saving it.

    Requires admin, librarian, or super-librarian role.
    """
    return _build_preview_response(source, provider, identifier, save=save)
