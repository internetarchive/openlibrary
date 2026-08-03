"""
FastAPI account endpoints for authentication.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated
from urllib.parse import unquote, urlparse

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from infogami import config
from openlibrary import accounts
from openlibrary.accounts import InternetArchiveAccount, OpenLibraryAccount, RunAs
from openlibrary.accounts.model import audit_accounts, generate_login_code_for_user
from openlibrary.core import stats
from openlibrary.core.auth import ExpiredTokenError, HMACToken, MissingKeyError
from openlibrary.fastapi.auth import (
    AuthenticatedUser,
    get_authenticated_user,
    require_authenticated_user,
)
from openlibrary.plugins.upstream import account as legacy_account
from openlibrary.plugins.upstream.account import get_login_error

logger = logging.getLogger("openlibrary.fastapi.account")

router = APIRouter()

SHOW_INTERNAL_IN_SCHEMA = os.getenv("LOCAL_DEV") is not None

# Allow overriding ia_sync_secret via env var (for dev/test environments).
# Legacy production config sets this value outside the repo.
_ia_sync_secret = os.getenv("IA_SYNC_SECRET")
if _ia_sync_secret:
    config.ia_sync_secret = _ia_sync_secret  # type: ignore[attr-defined]


class AnonymizeResponse(BaseModel):
    new_username: str = Field(description="The new anonymous username assigned to the patron")
    booknotes_count: int = Field(description="Number of booknotes deleted")
    ratings_count: int = Field(description="Number of ratings anonymized")
    observations_count: int = Field(description="Number of observations anonymized")
    bookshelves_count: int = Field(description="Number of bookshelf entries anonymized")
    merge_request_count: int = Field(description="Number of merge requests updated")
    bestbooks_count: int = Field(description="Number of bestbook entries anonymized")


def _safe_redirect(url: str, default: str = "/") -> str:
    """Return url only if it is a same-origin path; fall back to default."""
    parsed = urlparse(url)
    if parsed.scheme or parsed.netloc or not url.startswith("/") or url.startswith("//"):
        return default
    return url


class AccountLoansResponse(BaseModel):
    """Response model for /account/loans.json."""

    loans: list[dict] = Field(
        ...,
        description="List of the user's current loans, each containing ocaid, book, resource_type, expiry, etc.",
    )


class AccountLoanHistoryResponse(BaseModel):
    """Response model for /account/loan-history.json."""

    loans_history: dict = Field(
        ...,
        description="Loan history data containing 'docs' (list of loan records), 'show_next' (bool), 'limit' (int), and 'page' (int).",
    )


class AuthTestResponse(BaseModel):
    """Response model for the auth test endpoint."""

    username: str | None = Field(None, description="The username if authenticated")
    user_key: str | None = Field(None, description="The full user key if authenticated")
    timestamp: str | None = Field(None, description="The cookie timestamp if authenticated")
    is_authenticated: bool = Field(..., description="Whether the user is authenticated")
    error: str | None = Field(None, description="Error message if authentication failed")
    cookie_name: str = Field(..., description="The name of the session cookie")
    cookie_value: str | None = Field(None, description="The raw cookie value (for debugging)")
    cookie_parsed: dict = Field(..., description="Parsed cookie components")


@router.get("/account/test.json", response_model=AuthTestResponse, tags=["internal"], include_in_schema=SHOW_INTERNAL_IN_SCHEMA)
async def check_authentication(
    request: Request,
    user: Annotated[AuthenticatedUser | None, Depends(get_authenticated_user)],
) -> AuthTestResponse:
    """
    Check endpoint to verify authentication is working correctly.

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
            cookie_parsed["hash"] = parts[2][:20] + "..." if len(parts[2]) > 20 else parts[2]

    return AuthTestResponse(
        username=user.username if user else None,
        user_key=user.user_key if user else None,
        timestamp=user.timestamp if user else None,
        is_authenticated=user is not None,
        error=None,
        cookie_name=cookie_name,
        cookie_value=(cookie_value[:50] + "..." if cookie_value and len(cookie_value) > 50 else cookie_value),
        cookie_parsed=cookie_parsed,
    )


