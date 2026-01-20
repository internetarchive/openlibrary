"""
FastAPI authentication middleware for reading Open Library session cookies.

This module provides middleware and dependencies for authenticating users
based on the existing Open Library session cookie format.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import logging
import time
from typing import TYPE_CHECKING, Annotated
from urllib.parse import unquote

from fastapi import Cookie, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from infogami import config
from openlibrary.accounts.model import generate_hash, get_secret_key

if TYPE_CHECKING:
    from fastapi import FastAPI

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


def get_secret_key() -> str:
    """Get the secret key from config for verifying cookies.

    Returns:
        The secret key as a string.
    """
    key = config.get("infobase", {}).get("secret_key", "")
    if not key:
        # Fallback for development/testing
        logger.warning("No secret_key configured in infobase config")
        return "dev_secret_key_do_not_use_in_production"
    return key


def verify_hash(secret_key: str, text: str, hash_value: str) -> bool:
    """Verify if the hash is valid.

    Args:
        secret_key: The secret key for HMAC
        text: The text to verify
        hash_value: The hash to verify against (format: salt$hash)

    Returns:
        True if hash is valid, False otherwise
    """
    try:
        salt = hash_value.split("$", 1)[0]
        key_bytes = secret_key.encode("utf-8")

        computed_hash = hmac.HMAC(
            key_bytes, (salt + text).encode("utf-8"), hashlib.md5
        ).hexdigest()

        # Compare with provided hash
        expected_hash = hash_value.split("$", 1)[1] if "$" in hash_value else hash_value
        return hmac.compare_digest(computed_hash, expected_hash)
    except (ValueError, IndexError) as e:
        logger.error(f"Error verifying hash: {e}")
        return False


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
        # URL decode the cookie
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

        # Return AuthenticatedUser directly
        return AuthenticatedUser(
            username=username,
            user_key=user_key,
            timestamp=timestamp,
        )

    except ValueError as e:
        logger.error(f"Error decoding cookie: {e}")
        return None


async def get_authenticated_user(
    request: Request,
    session: str | None = Cookie(
        None, alias=config.get("login_cookie_name", "session")
    ),
) -> AuthenticatedUser | None:
    """FastAPI dependency to get the authenticated user from the session cookie.

    This function can be used as a dependency in FastAPI endpoints:

        @app.get("/protected")
        async def protected_route(user: AuthenticatedUser | None = Depends(get_authenticated_user)):
            if user:
                return {"message": f"Hello {user.username}!"}
            else:
                raise HTTPException(status_code=401, detail="Not authenticated")

    Args:
        request: The FastAPI request object
        session: The session cookie value

    Returns:
        AuthenticatedUser if valid cookie, None otherwise
    """
    return authenticate_user_from_cookie(session)


async def require_authenticated_user(
    user: Annotated[AuthenticatedUser | None, Depends(get_authenticated_user)],
) -> AuthenticatedUser:
    """FastAPI dependency that requires authentication.

    Use this when you want to ensure a user is authenticated, returning 401 if not.

        @app.get("/protected")
        async def protected_route(user: AuthenticatedUser = Depends(require_authenticated_user)):
            return {"message": f"Hello {user.username}!"}

    Args:
        user: The user from get_authenticated_user dependency

    Returns:
        AuthenticatedUser if authenticated

    Raises:
        HTTPException: If user is not authenticated
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Session"},
        )

    return user


def generate_login_code_for_user(username: str) -> str:
    """
    Generate auth token for a user for FastAPI.

    This extracts the logic from Account.generate_login_code()
    into a standalone function that doesn't need web.ctx.

    Args:
        username: The username to generate a login code for

    Returns:
        A string in the format: "/people/{username},{timestamp},{salt}${hash}"
        that can be used as a session cookie value
    """

    user_key = "/people/" + username
    t = datetime.datetime(*time.gmtime()[:6]).isoformat()
    text = f"{user_key},{t}"
    return text + "," + generate_hash(get_secret_key(), text)


def add_authentication_middleware(app: FastAPI) -> None:
    """
    Add authentication middleware to the FastAPI app.

    This middleware adds the authenticated user to request.state.user
    for easy access in endpoints without using dependencies.

    Args:
        app: The FastAPI application instance
    """

    @app.middleware("http")
    async def authentication_middleware(request: Request, call_next):
        """Middleware to decode session cookie and add user to request state."""
        cookie_name = config.get("login_cookie_name", "session")
        session_cookie = request.cookies.get(cookie_name)

        request.state.user = authenticate_user_from_cookie(session_cookie)

        response = await call_next(request)
        return response
