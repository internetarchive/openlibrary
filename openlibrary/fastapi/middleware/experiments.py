from fastapi import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from infogami import config
from openlibrary.accounts.model import verify_session_cookie
from openlibrary.core.experiments import get_user_experiments


class ABTestingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)

        session_value = request.cookies.get(config.get("login_cookie_name", "session"))
        is_authenticated = False
        user_id = None

        if session_value and session_value.startswith("/people/") and verify_session_cookie(session_value):
            is_authenticated = True
            user_id = session_value.split(",")[0]

        if not user_id:
            forwarded_for = request.headers.get("X-Forwarded-For")
            if forwarded_for:
                user_id = forwarded_for.split(",")[0].strip()
            else:
                user_id = request.client.host if request.client else "127.0.0.1"

        query_overrides = {k: v for k, v in request.query_params.items() if k.startswith("experiment_")}

        request.state.experiments = get_user_experiments(user_id, overrides=query_overrides, is_logged_in=is_authenticated)

        await self.app(scope, receive, send)
