from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from starlette.datastructures import MutableHeaders

from openlibrary.utils import server_timing

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("openlibrary.server_timing")


class ServerTimingMiddleware:
    """Adds a ``Server-Timing`` header. Pure ASGI so streamed responses aren't buffered;
    for those, ``total`` is the time to first byte."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        timings, token = server_timing.start_request()

        async def send_with_timing(message: Message) -> None:
            if message["type"] == "http.response.start":
                try:
                    MutableHeaders(scope=message).append("Server-Timing", server_timing.format_header(timings))
                except Exception:
                    logger.exception("Failed to add Server-Timing header")
            await send(message)

        try:
            await self.app(scope, receive, send_with_timing)
        finally:
            server_timing.end_request(token)
