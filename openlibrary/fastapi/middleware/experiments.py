from fastapi import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from infogami import config
from openlibrary.core.experiments import get_user_experiments
from openlibrary.fastapi.auth import authenticate_user_from_cookie


class ABTestingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        session_cookie_name = config.get("login_cookie_name", "session")
        session_value = request.cookies.get(session_cookie_name)
        user = authenticate_user_from_cookie(session_value)
        is_logged_in = user is not None

        user_id = session_value or (request.client.host if request.client else "127.0.0.1")

        query_overrides = {k: v for k, v in request.query_params.items() if k.startswith("experiment_")}
        request.state.experiments = get_user_experiments(user_id, overrides=query_overrides, is_logged_in=is_logged_in) if user_id else {}

        await self.app(scope, receive, send)
