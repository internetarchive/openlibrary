"""
FastAPI account endpoints for authentication.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated
from urllib.parse import unquote, urlencode, urlparse

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from infogami import config
from openlibrary import accounts
from openlibrary.accounts import InternetArchiveAccount, OpenLibraryAccount, RunAs
from openlibrary.accounts.model import audit_accounts, encrypt_s3_keys, generate_login_code_for_user
from openlibrary.core import stats
from openlibrary.core.auth import ExpiredTokenError, HMACToken, MissingKeyError
from openlibrary.core.env import get_ol_env
from openlibrary.core.follows import PubSub
from openlibrary.fastapi.auth import (
    AuthenticatedUser,
    get_authenticated_user,
    require_authenticated_user,
)
from openlibrary.fastapi.utils import set_flash_cookie
from openlibrary.plugins.upstream import account as legacy_account
from openlibrary.plugins.upstream.account import get_login_error
from openlibrary.utils.request_context import site

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
    if parsed.scheme or parsed.netloc or not url.startswith("/") or url.startswith(("//", "/\\")):
        return default
    return url


def _cookie_secure() -> bool:
    # Secure cookies are dropped over plain http (Safari drops them even on
    # localhost), so only set Secure outside local dev. Read per request so
    # tests can override LOCAL_DEV.
    return not get_ol_env().LOCAL_DEV


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
        curl http://localhost:8080/account/test.json \\
            -b "session=/people/openlibrary%2C2026-01-18T17%3A25%3A46%2C7897f%24841a3bd2f8e9a5ca46f505fa557d57bd"

        # Without cookie
        curl http://localhost:8080/account/test.json
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
    """Login form data - matches web.py's web.input defaults.

    All fields default like web.py's `web.input(username="", password="",
    redirect=None, ...)`: in particular username/password are optional so an
    S3-key login (access/secret) can be posted without them, and an empty
    redirect means "no redirect", which falls back to /account/books.
    """

    username: str = ""
    password: str = ""
    remember: bool = False
    redirect: str = ""
    action: str = ""
    access: str | None = None
    secret: str | None = None
    test: bool = False


def _set_login_cookies_on_response(
    response: Response,
    audit: dict,
    ol_username: str,
    email: str = "",
    remember: bool = False,
) -> OpenLibraryAccount | None:
    """Set all session cookies after a successful login.

    Mirrors web.py's _set_login_cookies (session, pd, s3, sfw, yrg_banner).
    Returns the OL account for post-login actions.
    """
    expires = 3600 * 24 * 365 if remember else None

    # Session cookie (same format as web.py's Account.generate_login_code())
    response.set_cookie(
        config.login_cookie_name,
        generate_login_code_for_user(ol_username),
        max_age=expires,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
    )

    # Print disability access flag (empty value deletes the cookie, like web.py)
    response.set_cookie(
        "pd",
        "1" if audit.get("special_access") else "",
        max_age=expires if audit.get("special_access") else 0,
    )

    # Encrypted s3 cookie when IA returned S3 keys (same semantics as legacy)
    if s3_keys := audit.get("s3_keys"):
        token = encrypt_s3_keys(s3_keys["access"], s3_keys["secret"])
        response.set_cookie(
            "s3",
            token,
            max_age=expires,
            httponly=True,
            secure=_cookie_secure(),
            samesite="lax",
        )

    # Safe-mode and yearly-reading-goal banner cookies
    ol_account = OpenLibraryAccount.get_by_email(email) if email else None
    if ol_account and (ol_user := ol_account.get_user()):
        sfw_value = "yes" if ol_user.get_safe_mode() == "yes" else ""
        response.set_cookie("sfw", sfw_value, max_age=expires if sfw_value else 0)
        if pref_key := ol_user.preferences().get("yrg_banner_pref"):
            response.set_cookie(pref_key, "1", max_age=3600 * 24 * 365)

    return ol_account


def _json_login_error(error: str) -> JSONResponse:
    """web.py's account_login_json 400 body: {"error", "errorDisplayString"}."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": error, "errorDisplayString": get_login_error(error)},
    )


async def _login_json(request: Request) -> Response:
    """Mirror web.py's account_login_json for JSON request bodies.

    S3 keys (access/secret) log the user in directly; username/password falls
    back to infogami's own login, exactly like legacy.
    """
    body = await request.json()
    access = body.get("access")
    secret = body.get("secret")
    test = body.get("test", False)

    # Try S3 authentication first, fallback to infogami user/pass
    if access and secret:
        audit = audit_accounts(
            email=None,
            password=None,
            require_link=True,
            s3_access_key=access,
            s3_secret_key=secret,
            test=test,
        )
        if error := audit.get("error"):
            return _json_login_error(error)
        if not (ol_username := audit.get("ol_username")):
            return _json_login_error("undefined_error")
        email = audit.get("ia_email") or audit.get("ol_email")
        response = Response(status_code=status.HTTP_200_OK)
        _set_login_cookies_on_response(response, audit, ol_username, email=email or "")
        return response

    # Fallback to infogami user/pass (same as legacy)
    username = body.get("username", "")
    password = body.get("password", "")
    try:
        site.get().login(username, password)
    except Exception as e:  # noqa: BLE001 - mirror web.py, which 400s on any login failure
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    response = Response(status_code=status.HTTP_200_OK)
    response.set_cookie(
        config.login_cookie_name,
        site.get()._conn.get_auth_token(),
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
    )
    return response


def _perform_post_login_action(response: Response, action: str, ol_account: OpenLibraryAccount | None) -> None:
    """Mirror web.py's perform_post_login_action (follow subscriptions).

    Subscribes the user and queues the confirmation flash on the response.
    Unknown actions are ignored, same as legacy.
    """
    if not action:
        return
    op, _, args = action.partition(":")
    if op != "follow" or not args or not ol_account:
        return
    if publisher_account := OpenLibraryAccount.get_by_username(args):
        PubSub.subscribe(subscriber=ol_account.username, publisher=args)
        publisher_name = publisher_account["data"]["displayname"]
        set_flash_cookie(response, "note", f"You are now following {publisher_name}!")


def _login_error_response(redirect: str, action: str, username: str, message: str) -> Response:
    """Redirect back to the login form with the error shown as a flash banner.

    Mirrors web.py's render_error (form re-shown, inputs preserved, message
    displayed): GET /account/login is still rendered by web.py, which reads
    the flash cookie in the site layout.
    """
    params = {"redirect": redirect, "action": action}
    if username:
        params["username"] = username
    response = Response(
        status_code=status.HTTP_303_SEE_OTHER,
        headers={"Location": f"/account/login?{urlencode(params)}"},
    )
    set_flash_cookie(response, "error", message)
    return response


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

    # A JSON body follows web.py's account_login_json: S3 keys (access/secret)
    # are required for password-less login.
    if (request.headers.get("content-type") or "").lower().startswith("application/json"):
        return await _login_json(request)

    # web.py's web.input() merges query string params with the posted form
    # (the public openlibrary/api.py client logs in via query string).
    q = request.query_params
    username = form_data.username or q.get("username", "")
    password = form_data.password or q.get("password", "")
    remember = form_data.remember or q.get("remember", "").lower() in ("yes", "true", "on", "1")
    redirect = form_data.redirect or q.get("redirect", "")
    action = form_data.action or q.get("action", "")
    access = form_data.access or q.get("access") or request.headers.get("x-s3-access")
    secret = form_data.secret or q.get("secret") or request.headers.get("x-s3-secret")
    test = form_data.test or q.get("test", "").lower() in ("yes", "true", "on", "1")

    # Call the EXACT same audit function that web.py uses
    audit = audit_accounts(
        email="" if (access and secret) else username,
        password=password,
        require_link=True,
        s3_access_key=access,
        s3_secret_key=secret,
        test=test,
    )

    # Authentication errors go back to the login form with a message,
    # mirroring web.py's render_error
    if error := audit.get("error"):
        return _login_error_response(redirect, action, username, get_login_error(error))

    # Extract user info from audit result
    ol_username = audit.get("ol_username")
    if not ol_username:
        return _login_error_response(redirect, action, username, get_login_error("undefined_error"))

    # web.py lands on the account books page whenever the redirect is missing,
    # unsafe, or loops back to an account page.
    blacklist = ["/account/login", "/account/create", "/account/verify"]
    is_valid_redirect = True
    redirect_url = _safe_redirect(redirect, default="")
    if not redirect_url or any(path in redirect_url for path in blacklist):
        is_valid_redirect = False
        redirect_url = "/account/books"

    # Create response with redirect
    response = Response(
        status_code=status.HTTP_303_SEE_OTHER,
        headers={"Location": redirect_url},
    )

    if is_valid_redirect:
        response.delete_cookie("pending_action")

    email = ("" if (access and secret) else username) or audit.get("ia_email") or audit.get("ol_email")

    ol_account = _set_login_cookies_on_response(response, audit, ol_username, email=email, remember=remember)

    # Perform any post-login action (same as web.py's perform_post_login_action)
    _perform_post_login_action(response, action, ol_account)

    # Increment stats (same as web.py)
    stats.increment("ol.account.xauth.login")

    return response


@router.post("/account/logout")
async def logout(request: Request) -> Response:
    """
    Logout endpoint - clears authentication cookies.

    This mirrors the web.py logout functionality.
    """

    # Return to the referring page (same as infogami logout). Browsers send the
    # full URL, so only honor same-origin referrers -- a forged Referer must
    # not bounce patrons offsite (legacy web.py redirects it raw).
    parsed_referer = urlparse(request.headers.get("referer", "/"))
    if parsed_referer.netloc and parsed_referer.netloc != request.headers.get("host", ""):
        location = "/"
    else:
        referer_path = parsed_referer.path or "/"
        if parsed_referer.query:
            referer_path += f"?{parsed_referer.query}"
        location = _safe_redirect(referer_path, default="/")

    response = Response(
        status_code=status.HTTP_303_SEE_OTHER,
        headers={"Location": location},
    )

    # Clear all auth cookies (same as web.py does)
    response.delete_cookie(config.login_cookie_name)
    response.delete_cookie("pd")
    response.delete_cookie(
        "s3",
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
    )
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
