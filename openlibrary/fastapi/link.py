from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Form, HTTPException, status

from infogami.infobase.client import ClientException
from openlibrary import accounts
from openlibrary.core.auth import ExpiredTokenError, HMACToken, MissingKeyError
from openlibrary.utils.request_context import req_context, site, web_ctx_ip

logger = logging.getLogger("openlibrary.fastapi.link")

router = APIRouter(tags=["link"], include_in_schema=False)


@router.post("/api/link")
def link_ia_ol(
    digest: Annotated[str, Form()] = "",
    msg: Annotated[str, Form()] = "",
) -> dict[str, Any]:
    x_fwd = req_context.get().x_forwarded_for
    client_ip = x_fwd.split(",")[0].strip() if x_fwd else "127.0.0.1"

    try:
        if not HMACToken.verify(digest, msg, "ia_sync_secret", unix_time=True):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    except ValueError, ExpiredTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    except MissingKeyError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

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


def _link(edition, ocaid):
    data = edition.dict()
    data["ocaid"] = ocaid
    with accounts.RunAs("ImportBot"):
        s = site.get()
        s.save(data, "Associate OCAID with record", action="edit-edition-ocaid")
