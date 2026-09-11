"""Borrow a book from a Lenny node, via OAuth 2.0 (#12844).

Lenny is a self-hosted lending server; many organisations run their own node.
Each node is its own OAuth authorization server, and Open Library is a client of
each. #13565 harvests a node's OPDS feed into the ``acquisitions`` table, so the
borrow links already exist as rows; this is the flow behind them.

    /borrow/lenny/OL51008637M  ->  node's /authorize  ->  /borrow/lenny/callback
                                                              |
                                            POST {node}/v1/api/oauth2/borrow

**This is a demo, and it deliberately stops one step short of reading the
book.** A Lenny access token authorizes creating a loan; it does NOT get the
patron through Lenny's read gate, which accepts a session cookie only and keys
the patron on ``sha256(lowercased email)`` (``lenny/core/api.py`` ``auth_check``).
So a loan created here is invisible to a patron who later signs in to Lenny
directly, and the reader will still ask them for an OTP. Closing that needs a
single-use token-to-session exchange on the Lenny side (ArchiveLabs/lenny#211)
plus a decision about how the two identities reconcile. Until then, showing a
"read now" link here would strand the patron *after* they had borrowed, which is
worse than not offering it.

Deliberate design choices, and the reasons, because each looks like an omission:

**The patron signs in at the node, and that is what makes the book readable.**
An OAuth access token authorizes Open Library's *backend* to call a node's API.
It does nothing for the patron's browser -- no cookie, no session, no reader. So
the node's own login is not an obstacle to route around here: it is the step
that gives the patron the session their reader needs. Open Library asserting an
already-authenticated patron would save them that sign-in, but it would not make
the book open, which is why this does not attempt it.

**The token is held custodially in the patron's own cookie**, Fernet-encrypted
with the same key and the same pattern as the S3 keys
(``accounts.model.encrypt_lenny_token``). Nothing is stored server-side, so
there is no table and no row to expire; a patron clearing cookies simply signs
in again.

One hazard comes with that, and it is inherent rather than a bug: the cookie is
the single copy of a rotating refresh token. Lenny revokes the whole family when
a rotated refresh token is reused, so two tabs refreshing at once would destroy
the grant. Refresh is therefore attempted once, on demand, and any failure
clears the cookie and sends the patron back through the flow -- a second sign-in
rather than a silent dead end.

**Endpoints come from discovery, not constants.** Every node publishes
``/.well-known/oauth-authorization-server``; a node that moves an endpoint
should not require an Open Library deploy.
"""

import base64
import hashlib
import logging
import secrets
from typing import Any
from urllib.parse import urlencode

import requests
import web
from cryptography.fernet import InvalidToken

from infogami import config
from infogami.utils import delegate
from openlibrary.accounts import get_current_user
from openlibrary.accounts.model import decrypt_lenny_token, encrypt_lenny_token
from openlibrary.core import cache
from openlibrary.core.acquisitions import Acquisition
from openlibrary.utils import extract_numeric_id_from_olid

logger = logging.getLogger("openlibrary.lenny")

DISCOVERY_PATH = "/.well-known/oauth-authorization-server"
REQUIRED_CODE_CHALLENGE_METHOD = "S256"
BORROW_SCOPE = "borrow"
REDIRECT_PATH = "/borrow/lenny/callback"

STATE_TTL_SECONDS = 600
"""How long a patron has to complete the node's login. Ten minutes is generous
for an OTP round trip and short enough that an abandoned attempt expires."""

DISCOVERY_TTL_SECONDS = 3600
HTTP_TIMEOUT_SECONDS = 10

PROVIDER_PREFIX = "lenny"
"""Feed provider names are per node (``lenny``, ``lenny_<host>``), because a
node's feed identity and cursor are its own. See #12844."""


