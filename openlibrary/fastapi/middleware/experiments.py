from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from infogami import config
from openlibrary.core.experiments import get_user_experiments


class ABTestingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Adjust logic to match Open Library's FastAPI authentication method - NOT a perfect match.
        user_id = request.cookies.get(config.get("login_cookie_name", "session")) or (request.client.host if request.client else "127.0.0.1")

        request.state.experiments = get_user_experiments(user_id) if user_id else {}

        return await call_next(request)
