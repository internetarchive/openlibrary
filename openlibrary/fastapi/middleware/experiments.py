from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request

from infogami import config
from openlibrary.core.experiments import evaluate_experiments_for_request

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send


class ABTestingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)

        session_value = request.cookies.get(config.get("login_cookie_name", "session"))
        forwarded_for = request.headers.get("X-Forwarded-For")
        client_ip = request.client.host if request.client else "127.0.0.1"
        query_params = dict(request.query_params)

        request.state.experiments = evaluate_experiments_for_request(
            session_value=session_value,
            forwarded_for=forwarded_for,
            client_ip=client_ip,
            query_params=query_params,
        )

        await self.app(scope, receive, send)
