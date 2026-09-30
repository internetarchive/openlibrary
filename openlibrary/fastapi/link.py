"""FastAPI endpoints for the archive.org OCAID sync API.

/api/link and /api/unlink are called by archive.org (e.g. ImportBot) and
authenticated with an HMAC digest signed with the shared ``ia_sync_secret``.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Response, status
from fastapi.responses import JSONResponse

from infogami.infobase.client import ClientException
from openlibrary import accounts
from openlibrary.core.auth import ExpiredTokenError, HMACToken, MissingKeyError
from openlibrary.fastapi.shared.dependencies import ClientIpDep  # noqa: TC001
from openlibrary.utils.request_context import site, web_ctx_ip

logger = logging.getLogger("openlibrary.fastapi.link")

router = APIRouter(tags=["link"], include_in_schema=False)


def verify_ia_sync_msg(
    digest: Annotated[str, Form()] = "",
    msg: Annotated[str, Form()] = "",
) -> str:
    """Verify the HMAC digest protecting the ia sync endpoints.

    Returns the verified ``msg`` so callers can parse it.

    Raises:
        HTTPException: 401 if the digest is missing, invalid, or expired;
            503 if the ia_sync_secret is not configured.
    """
    try:
        if not HMACToken.verify(digest, msg, "ia_sync_secret", unix_time=True):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    except ValueError, ExpiredTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    except MissingKeyError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    return msg


IaSyncMsgDep = Annotated[str, Depends(verify_ia_sync_msg)]

DEFAULT_UNLINK_COMMENT = "Unlink OCAID: Item no longer available"


@router.post("/api/link")
def link_ia_ol(
    msg: IaSyncMsgDep,
    client_ip: ClientIpDep,
) -> dict[str, Any]:
    parts = msg.split("|", maxsplit=2)
    if len(parts) != 3 or not all(parts):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid inputs",
        )
    ocaid, olid, _ts = parts

    edition = site.get().get(f"/books/{olid}")
    if not edition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    try:
        with web_ctx_ip(client_ip):
            _link(edition, ocaid)
    except ClientException as e:
        logger.error(f"Failed to associate {ocaid} with {olid}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )

    return {"status": "ok"}


@router.post("/api/unlink")
def unlink_ia_ol(
    msg: IaSyncMsgDep,
    client_ip: ClientIpDep,
    comment: Annotated[str, Form()] = "",
) -> Response:
    parts = msg.split("|", maxsplit=1)
    if len(parts) != 2 or not all(parts):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Invalid inputs"},
        )
    ocaid, _ts = parts

    s = site.get()
    edition_keys = s.things({"type": "/type/edition", "ocaid": ocaid})
    edition_keys.extend(s.things({"type": "/type/edition", "source_records": f"ia:{ocaid}"}))
    edition_keys = list(set(edition_keys))
    if not edition_keys:
        return Response(status_code=status.HTTP_404_NOT_FOUND, media_type="application/json")

    editions = s.get_many(edition_keys)
    logger.info(f"Disassociating {ocaid} from the following editions: {', '.join(edition_keys)}")

    with web_ctx_ip(client_ip):
        for edition in editions:
            try:
                _make_dark(edition, ocaid, comment)
            except ClientException as e:
                logger.error(f"Failed to disassociate record with key {edition.key}", exc_info=True)
                return JSONResponse(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content={"error": str(e)},
                )

    return JSONResponse(content={"status": "ok"})


def _link(edition: Any, ocaid: str) -> None:
    data = edition.dict()
    data["ocaid"] = ocaid
    save_edition_as_importbot(data, "Associate OCAID with record")


def _make_dark(edition: Any, ocaid: str, comment: str = "") -> None:
    data = edition.dict()
    if "ocaid" in data and data["ocaid"] == ocaid:
        del data["ocaid"]
    source_records = data.get("source_records", [])
    data["source_records"] = [rec for rec in source_records if rec != f"ia:{ocaid}"]
    if not data["source_records"]:
        del data["source_records"]
    save_edition_as_importbot(data, comment or DEFAULT_UNLINK_COMMENT)


def save_edition_as_importbot(data: dict[str, Any], comment: str) -> None:
    """Save edition data as the ImportBot account, credited to the edit-edition-ocaid action."""
    with accounts.RunAs("ImportBot"):
        site.get().save(data, comment, action="edit-edition-ocaid")