@router.get("/account/protected.json", tags=["internal"], include_in_schema=SHOW_INTERNAL_IN_SCHEMA)
async def protected_endpoint(
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
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


@router.get("/account/optional.json", tags=["internal"], include_in_schema=SHOW_INTERNAL_IN_SCHEMA)
async def optional_auth_endpoint(
    user: Annotated[AuthenticatedUser | None, Depends(get_authenticated_user)],
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


@router.get("/account/loans.json", response_model=AccountLoansResponse)
def account_loans_json(
    _: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> dict:
    try:
        return legacy_account.get_account_loans_json(accounts.get_current_user())
    except Exception:
        if os.getenv("LOCAL_DEV"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Loan data requires credentials for the production Internet Archive server and is not available in the local development environment.",
            )
        raise


@router.get("/account/loan-history.json", response_model=AccountLoanHistoryResponse)
def account_loan_history_json(
    _: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    page: Annotated[int, Query(ge=1)] = 1,
) -> dict:
    try:
        return legacy_account.get_account_loan_history_json(accounts.get_current_user(), page)
    except Exception:
        if os.getenv("LOCAL_DEV"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Loan history requires credentials for the production Internet Archive server and is not available in the local development environment.",
            )
        raise


class LoginForm(BaseModel):
    """Login form data - matches web.py forms.Login"""

    username: str
    password: str
    remember: bool = False
    redirect: str = "/"
    action: str = ""


@router.post("/account/login")
async def login(
    request: Request,
    form_data: Annotated[LoginForm, Form()],
) -> Response:
    """
    Login endpoint - works identically to web.py version.

    This endpoint:
    1. Validates email/password against Internet Archive
    2. Creates/links OpenLibrary account if needed
    3. Sets session cookie and other cookies
    4. Redirects to target page

    This reuses all existing authentication logic from the legacy system.
    """

    # Call the EXACT same audit function that web.py uses
    audit = audit_accounts(
        email=form_data.username,
        password=form_data.password,
        require_link=True,
        s3_access_key=None,
        s3_secret_key=None,
        test=False,
    )

    # Check for authentication errors
    if error := audit.get("error"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=get_login_error(error),
        )

    # Extract user info from audit result
    ol_username = audit.get("ol_username")
    if not ol_username:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login succeeded but no username found",
        )

    # Determine cookie expiration
    expires = 3600 * 24 * 365 if form_data.remember else None

    # Generate auth token (same way web.py does it via Account.generate_login_code())
    login_code = generate_login_code_for_user(ol_username)

    blacklist = [
        "/account/login",
        "/account/create",
        "/account/verify",
    ]
    is_valid_redirect = True
    redirect_url = _safe_redirect(form_data.redirect, default="")
    if not redirect_url or any(path in redirect_url for path in blacklist):
        is_valid_redirect = False
        redirect_url = "/"

    # Create response with redirect
    response = Response(
        status_code=status.HTTP_303_SEE_OTHER,
        headers={"Location": redirect_url},
    )

    if is_valid_redirect:
        response.delete_cookie("pending_action")

    # Set session cookie (same as web.py)
    response.set_cookie(
        config.login_cookie_name,
        login_code,
        max_age=expires,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
    )

    # Set print disability flag if user has special access
    response.set_cookie(
        "pd",
        str(int(audit.get("special_access", 0))) if audit.get("special_access") else "",
        max_age=expires,
    )

    # Increment stats (same as web.py)
    stats.increment("ol.account.xauth.login")

    return response


@router.post("/account/logout")
async def logout(request: Request) -> Response:
    """
    Logout endpoint - clears authentication cookies.

    This mirrors the web.py logout functionality.
    """

    response = Response(
        status_code=status.HTTP_303_SEE_OTHER,
        headers={"Location": "/"},
    )

    # Clear all auth cookies (same as web.py does)
    response.delete_cookie(config.login_cookie_name)
    response.delete_cookie("pd")
    response.delete_cookie("sfw")

    return response


@router.post(
    "/account/anonymize.json",
    response_model=AnonymizeResponse,
    tags=["internal"],
    include_in_schema=SHOW_INTERNAL_IN_SCHEMA,
)
async def anonymize_account(
    request: Request,
    test: Annotated[str, Form()] = "false",
    digest: Annotated[str, Form()] = "",
    msg: Annotated[str, Form()] = "",
) -> AnonymizeResponse:
    test_mode = test == "true"

    try:
        if not HMACToken.verify(digest, msg, "ia_sync_secret", delimiter=":", unix_time=True):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bad Request")
    except ExpiredTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    except MissingKeyError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Service Unavailable")

    auth_header = request.headers.get("authorization", "")
    try:
        _, keys = auth_header.split("LOW ", 1)
        s3_access, s3_secret = keys.split(":", 1)
        s3_access = s3_access.strip()
        s3_secret = s3_secret.strip()
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed Authorization Header")

    xauthn_response = InternetArchiveAccount.s3auth(s3_access, s3_secret)
    if "error" in xauthn_response:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    ol_account = OpenLibraryAccount.get_by_link(xauthn_response.get("itemname", ""))
    if not ol_account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    try:
        # RunAs sets the auth token on the connection (via site ContextVar)
        # so that anonymize() can write to infobase as the target user.
        # This endpoint authenticates via HMAC+S3, not a user session, so
        # there is no auth token on the connection without RunAs.
        with RunAs(ol_account.username):
            result = ol_account.anonymize(test=test_mode)
    except Exception as e:  # noqa: BLE001
        logger.error(e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal Server Error")

    return AnonymizeResponse(**result)