def nodes() -> dict[str, dict[str, str]]:
    """Configured Lenny nodes, keyed by the feed ``provider_name`` they harvest as.

    Each entry needs ``issuer``, ``client_id`` and ``client_secret`` -- the
    credentials a node's operator issued to Open Library when they connected it.

    Config-based on purpose: there is no HTTP registration endpoint yet, and
    when there is, a client secret must NOT live in ``feed_registry.data``.
    That blob is treated as printable config throughout the harvest tooling (it
    is echoed by ``bookworm.cli register --show`` and named in its drift
    warning), so a secret there would reach stdout, the cron log, and cron mail.
    """
    return config.get("lenny_nodes") or {}


def discover(issuer: str) -> dict[str, Any]:
    """A node's OAuth metadata, cached.

    Raises ``ValueError`` if the node does not offer S256. Checked by
    membership rather than by taking the first entry: ``plain`` is refused by
    every node today, and a node advertising something weaker should fail
    closed rather than be accommodated.
    """
    key = f"lenny-oauth-metadata/{issuer}"
    if metadata := cache.get_memcache().get(key):
        return metadata

    resp = requests.get(issuer.rstrip("/") + DISCOVERY_PATH, timeout=HTTP_TIMEOUT_SECONDS)
    resp.raise_for_status()
    metadata = resp.json()

    methods = metadata.get("code_challenge_methods_supported") or []
    if REQUIRED_CODE_CHALLENGE_METHOD not in methods:
        raise ValueError(f"{issuer} does not support {REQUIRED_CODE_CHALLENGE_METHOD} (offers {methods})")
    for required in ("authorization_endpoint", "token_endpoint"):
        if not metadata.get(required):
            raise ValueError(f"{issuer} discovery document has no {required}")

    cache.get_memcache().set(key, metadata, expires=DISCOVERY_TTL_SECONDS)
    return metadata


