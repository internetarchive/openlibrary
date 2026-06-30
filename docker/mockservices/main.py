"""
Mock services for Open Library local development.

Replaces the web.py inline stubs from account.py (/internal/fake/*) and
provides mocks for external services that do not have dev interceptors:
  - IA xauthn  (was /internal/fake/xauth)
  - IA S3 auth (was /internal/fake/s3auth)
  - IA loans   (was /internal/fake/loans)
  - IA availability v2 (was not mocked — pointed at real archive.org)
  - IA borrow status (was hardcoded in lending.py)
  - reCAPTCHA siteverify
  - be-api full-text search
  - Amazon PA-API (stub)

Configure openlibrary.yml to point at this service:
  ia_xauth_api_url:          http://mockservices:8090/services/xauthn/
  ia_s3_auth_url:            http://mockservices:8090/services/s3auth/
  ia_loan_api_url:           http://mockservices:8090/services/loans/loan/
  ia_availability_api_v2_url: http://mockservices:8090/services/availability/
  ia_borrow_status_url:      http://mockservices:8090/services/borrow/
  recaptcha_url:             http://mockservices:8090/recaptcha/api/siteverify
  (plugin_inside) search_endpoint: http://mockservices:8090/fts/v1/search

Email: configure smtp_server=mockservices, smtp_port=1025, dummy_sendmail=False
       Inspect captured mail via mailpit: http://localhost:8025
"""

import logging
from typing import Annotated

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

app = FastAPI(title="OL Mock Services", docs_url="/mock/docs")

# ---------------------------------------------------------------------------
# IA xauthn  (was /internal/fake/xauth in account.py)
# POST /services/xauthn/
#
# Supported ops: authenticate, info, issue_otp, redeem_otp, create
# Dev credentials: email=test@example.com, password=test (or any non-empty)
# Dev S3 keys:     access=foo, secret=foo
# Dev OTP code:    123456
# ---------------------------------------------------------------------------

_DEV_S3 = {"s3": {"access": "foo", "secret": "foo"}, "version": "1"}
_DEV_SCREENNAME = "testuser"
_DEV_EMAIL = "test@example.com"


@app.post("/services/xauthn/")
async def xauth(request: Request) -> JSONResponse:
    body = await request.form()
    op = body.get("op", "")

    if op == "authenticate":
        return JSONResponse(
            {
                "status": "ok",
                "values": {
                    **_DEV_S3,
                    "email": _DEV_EMAIL,
                    "screenname": _DEV_SCREENNAME,
                    "itemname": "@" + _DEV_SCREENNAME,
                    "verified": True,
                    "locked": False,
                },
            }
        )

    if op == "info":
        return JSONResponse(
            {
                "status": "ok",
                "values": {
                    **_DEV_S3,
                    "email": _DEV_EMAIL,
                    "screenname": _DEV_SCREENNAME,
                    "itemname": "@" + _DEV_SCREENNAME,
                    "verified": True,
                    "locked": False,
                },
            }
        )

    if op == "issue_otp":
        return JSONResponse({"status": "ok", "values": {}})

    if op == "redeem_otp":
        otp = body.get("otp", "")
        if otp == "123456":
            return JSONResponse(
                {
                    "status": "ok",
                    "values": {
                        **_DEV_S3,
                        "email": _DEV_EMAIL,
                        "screenname": _DEV_SCREENNAME,
                    },
                }
            )
        return JSONResponse({"status": "error", "values": {"reason": "Invalid OTP"}}, status_code=401)

    if op == "create":
        email = str(body.get("email") or _DEV_EMAIL)
        screenname = str(body.get("screenname") or _DEV_SCREENNAME)
        return JSONResponse(
            {
                "status": "ok",
                "values": {
                    **_DEV_S3,
                    "email": email,
                    "screenname": screenname,
                    "itemname": "@" + screenname,
                    "verified": False,
                    "locked": False,
                },
            }
        )

    logger.warning("xauthn: unhandled op=%s", op)
    return JSONResponse({"status": "error", "values": {"reason": f"Unknown op: {op}"}}, status_code=400)


# ---------------------------------------------------------------------------
# IA S3 auth  (was /internal/fake/s3auth in account.py)
# GET /services/s3auth/
#
# Accepts: Authorization: LOW foo:foo
# ---------------------------------------------------------------------------


@app.get("/services/s3auth/")
async def s3auth(authorization: Annotated[str | None, Header()] = None) -> JSONResponse:
    if authorization and authorization.startswith("LOW "):
        credentials = authorization[4:]
        if ":" in credentials:
            return JSONResponse(
                {
                    "authorized": True,
                    "username": _DEV_SCREENNAME,
                    "itemname": "@" + _DEV_SCREENNAME,
                    "email": _DEV_EMAIL,
                    "screenname": _DEV_SCREENNAME,
                }
            )
    return JSONResponse({"authorized": False}, status_code=401)


# ---------------------------------------------------------------------------
# IA Loans API  (was /internal/fake/loans in account.py)
# POST /services/loans/loan/
# ---------------------------------------------------------------------------


@app.post("/services/loans/loan/")
async def loans() -> JSONResponse:
    return JSONResponse({})


# ---------------------------------------------------------------------------
# IA Availability API v2  (was not mocked — pointed at real archive.org)
# POST /services/availability/
# ---------------------------------------------------------------------------


@app.post("/services/availability/")
async def availability() -> JSONResponse:
    return JSONResponse({"responses": {}})


# ---------------------------------------------------------------------------
# IA Borrow Status  (was hardcoded in lending.py line 599)
# GET /services/borrow/{identifier}
# ---------------------------------------------------------------------------


@app.get("/services/borrow/{identifier}")
async def borrow_status(identifier: str) -> JSONResponse:
    return JSONResponse({"status": "borrow_available", "identifier": identifier})


# ---------------------------------------------------------------------------
# reCAPTCHA siteverify  (was hitting recaptcha.net in dev)
# POST /recaptcha/api/siteverify
# ---------------------------------------------------------------------------


@app.post("/recaptcha/api/siteverify")
async def recaptcha_siteverify() -> JSONResponse:
    return JSONResponse({"success": True, "score": 0.9, "action": "submit"})


# ---------------------------------------------------------------------------
# be-api full-text search  (was hitting be-api.us.archive.org in dev)
# GET /fts/v1/search
# ---------------------------------------------------------------------------


@app.get("/fts/v1/search")
async def fts_search() -> JSONResponse:
    return JSONResponse({"hits": [], "total": 0})


# ---------------------------------------------------------------------------
# Amazon PA-API stub  (stretch goal — currently no dev intercept)
# POST /paapi5/getItems
# ---------------------------------------------------------------------------


@app.post("/paapi5/getItems")
async def amazon_get_items(request: Request) -> JSONResponse:
    body = await request.json()
    item_ids = body.get("ItemIds", [])
    items = [
        {
            "ASIN": asin,
            "ItemInfo": {
                "Title": {"DisplayValue": f"Mock Book ({asin})", "Label": "Title"},
            },
        }
        for asin in item_ids
    ]
    return JSONResponse({"ItemsResult": {"Items": items}})


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "ol-mockservices"})
