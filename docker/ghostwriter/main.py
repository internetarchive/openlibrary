"""
Ghostwriter — mock services for Open Library local development.

Replaces the web.py inline stubs from account.py (/internal/fake/*) and
provides mocks for external services that do not have dev interceptors:
  - IA xauthn  (was /internal/fake/xauth)
  - IA S3 auth (was /internal/fake/s3auth)
  - IA loans   (was /internal/fake/loans)
  - IA loans "changes" feed (needed by the near-realtime loan availability updater)
  - IA availability v2 (was not mocked — pointed at real archive.org)
  - IA borrow status (was hardcoded in lending.py)
  - reCAPTCHA siteverify
  - be-api full-text search
  - Amazon PA-API (stub)

Configure openlibrary.yml to point at this service:
  ia_xauth_api_url:          http://ghostwriter:8090/services/xauthn/
  ia_s3_auth_url:            http://ghostwriter:8090/services/s3auth/
  ia_loan_api_url:           http://ghostwriter:8090/services/loans/loan/
  ia_s3_loan_url:            http://ghostwriter:8090/services/loans/loan/
  ia_availability_api_v2_url: http://ghostwriter:8090/services/availability/
  ia_borrow_status_url:      http://ghostwriter:8090/services/borrow/
  recaptcha_url:             http://ghostwriter:8090/recaptcha/api/siteverify

  /fts/v1/search is implemented but NOT wired as the default — be-api.us.archive.org
  works fine for local dev as-is. Point (plugin_inside) search_endpoint at
  http://ghostwriter:8090/fts/v1/search only if you need to work offline or
  simulate a specific search response.

Email: configure smtp_server=ghostwriter, smtp_port=1025, dummy_sendmail=False
       Inspect captured mail via mailpit: http://localhost:8025
"""

import asyncio
import itertools
import json as jsonlib
import logging
import random
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    await _seed_loan_changes()
    task = asyncio.create_task(_loan_changes_ongoing_loop())
    yield
    task.cancel()


app = FastAPI(title="Ghostwriter", docs_url="/mock/docs", lifespan=_lifespan)

# ---------------------------------------------------------------------------
# IA xauthn  (was /internal/fake/xauth in account.py)
# POST /services/xauthn/?op=...
#
# The real client (InternetArchiveAccount.xauth in accounts/model.py) sends
# `op` as a query param and the payload as a JSON body, and reads "success"
# (not "status") from the response.
#
# Supported ops: authenticate, info, issue_otp, redeem_otp, create, issue_key, activate
# Dev credentials: email=test@example.com, password=<any non-empty>
# Dev S3 keys:     access=foo, secret=foo
# Dev OTP code:    123456
# ---------------------------------------------------------------------------

_DEV_S3 = {"access": "foo", "secret": "foo"}
_DEV_SCREENNAME = "testuser"
_DEV_EMAIL = "test@example.com"
_DEV_OTP = "123456"
_DEV_TOKEN = "dev_placeholder_token"


