from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Form, HTTPException, Response, status
from fastapi.responses import JSONResponse

from infogami.infobase.client import ClientException
from openlibrary import accounts
from openlibrary.core.auth import ExpiredTokenError, HMACToken, MissingKeyError
from openlibrary.utils.request_context import req_context, site, web_ctx_ip

logger = logging.getLogger("openlibrary.fastapi.unlink")

router = APIRouter(tags=["unlink"], include_in_schema=False)

DEFAULT_UNLINK_COMMENT = "Unlink OCAID: Item no longer available"


@router.post("/api/unlink")
def unlink_ia_ol(
    digest: Annotated[str, Form()] = "",
    msg: Annotated[str, Form()] = "",
    comment: Annotated[str, Form()] = "",
) -> Response:
    x_fwd = req_context.get().x_forwarded_for
    client_ip = x_fwd.split(",")[0].strip() if x_fwd else "127.0.0.1"

    try:
        if not HMACToken.verify(digest, msg, "ia_sync_secret", unix_time=True):
            return Response(status_code=status.HTTP_401_UNAUTHORIZED, media_type="application/json")
    except ValueError:
        return Response(status_code=status.HTTP_401_UNAUTHORIZED, media_type="application/json")
    except ExpiredTokenError:
        return Response(status_code=status.HTTP_401_UNAUTHORIZED, media_type="application/json")
    except MissingKeyError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

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


def _make_dark(edition: Any, ocaid: str, comment: str = "") -> None:
    data = edition.dict()
    if "ocaid" in data and data["ocaid"] == ocaid:
        del data["ocaid"]
    source_records = data.get("source_records", [])
    data["source_records"] = [rec for rec in source_records if rec != f"ia:{ocaid}"]
    if not data["source_records"]:
        del data["source_records"]
    with accounts.RunAs("ImportBot"):
        s = site.get()
        s.save(
            data,
            comment or DEFAULT_UNLINK_COMMENT,
            action="edit-edition-ocaid",
        )
