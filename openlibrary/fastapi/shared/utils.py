"""Shared helpers for FastAPI routers."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Literal
from urllib.parse import quote

if TYPE_CHECKING:
    from fastapi import Response

# Flash banner types ever used with add_flash_message / the flash cookie.
FlashType = Literal["error", "note", "success", "info"]


def set_flash_cookie(response: Response, flash_type: FlashType, message: str) -> None:
    """Set a web.py-compatible flash cookie on the response.

    The site layout renders these banners on the next page load, including
    pages rendered by web.py after a cross-stack redirect.

    web.py's flash cookie reader (infogami.utils.flash / web.cookies())
    unconditionally percent-decodes the raw cookie value, symmetric with
    web.setcookie()'s percent-encoding on write. Starlette's default
    cookie quoting instead backslash-escapes values containing commas
    (RFC 2109 style), which web.py's decoder can't reverse -- so the
    flash message would silently vanish unless we percent-encode it
    ourselves here to match web.py's wire format.
    """
    flash_json = json.dumps([{"type": flash_type, "message": str(message)}])
    response.set_cookie("flash", quote(flash_json, safe=""))