@app.post("/services/xauthn/")
async def xauth(op: str, request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except ValueError:
        body = {}

    if op == "authenticate":
        if not body.get("password"):
            return JSONResponse({"success": False, "values": {"reason": "bad_password"}})
        return JSONResponse(
            {
                "success": True,
                "version": 1,
                "values": {
                    "token": _DEV_TOKEN,
                    "email": body.get("email") or _DEV_EMAIL,
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
                "success": True,
                "version": 1,
                "values": {
                    "locked": False,
                    "email": _DEV_EMAIL,
                    "itemname": "@" + _DEV_SCREENNAME,
                    "screenname": _DEV_SCREENNAME,
                    "verified": True,
                },
            }
        )

    if op == "issue_otp":
        return JSONResponse({"success": True, "version": 1})

    if op == "redeem_otp":
        # xauth("redeem_otp", ..., password=otp) sends the OTP in the "password" field
        if body.get("password") == _DEV_OTP:
            return JSONResponse(
                {
                    "success": True,
                    "version": 1,
                    "values": {
                        "email": body.get("email") or _DEV_EMAIL,
                        "itemname": "@" + _DEV_SCREENNAME,
                        "screenname": _DEV_SCREENNAME,
                        "token": _DEV_TOKEN,
                    },
                }
            )
        return JSONResponse({"success": False, "version": 1, "values": {"reason": "invalid_otp"}})

    if op == "issue_key":
        return JSONResponse({"success": True, "version": 1, "s3": dict(_DEV_S3), "ttl": 3600})

    if op == "create":
        email = str(body.get("email") or _DEV_EMAIL)
        screenname = str(body.get("screenname") or _DEV_SCREENNAME)
        return JSONResponse(
            {
                "success": True,
                "version": 1,
                "values": {
                    "email": email,
                    "screenname": screenname,
                    "itemname": "@" + screenname,
                    "verified": False,
                    "locked": False,
                },
            }
        )

    if op == "activate":
        return JSONResponse(
            {
                "success": True,
                "version": 1,
                "values": {
                    "email": _DEV_EMAIL,
                    "itemname": "@" + _DEV_SCREENNAME,
                    "screenname": _DEV_SCREENNAME,
                    "token": _DEV_TOKEN,
                },
            }
        )

    logger.warning("xauthn: unhandled op=%s", op)
    return JSONResponse({"success": False, "values": {"reason": f"unknown_op:{op}"}}, status_code=400)


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
# IA Loans "changes" feed  (needed by scripts/solr_updater/loan_availability_updater.py,
# see get_loan_changes() in openlibrary/core/lending.py)
# GET /services/loans/loan/?action=changes&after_uid=N&limit=N
#
# On startup, seeds 1000 borrow/return events using real `ia` identifiers
# pulled from the local Solr index, with timestamps spread evenly over the
# last 14 days — this proves catchup/backfill for a fresh consumer.
# Every 60s a background loop then appends 50 new events and evicts the 50
# oldest from the in-memory window — this proves ongoing/steady-state polling.
# ---------------------------------------------------------------------------

_SOLR_URL = "http://solr:8983/solr/openlibrary/select"
_FALLBACK_IA_IDS = [
    "recipesfromoldso00mead",
    "interiorcastleor00tere",
    "pioneersfrontier00macd",
    "completeworksofm10twai",
    "completeworksofm21twai",
    "completeworksofm01twaiiala",
    "completeworksofm00twai",
]
_LOAN_CHANGES_WINDOW_SIZE = 1000
_LOAN_CHANGES_BATCH_SIZE = 50
_LOAN_CHANGES_INTERVAL_SECONDS = 60

_loan_changes: list[dict] = []
_loan_changes_lock = asyncio.Lock()
_next_loan_uid = itertools.count(1)


async def _fetch_real_ia_ids(limit: int = 200) -> list[str]:
    """Best-effort fetch of real `ia` identifiers from the local Solr index.

    Falls back to a small static pool (matching the shape of real IA identifiers)
    if Solr is unreachable or has no ebook-access documents yet, which is the
    case on a completely fresh dev environment before any content is indexed.
    """
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(
                _SOLR_URL,
                params={"q": "ia:*", "fl": "ia", "rows": limit, "wt": "json"},
            )
            resp.raise_for_status()
            docs = resp.json()["response"]["docs"]
            ids = [ia_id for doc in docs for ia_id in doc.get("ia", [])]
            return ids or list(_FALLBACK_IA_IDS)
    except (httpx.HTTPError, KeyError, ValueError):  # fmt: skip
        logger.warning("loan changes: could not fetch real ia ids from solr, using fallback pool")
        return list(_FALLBACK_IA_IDS)


def _make_loan_event(identifier: str, when: datetime, event_type: str) -> dict:
    uid = next(_next_loan_uid)
    extra = jsonlib.dumps({"until": (when + timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")}) if event_type == "borrow" else "{}"
    return {
        "time": when.strftime("%Y-%m-%d %H:%M:%S"),
        "identifier": identifier,
        "username": "@dummy",
        "loan_id": f"a1000001-0001-4000-8000-{uid:012x}",
        "event_type": event_type,
        "extra": extra,
        "uid": uid,
    }


async def _seed_loan_changes() -> None:
    ids = await _fetch_real_ia_ids()
    now = datetime.now(UTC)
    start = now - timedelta(days=14)
    step = (now - start) / _LOAN_CHANGES_WINDOW_SIZE
    events = [
        _make_loan_event(
            random.choice(ids),
            start + step * i,
            "borrow" if i % 2 == 0 else "return",
        )
        for i in range(_LOAN_CHANGES_WINDOW_SIZE)
    ]
    async with _loan_changes_lock:
        _loan_changes.extend(events)
    logger.info("loan changes: seeded %d events spanning the last 14 days", len(events))


async def _loan_changes_ongoing_loop() -> None:
    ids = await _fetch_real_ia_ids()
    while True:
        await asyncio.sleep(_LOAN_CHANGES_INTERVAL_SECONDS)
        now = datetime.now(UTC)
        new_events = [_make_loan_event(random.choice(ids), now, "borrow" if i % 2 == 0 else "return") for i in range(_LOAN_CHANGES_BATCH_SIZE)]
        async with _loan_changes_lock:
            _loan_changes.extend(new_events)
            del _loan_changes[:_LOAN_CHANGES_BATCH_SIZE]
        logger.info("loan changes: added %d, evicted %d oldest", len(new_events), _LOAN_CHANGES_BATCH_SIZE)


@app.get("/services/loans/loan/")
async def loan_changes(action: str, after_uid: int = 0, limit: int = 1000) -> JSONResponse:
    if action != "changes":
        return JSONResponse({"status": "error", "error": f"unsupported action: {action}"}, status_code=400)
    async with _loan_changes_lock:
        rows = [event for event in _loan_changes if event["uid"] > after_uid][:limit]
        latest_uid = _loan_changes[-1]["uid"] if _loan_changes else 0
    return JSONResponse({"status": "OK", "latest_uid": latest_uid, "rows": rows})


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
    return JSONResponse({"status": "ok", "service": "ol-ghostwriter"})
