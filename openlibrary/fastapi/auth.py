"""
FastAPI authentication dependencies for reading Open Library session cookies.

This module provides dependencies for authenticating users based on the existing
Open Library session cookie format.
"""

from __future__ import annotations

import logging
from typing import Annotated
from urllib.parse import unquote

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyCookie
from pydantic import BaseModel, Field

from infogami import config
from openlibrary.accounts import get_current_user
from openlibrary.accounts.model import get_secret_key, verify_hash

logger = logging.getLogger(__name__)


class AuthenticatedUser(BaseModel):
    """Model representing an authenticated user."""

    username: str = Field(..., description="The username (without /people/ prefix)")
    user_key: str = Field(..., description="The full user key (e.g., /people/username)")
    timestamp: str = Field(..., description="The timestamp from the cookie")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "username": "openlibrary",
                    "user_key": "/people/openlibrary",
                    "timestamp": "2026-01-18T17:25:46",
                }
            ]
        }
    }


# Define the session cookie as a FastAPI security scheme so it appears
# in the auto-generated OpenAPI/Swagger documentation.
session_cookie = APIKeyCookie(
    name=config.get("login_cookie_name", "session"),
    auto_error=False,
)


def authenticate_user_from_cookie(cookie_value: str | None) -> AuthenticatedUser | None:
    """Authenticate a user from a session cookie.

    Args:
        cookie_value: The raw cookie value (URL-encoded), or None

    Returns:
        AuthenticatedUser if cookie is valid, None otherwise
    """
    if not cookie_value:
        return None

    try:
        decoded = unquote(cookie_value)

        # Split into parts: /people/username,timestamp,salt$hash
        parts = decoded.split(",")

        if len(parts) != 3:
            return None

        user_key, timestamp, hash_value = parts

        # Verify the hash
        text_to_hash = f"{user_key},{timestamp}"
        secret_key = get_secret_key()

        if not verify_hash(secret_key, text_to_hash, hash_value):
            return None

        # Extract username from user_key
        if not user_key.startswith("/people/"):
            return None

        username = user_key[len("/people/") :]

        return AuthenticatedUser(
            username=username,
            user_key=user_key,
            timestamp=timestamp,
        )

    except ValueError as e:
        logger.error(f"Error decoding cookie: {e}")
        return None


async def get_authenticated_user(
    session: Annotated[str | None, Depends(session_cookie)],
) -> AuthenticatedUser | None:
    """FastAPI dependency to get the authenticated user from the session cookie.

    This function can be used as a dependency in FastAPI routes:

    @app.get("/protected")
    async def protected_route(
        user: Annotated[AuthenticatedUser | None, Depends(get_authenticated_user)],
    ):
        if user:
            return {"message": f"Hello {user.username}!"}
        else:
            raise HTTPException(status_code=401, detail="Not authenticated")
    """
    return authenticate_user_from_cookie(session)


async def require_authenticated_user(
    user: Annotated[AuthenticatedUser | None, Depends(get_authenticated_user)],
) -> AuthenticatedUser:
    """FastAPI dependency that requires authentication.

    Use this when you want to ensure a user is authenticated, returning 401 if not.

    @app.get("/protected")
    async def protected_route(
        user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    ):
        return {"message": f"Hello {user.username}!"}
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Session"},
        )

    return user


async def require_librarian(
    _: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> AuthenticatedUser:
    """FastAPI dependency that requires librarian-level access.

    Checks that the authenticated user has admin, librarian, or super-librarian role.
    Returns 403 if the user lacks sufficient permissions.

    Usage:
        @router.get("/protected")
        async def protected_route(
            _: Annotated[AuthenticatedUser, Depends(require_librarian)],
        ):
            return {"message": "You have librarian access!"}
    """
    user = get_current_user()
    if not (user and user.is_librarian_or_higher()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    return _


async def require_api_permissions(
    _: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> AuthenticatedUser:
    """FastAPI dependency matching web.py's ``can_write()`` check.

    Mirrors ``openlibrary.plugins.openlibrary.code.can_write`` which allows:
    - Members of ``/usergroup/admin`` (admins)
    - Members of ``/usergroup/api``
    - Bot-flagged accounts (accounts with ``bot=true`` in the store)

    This is intentionally broader than ``require_librarian`` — legacy API
    integrations and automated tooling rely on the ``/usergroup/api`` and
    bot-flag paths.  Returns 403 if the user lacks sufficient permissions.
    """
    user = get_current_user()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    # Check the three conditions from web.py's can_write()
    can_write = bool(user.is_admin() or user.is_usergroup_member("/usergroup/api") or (user.get_account() and user.get_account().get("bot") in ("true", True)))

    if not can_write:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    return _


LibrarianDep = Annotated[AuthenticatedUser, Depends(require_librarian)]
ApiPermissionsDep = Annotated[AuthenticatedUser, Depends(require_api_permissions)]
