from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from infogami import config
from openlibrary.core.experiments import get_user_experiments
from openlibrary.fastapi.auth import authenticate_user_from_cookie


class ABTestingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Adjust logic to match Open Library's FastAPI authentication method
        session_cookie_name = config.get("login_cookie_name", "session")
        session_value = request.cookies.get(session_cookie_name)
        user = authenticate_user_from_cookie(session_value)
        is_logged_in = user is not None

        user_id = session_value or (request.client.host if request.client else "127.0.0.1")

        query_overrides = dict(request.query_params)
        request.state.experiments = get_user_experiments(user_id, overrides=query_overrides, is_logged_in=is_logged_in) if user_id else {}

        return await call_next(request)
