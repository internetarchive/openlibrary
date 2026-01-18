"""
FastAPI account endpoints for testing authentication.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from openlibrary.fastapi.auth import (
    AuthenticatedUser,
    get_authenticated_user,
    require_authenticated_user,
)

router = APIRouter()


class AuthTestResponse(BaseModel):
    """Response model for the auth test endpoint."""

    username: str | None = Field(None, description="The username if authenticated")
    user_key: str | None = Field(None, description="The full user key if authenticated")
    timestamp: str | None = Field(
        None, description="The cookie timestamp if authenticated"
    )
    is_authenticated: bool = Field(..., description="Whether the user is authenticated")
    error: str | None = Field(
        None, description="Error message if authentication failed"
    )
    cookie_name: str = Field(..., description="The name of the session cookie")
    cookie_value: str | None = Field(
        None, description="The raw cookie value (for debugging)"
    )
    cookie_parsed: dict = Field(..., description="Parsed cookie components")


@router.get("/account/test.json", response_model=AuthTestResponse)
async def test_authentication(
    request: Request,
    user: AuthenticatedUser | None = Depends(get_authenticated_user),
) -> AuthTestResponse:
    """
    Test endpoint to verify authentication is working correctly.

    This endpoint reads the session cookie, decodes it, and returns information
    about the authenticated user. It's useful for testing the authentication
    middleware without requiring a full login flow.

    Returns:
        AuthTestResponse: Information about the authentication status

    Example:
        # With valid session cookie
        curl http://localhost:18080/account/test.json \\
            -b "session=/people/openlibrary%2C2026-01-18T17%3A25%3A46%2C7897f%24841a3bd2f8e9a5ca46f505fa557d57bd"

        # Without cookie
        curl http://localhost:18080/account/test.json
    """
    from urllib.parse import unquote

    from infogami import config

    cookie_name = config.get("login_cookie_name", "session")
    cookie_value = request.cookies.get(cookie_name)

    # Parse the cookie for debugging
    cookie_parsed = {}
    if cookie_value:
        decoded = unquote(cookie_value)
        parts = decoded.split(",")
        cookie_parsed = {
            "raw_decoded": decoded,
            "parts": parts,
            "num_parts": len(parts),
        }
        if len(parts) == 3:
            cookie_parsed["user_key"] = parts[0]
            cookie_parsed["timestamp"] = parts[1]
            cookie_parsed["hash"] = (
                parts[2][:20] + "..." if len(parts[2]) > 20 else parts[2]
            )

    return AuthTestResponse(
        username=user.username if user else None,
        user_key=user.user_key if user else None,
        timestamp=user.timestamp if user else None,
        is_authenticated=user is not None,
        cookie_name=cookie_name,
        cookie_value=(
            cookie_value[:50] + "..."
            if cookie_value and len(cookie_value) > 50
            else cookie_value
        ),
        cookie_parsed=cookie_parsed,
    )


@router.get("/account/protected.json")
async def protected_endpoint(
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> dict:
    """
    Example of a protected endpoint that requires authentication.

    This endpoint will return 401 Unauthorized if the user is not authenticated.

    Returns:
        dict: Success message with user information

    Raises:
        HTTPException: 401 if not authenticated
    """
    return {
        "message": f"Hello {user.username}!",
        "user_key": user.user_key,
        "timestamp": user.timestamp,
    }


@router.get("/account/optional.json")
async def optional_auth_endpoint(
    user: AuthenticatedUser | None = Depends(get_authenticated_user),
) -> dict:
    """
    Example of an endpoint with optional authentication.

    This endpoint works for both authenticated and unauthenticated users,
    returning different information based on auth status.

    Returns:
        dict: Response with user info or anonymous message
    """
    if user:
        return {
            "message": f"Welcome back, {user.username}!",
            "user_key": user.user_key,
            "timestamp": user.timestamp,
            "is_authenticated": True,
        }
    else:
        return {
            "message": "Hello, anonymous user!",
            "is_authenticated": False,
        }