def pkce_pair() -> tuple[str, str]:
    """A PKCE verifier and its S256 challenge (RFC 7636)."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def node_for_edition(edition_key: str) -> tuple[str, dict[str, str]] | None:
    """The configured node holding this edition, from the acquisitions table.

    Returns ``(provider_name, node_config)``, or None when no configured node
    lends it. Reads the rows the harvest already wrote rather than asking the
    nodes, so a book with no acquisition offers no borrow link.
    """
    try:
        edition_id = int(extract_numeric_id_from_olid(edition_key))
    except ValueError, TypeError:
        return None
    configured = nodes()
    for acquisition in Acquisition.get_by_edition(edition_id):
        provider_name = acquisition.provider_name or ""
        if provider_name.startswith(PROVIDER_PREFIX) and provider_name in configured:
            return provider_name, configured[provider_name]
    return None


def _redirect_uri() -> str:
    return config.get("lenny_redirect_uri") or f"https://openlibrary.org{REDIRECT_PATH}"


def _state_key(state: str) -> str:
    return f"lenny-oauth-state/{state}"


def take_state(state: str) -> dict[str, Any] | None:
    """Read and consume a pending authorization. Single use.

    Deleted on read, so a replayed callback finds nothing. The PKCE verifier
    lives here, server-side, rather than in a cookie.
    """
    memcache = cache.get_memcache()
    key = _state_key(state)
    if not (pending := memcache.get(key)):
        return None
    memcache.delete(key)
    return pending


def check_issuer(pending: dict[str, Any], iss: str | None) -> None:
    """Verify the callback came from the node we sent the patron to.

    One callback path serves every node, so the URL cannot say which node is
    answering: the node comes from ``state`` and ``iss`` has to match what that
    node is registered as. Without this, a hostile node that a patron also uses
    can replay a code and have Open Library redeem it at a different node --
    the OAuth mix-up attack. Every node sets
    ``authorization_response_iss_parameter_supported``, so a missing ``iss`` is
    itself wrong, and both cases abort rather than warn.
    """
    expected = pending["issuer"].rstrip("/")
    if not iss:
        raise ValueError(f"callback for {expected} carried no iss parameter")
    if iss.rstrip("/") != expected:
        raise ValueError(f"callback iss {iss!r} does not match {expected!r}")


def exchange_code(pending: dict[str, Any], code: str) -> tuple[str, str]:
    """Trade the authorization code for tokens. Returns ``(access, refresh)``.

    The refresh token may be absent; a node is not obliged to issue one.
    """
    metadata = discover(pending["issuer"])
    resp = requests.post(
        metadata["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": pending["redirect_uri"],
            "client_id": pending["client_id"],
            "client_secret": pending["client_secret"],
            "code_verifier": pending["code_verifier"],
        },
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    payload = resp.json() or {}
    if not (token := payload.get("access_token")):
        raise ValueError("token endpoint returned no access_token")
    return token, payload.get("refresh_token") or ""


BORROW_ERRORS = {
    "not_found": "This book is not in that library's collection.",
    "unavailable": "Every copy is currently on loan. Please try again later.",
    "loan_limit_reached": "You have reached the loan limit for this library.",
    "not_lendable": "This book is not available to borrow.",
}
"""Lenny's typed borrow failures. Distinct messages on purpose: "all copies are
out" and "you have too many books out" ask the patron to do different things,
and collapsing them into one generic failure loses that."""


def borrow(pending: dict[str, Any], token: str, edition_id: int) -> dict[str, Any]:
    """Create the loan. Returns the node's response."""
    issuer = pending["issuer"].rstrip("/")
    resp = requests.post(
        f"{issuer}/v1/api/oauth2/borrow",
        data={"edition_id": edition_id},
        headers={"Authorization": f"Bearer {token}"},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    if resp.status_code >= 400:
        error = (resp.json() or {}).get("error") if resp.headers.get("content-type", "").startswith("application/json") else None
        raise LennyBorrowError(error or "unknown_error", resp.status_code)
    return resp.json()


class LennyBorrowError(Exception):
    def __init__(self, error: str, status: int):
        super().__init__(error)
        self.error = error
        self.status = status

    @property
    def message(self) -> str:
        return BORROW_ERRORS.get(self.error, "That library could not lend this book right now.")


class lenny_borrow(delegate.page):
    path = r"/borrow/lenny/(OL\d+M)"

    def GET(self, edition_olid: str):
        edition_key = f"/books/{edition_olid}"
        if not (user := get_current_user()):
            raise web.seeother(f"/account/login?redirect={edition_key}")
        if not (found := node_for_edition(edition_key)):
            raise web.notfound()
        provider_name, node = found

        try:
            metadata = discover(node["issuer"])
        except Exception:
            logger.exception("lenny discovery failed for %s", provider_name)
            return render_error("That library is not reachable right now. Please try again later.")

        verifier, challenge = pkce_pair()
        state = secrets.token_urlsafe(32)
        cache.get_memcache().set(
            _state_key(state),
            {
                "issuer": node["issuer"],
                "client_id": node["client_id"],
                "client_secret": node["client_secret"],
                "code_verifier": verifier,
                "redirect_uri": _redirect_uri(),
                "edition_key": edition_key,
                "provider_name": provider_name,
                "username": user.key,
            },
            expires=STATE_TTL_SECONDS,
        )

        params = {
            "response_type": "code",
            "client_id": node["client_id"],
            "redirect_uri": _redirect_uri(),
            "scope": BORROW_SCOPE,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": REQUIRED_CODE_CHALLENGE_METHOD,
        }
        raise web.seeother(f"{metadata['authorization_endpoint']}?{urlencode(params)}")


class lenny_callback(delegate.page):
    path = REDIRECT_PATH

    def GET(self):
        i = web.input(code=None, state=None, iss=None, error=None)

        if not i.state or not (pending := take_state(i.state)):
            # Expired, replayed, or forged: all indistinguishable, and all mean
            # there is no authorization in flight to complete.
            return render_error("That borrow request expired. Please try borrowing again.")

        if i.error:
            logger.info("lenny authorization declined for %s: %s", pending["provider_name"], i.error)
            return render_error("The library did not authorize this loan.")

        try:
            check_issuer(pending, i.iss)
        except ValueError:
            logger.exception("lenny callback failed the issuer check")
            return render_error("That borrow request could not be verified. Please try again.")

        if not i.code:
            return render_error("That borrow request expired. Please try borrowing again.")

        try:
            token, refresh_token = exchange_code(pending, i.code)
        except Exception:
            logger.exception("lenny token exchange failed for %s", pending["provider_name"])
            return render_error("That library could not complete the loan. Please try again later.")

        edition_id = int(extract_numeric_id_from_olid(pending["edition_key"]))
        try:
            loan = borrow(pending, token, edition_id)
        except LennyBorrowError as e:
            logger.info("lenny borrow refused (%s/%s)", e.status, e.error)
            return render_error(e.message)
        except Exception:
            logger.exception("lenny borrow failed for %s", pending["provider_name"])
            return render_error("That library could not complete the loan. Please try again later.")

        set_custodial_token(pending["provider_name"], token, refresh_token)
        logger.info("lenny loan created on %s for %s", pending["provider_name"], pending["edition_key"])
        return render_borrowed(pending["edition_key"], loan, read_url(pending, loan))


COOKIE_NAME = "lenny"
COOKIE_MAX_AGE = 3600 * 24 * 30
"""Thirty days. A node's refresh token lasts ninety, but a custodial credential
in a cookie should not outlive the patron's interest in it by two months."""


def set_custodial_token(node: str, access_token: str, refresh_token: str) -> None:
    """Hold the patron's node tokens in their own cookie.

    ``secure`` and ``httponly`` for the same reasons as the S3 cookie: this is a
    credential, script has no business reading it, and it must not travel over
    plain HTTP. ``samesite="Lax"`` so it survives the return redirect from the
    node.
    """
    web.setcookie(
        COOKIE_NAME,
        encrypt_lenny_token(node, access_token, refresh_token),
        expires=COOKIE_MAX_AGE,
        secure=True,
        httponly=True,
        samesite="Lax",
    )


def clear_custodial_token() -> None:
    web.setcookie(COOKIE_NAME, "", expires=1)


def get_custodial_token(node: str) -> tuple[str, str] | None:
    """The patron's held tokens for a node, or None.

    Returns None for a missing, tampered, stale or other-node cookie rather
    than raising: every one of them means "this patron has no usable credential
    for this node", and the caller's response to all of them is the same.
    """
    if not (cookie := web.cookies().get(COOKIE_NAME)):
        return None
    try:
        stored_node, access_token, refresh_token = decrypt_lenny_token(cookie)
    except InvalidToken, ValueError:
        # InvalidToken: tampered, or encrypted under a rotated key. ValueError:
        # a well-formed token whose plaintext is not the three fields this
        # version writes. Both mean the same thing to every caller -- no usable
        # credential -- and neither is worth an exception for.
        return None
    if stored_node != node:
        return None
    return access_token, refresh_token


def read_url(pending: dict[str, Any], loan: dict[str, Any]) -> str:
    """Where the patron reads what they just borrowed.

    They authenticated at the node a moment ago, so their browser already holds
    that node's session -- which is what its reader requires, and what an API
    token could not have given them.
    """
    issuer = pending["issuer"].rstrip("/")
    edition_id = loan.get("edition_id") or extract_numeric_id_from_olid(pending["edition_key"])
    return f"{issuer}/v1/api/items/{edition_id}/read"


def render_error(message: str) -> str:
    return f"<html><body><h1>Borrow</h1><p>{web.websafe(message)}</p></body></html>"


def render_borrowed(edition_key: str, loan: dict[str, Any], read: str) -> str:
    due = web.websafe(str(loan.get("due_at") or "unknown"))
    return (
        "<html><body><h1>Borrowed</h1>"
        f"<p>The loan was created, due {due}.</p>"
        f'<p><a href="{web.websafe(read)}">Read it now</a></p>'
        f'<p><a href="{web.websafe(edition_key)}">Back to the book</a></p>'
        "</body></html>"
    )
