"""
FastAPI endpoints for import preview.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, Query

from openlibrary.fastapi.auth import LibrarianDep  # noqa: TC001
from openlibrary.plugins.importapi.import_ui import ImportPreviewRequest
from openlibrary.utils.request_context import req_context, web_ctx_ip

router = APIRouter(tags=["import"])


def _build_preview_response(
    source: str | None,
    provider: str | None,
    identifier: str | None,
    save: bool,
    client_ip: str,
) -> dict:
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

    with web_ctx_ip(client_ip):
        return dict(req.metadata_provider.do_import(req.identifier, req.save))


@router.get("/import/preview.json")
def import_preview_json_get(
    _: LibrarianDep,
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
    x_fwd = req_context.get().x_forwarded_for
    client_ip = x_fwd.split(",")[0].strip() if x_fwd else "127.0.0.1"
    return _build_preview_response(source, provider, identifier, save=False, client_ip=client_ip)


@router.post("/import/preview.json")
def import_preview_json_post(
    _: LibrarianDep,
    source: Annotated[str | None, Form()] = None,
    provider: Annotated[str | None, Form()] = None,
    identifier: Annotated[str | None, Form()] = None,
    save: Annotated[bool, Form()] = False,
) -> dict:
    """
    Import metadata, optionally saving it.

    Requires admin, librarian, or super-librarian role.
    """
    x_fwd = req_context.get().x_forwarded_for
    client_ip = x_fwd.split(",")[0].strip() if x_fwd else "127.0.0.1"
    return _build_preview_response(source, provider, identifier, save=save, client_ip=client_ip)
