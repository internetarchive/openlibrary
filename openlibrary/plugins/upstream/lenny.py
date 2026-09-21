"""Borrow a book from a Lenny node, via OAuth 2.0 (#12844).

Lenny is a self-hosted lending server; many organisations run their own node.
Each node is its own OAuth authorization server, and Open Library is a client of
each. #13565 harvests a node's OPDS feed into the ``acquisitions`` table, so the
borrow links already exist as rows; this is the flow behind them.

    /borrow/lenny/OL51008637M  ->  node's /authorize  ->  /borrow/lenny/callback
                                                              |
                                            POST {node}/v1/api/oauth2/borrow

Lenny's read gate accepts a session cookie only -- there is no bearer path --
and keys the patron on ``sha256(lowercased email)`` (``lenny/core/api.py``
``auth_check``). That is not a gap this flow has to close. The node's
``/v1/api/oauth2/authorize`` refuses to issue a code without a node session and
bounces a patron who has none to Lenny's own OTP login
(``lenny/routes/oauth2.py:241``), so by the time Open Library holds a token the
patron's browser already holds the session the reader asks for. An earlier
version of this docstring said the opposite and recommended a token-to-session
exchange (ArchiveLabs/lenny#211); that conclusion came from checking the read
gate in isolation without tracing the flow that feeds it. See
``ol-kb/wiki/lenny-oauth.md``.

Deliberate design choices, and the reasons, because each looks like an omission:

**The patron signs in at the node, and that is what makes the book readable.**
An OAuth access token authorizes Open Library's *backend* to call a node's API.
It does nothing for the patron's browser -- no cookie, no session, no reader. So
the node's own login is not an obstacle to route around here: it is the step
that gives the patron the session their reader needs. Open Library asserting an
already-authenticated patron -- a signed assertion the node trusts in place of
its own login -- would save them that sign-in, but it would not make the book
open, and it needs a pairwise pseudonymous subject and a published signing key
that do not exist. This does not attempt it. It does send ``login_hint``, which
is a suggestion the node is free to ignore and not an assertion of anything;
see :func:`authorize_url` for what it costs and for why no node in service
reads it yet.

**The grant is stored server-side**, one row per ``(patron, node)``, by
:mod:`openlibrary.core.provider_tokens` (#13685). A cookie cannot do this job,
and the reason is not a preference: Lenny rotates refresh tokens and revokes the
whole family when a spent one is presented again, so the storage has to
single-flight the refresh. Two tabs send the same cookie, so both hold the same
``R0``. A lock can make the loser wait, but when it wakes the only refresh token
it has is the ``R0`` from its own request headers -- ``R1`` exists solely in the
winner's HTTP response to the *other* tab, with nowhere server-side to read it
back from. The loser then either presents ``R0``, which is the reuse that
destroys the grant, or abandons a grant that is alive.
:meth:`~openlibrary.core.provider_tokens.ProviderToken.get_fresh` re-reads under
the lock, which is the step a cookie has no way to perform.

**This module holds no storage of its own.** It supplies the HTTP half:
:func:`node_refresher` is the ``Refresher`` that ``get_fresh`` calls with the
patron's row locked, which is why it carries a tighter timeout than the rest of
this module -- whatever it waits for, the row waits for too.

**Endpoints come from discovery, not constants.** Every node publishes
``/.well-known/oauth-authorization-server``; a node that moves an endpoint
should not require an Open Library deploy.
"""

import asyncio
import base64
import datetime
import hashlib
import logging
import secrets
import time
from typing import Any, NamedTuple
from urllib.parse import urlencode

import httpx
import requests
import web

from infogami import config
from infogami.utils import delegate
from openlibrary.accounts import get_current_user
from openlibrary.core import cache
from openlibrary.core.acquisitions import Acquisition
from openlibrary.core.provider_tokens import (
    Grant,
    ProviderToken,
    Refresher,
    TokenRefreshFailed,
)
from openlibrary.utils import extract_numeric_id_from_olid
from openlibrary.utils.async_utils import async_bridge, cache_per_event_loop

logger = logging.getLogger("openlibrary.lenny")

DISCOVERY_PATH = "/.well-known/oauth-authorization-server"
REQUIRED_CODE_CHALLENGE_METHOD = "S256"
REDIRECT_PATH = "/borrow/lenny/callback"

SCOPES = "loans:read borrow"
"""Requested together, in one consent.

``borrow`` alone is enough to create the loan, but the merged loan lookup
(#13687) needs ``loans:read``, and asking for it later means a second trip
through the node's login for a patron who already agreed once. Both are in the
node's ``scopes_supported`` (verified against ``lennyforlibraries.org``
discovery, 2026-09-20), and an unregistered scope is a hard error at the node
rather than a silent narrowing -- so a node that does not offer one of these
fails visibly here rather than handing back a grant that cannot read loans.
"""

STATE_TTL_SECONDS = 600
"""How long a patron has to complete the node's login. Ten minutes is generous
for an OTP round trip and short enough that an abandoned attempt expires."""

DISCOVERY_TTL_SECONDS = 3600
HTTP_TIMEOUT_SECONDS = 10

REFRESH_TIMEOUT_SECONDS = 5
"""Every network call a refresh makes, and deliberately shorter than the rest.

``ProviderToken.get_fresh`` calls :func:`node_refresher` with ``SELECT ... FOR
UPDATE`` held on the patron's row, so this bounds how long that row -- and every
other flight for the same patron and node -- is blocked. The worst case is two
of these back to back, discovery then the token endpoint, so ten seconds.
"""

LOANS_PATH = "/v1/api/oauth2/loans"
"""Built from the issuer rather than read from discovery, and that is not a
shortcut taken for convenience.

RFC 8414 registers no metadata field for a resource endpoint, and no node
advertises one: ``lennyforlibraries.org`` publishes ``authorization_endpoint``,
``token_endpoint`` and ``revocation_endpoint`` and nothing else (checked
2026-09-20, command below). #13687 asked for this path to come from discovery;
there is nowhere in the document for it to come from. :func:`borrow` builds its
own path the same way, for the same reason.

Discovery still decides the *origin*, which is the part a node can move. The
path is Lenny's own API surface and carries its version in itself.

    curl -s https://lennyforlibraries.org/.well-known/oauth-authorization-server
"""

LOANS_TIMEOUT_SECONDS = 4
"""Per node, and it bounds the page.

The nodes are queried concurrently, so the wall time a patron waits for the
loans of N libraries is one of these and not N of them. That is the whole
reason this is not a sequential loop: four providers behind four dead nodes
would otherwise be four timeouts end to end on a page the patron asked for.
"""

LOANS_DEADLINE_SECONDS = 12
"""A ceiling over the *token* phase, which is the part concurrency cannot fix.

:func:`access_token_for` is synchronous and may refresh, which costs up to two
``REFRESH_TIMEOUT_SECONDS`` calls with the patron's row locked. Those cannot be
run on worker threads: ``web.db.DB`` keeps its connection in a ``threadeddict``
and ``oldev:latest`` has no ``dbutils``, so ``has_pooling`` is false and every
new thread that touches :func:`openlibrary.core.db.get_db` opens a Postgres
connection that is never released (``_unload_context`` only runs when pooling
is on). So the token phase stays sequential in the request thread, and this
deadline stops it after the grants it has managed to resolve rather than
letting N expired grants at N hanging nodes add up.
"""

PROVIDER_RESOURCE_TYPE = "provider"
"""``resource_type`` on a merged provider loan.

Deliberately not ``bookreader`` and deliberately not absent. ``bookreader`` is
what ``templates/account/loans.html`` keys its Internet Archive branch on, and
anything falling past that branch reaches an ``else`` that offers a
``loan['loan_link']`` download and an Adobe Digital Editions return -- a
``KeyError`` on this loan shape, and wrong advice if it were not. The template
tests ``loan.get('provider')`` before either branch; this value exists so that
the loan is never *silently* IA-shaped if some other consumer keys on the type.
"""


class ProviderLoans(NamedTuple):
    """What a merged loan lookup could and could not find out.

    ``unreachable`` and ``unauthorized`` are kept apart because they ask the
    patron to do different things -- wait, or reconnect the library -- the same
    reason :data:`BORROW_ERRORS` does not collapse "all copies are out" into
    "you have too many books out". Both are provider names, not counts, so a
    caller can name the library.
    """

    loans: list[dict[str, Any]]
    unreachable: list[str]
    unauthorized: list[str]


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


def discover(issuer: str, timeout: int = HTTP_TIMEOUT_SECONDS) -> dict[str, Any]:
    """A node's OAuth metadata, cached.

    Raises ``ValueError`` if the node does not offer S256. Checked by
    membership rather than by taking the first entry: ``plain`` is refused by
    every node today, and a node advertising something weaker should fail
    closed rather than be accommodated.

    ``timeout`` is a parameter because a cache miss inside a refresh happens
    with the patron's row locked, and the caller there needs a tighter bound
    than a patron-facing request does.
    """
    key = f"lenny-oauth-metadata/{issuer}"
    if metadata := cache.get_memcache().get(key):
        return metadata

    resp = requests.get(issuer.rstrip("/") + DISCOVERY_PATH, timeout=timeout)
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


def _grant_from_payload(payload: dict[str, Any]) -> Grant:
    """A token endpoint response as a :class:`Grant`.

    ``expires`` is naive UTC to match the table's ``timestamp`` columns; see
    ``provider_tokens._utcnow``.

    An ``expires_in`` that is present but not an integer raises rather than
    being dropped. A grant whose lifetime cannot be read is never refreshed --
    ``Grant.is_expired`` reads a missing expiry as "still live" -- so tolerating
    the garbage buys one working borrow and pays for it with an unexplained
    logout later.
    """
    if not (token := payload.get("access_token")):
        raise ValueError("token endpoint returned no access_token")
    expires = None
    if (expires_in := payload.get("expires_in")) is not None:
        expires = datetime.datetime.now(datetime.UTC).replace(tzinfo=None) + datetime.timedelta(seconds=int(expires_in))
    return Grant(
        access_token=token,
        refresh_token=payload.get("refresh_token") or None,
        expires=expires,
        scope=payload.get("scope") or "",
    )


def exchange_code(pending: dict[str, Any], code: str) -> Grant:
    """Trade the authorization code for the patron's grant at the node.

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
    return _grant_from_payload(resp.json() or {})


def node_refresher(node: dict[str, str]) -> Refresher:
    """A ``Refresher`` for ``ProviderToken.get_fresh``, bound to one node.

    Called with the patron's row locked, so both of its network calls carry
    :data:`REFRESH_TIMEOUT_SECONDS` rather than the module's ordinary timeout.

    It does not catch anything. ``get_fresh`` treats every exception the same
    way -- delete the grant, do not retry -- because a timeout and a rejection
    are indistinguishable from this side, and the node may have rotated the
    token and lost the response on the way back. Presenting it again is the
    precise act that revokes the whole family.
    """

    def refresh(refresh_token: str) -> Grant:
        metadata = discover(node["issuer"], timeout=REFRESH_TIMEOUT_SECONDS)
        resp = requests.post(
            metadata["token_endpoint"],
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": node["client_id"],
                "client_secret": node["client_secret"],
            },
            timeout=REFRESH_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return _grant_from_payload(resp.json() or {})

    return refresh


def access_token_for(username: str, provider_name: str) -> str | None:
    """A usable access token for this patron at this node, or None.

    The one entry point for anything that presents a token to a node -- the
    merged loan lookup (#13687) included. Returns None when the patron has to
    authorize again, which is what a missing grant, an expired one with no
    refresh token, and a failed refresh all mean.
    """
    if not (node := nodes().get(provider_name)):
        return None
    try:
        grant = ProviderToken.get_fresh(username, provider_name, node_refresher(node))
    except TokenRefreshFailed:
        logger.info("lenny grant cleared for %s at %s", username, provider_name)
        return None
    return grant.access_token if grant else None


_loans_client = cache_per_event_loop(httpx.AsyncClient)
"""One client per event loop, never one per process.

``async_bridge`` runs its own loop on its own thread, so a process-wide
``AsyncClient`` would eventually have a pooled connection created on one loop
reused from another and raise ``RuntimeError: ... bound to a different event
loop``. See :func:`openlibrary.utils.async_utils.cache_per_event_loop`.
"""


async def fetch_node_loans(issuer: str, token: str, timeout_seconds: float) -> list[dict[str, Any]]:
    """The ``{"loans": [...]}`` payload from one node, as a list.

    Returns the node's own dicts -- ``edition_id``, ``borrowed_at``, ``due_at``
    -- and does not translate them. Raises on anything that is not a 2xx with a
    JSON body, which the caller turns into "that library did not answer"
    rather than into a broken page.

    The bound is handed to httpx rather than wrapped in ``asyncio.timeout``
    (which is what ruff's ASYNC109 asks for, hence the parameter's name): httpx
    applies it separately to connect, read, write and pool, and a node that
    accepts the connection and then dribbles bytes is the failure this has to
    survive. An outer ``asyncio.timeout`` would be a second, blunter bound over
    the top of that one.
    """
    resp = await _loans_client().get(
        issuer.rstrip("/") + LOANS_PATH,
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout_seconds,
    )
    resp.raise_for_status()
    return (resp.json() or {}).get("loans") or []


def _epoch(value: Any) -> float:
    """An ISO 8601 instant as a POSIX timestamp, or ``0.0``.

    ``0.0`` rather than ``None`` because the loans template feeds this straight
    to ``datetime_from_utc_timestamp``. ``borrowed_at`` is documented nullable,
    and the template skips its "Borrowed ..." line on a falsy value rather than
    telling the patron they borrowed the book in 1970.
    """
    if not value:
        return 0.0
    try:
        parsed = datetime.datetime.fromisoformat(str(value))
    except ValueError:
        logger.info("lenny loan carried an unparsable timestamp: %r", value)
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.UTC)
    return parsed.timestamp()


def loan_from_node(provider_name: str, issuer: str, username: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """One node loan in the shape ``templates/account/loans.html`` consumes.

    Returns None when ``edition_id`` is missing or not an integer: there is
    then no edition key to render and nothing useful to say about it.

    ``edition_id`` is the **bare integer** -- ``37044497`` means
    ``OL37044497M`` -- so it maps onto an edition key directly rather than
    through a lookup.

    The failure log names the payload's *keys*, never its values. What it is
    diagnosing is a shape mismatch, which the keys answer completely, and the
    values are a record of which books a named patron has borrowed from a
    library -- circulation records, which is not a thing to leave in
    application logs in exchange for nothing.
    """
    try:
        edition_id = int(payload["edition_id"])
    except KeyError, TypeError, ValueError:
        logger.info("lenny loan from %s had no usable edition_id; keys were %s", provider_name, sorted(payload))
        return None
    return {
        "book": f"/books/OL{edition_id}M",
        "loaned_at": _epoch(payload.get("borrowed_at")),
        "expiry": payload.get("due_at"),
        "userid": f"ol:{username}",
        "provider": provider_name,
        "resource_type": PROVIDER_RESOURCE_TYPE,
        "read_url": item_read_url(issuer, edition_id),
    }


def _patron_tokens(username: str, deadline: float) -> tuple[list[tuple[str, str]], list[str], list[str]]:
    """Access tokens for every configured node this patron holds a grant at.

    Sequential and synchronous on purpose -- see :data:`LOANS_DEADLINE_SECONDS`
    for why it cannot be moved onto worker threads. In the ordinary case it
    does no network at all: an unexpired grant is one locked indexed read,
    measured at 0.446 ms, of which the lock is 0.023 ms. Cheap enough at
    page-render frequency that the unconditional ``FOR UPDATE`` in
    ``get_fresh`` is not worth avoiding -- the read-then-lock variant was
    built and measured, and is slower under contention because the row it
    reads unlocked is expired precisely when a refresh is already in flight.

    Returns ``(holdings, unreachable, unauthorized)``.
    """
    configured = nodes()
    holdings: list[tuple[str, str]] = []
    unreachable: list[str] = []
    unauthorized: list[str] = []

    try:
        providers = ProviderToken.get_providers(username)
    except Exception:
        # The patron's own loans page must still render. This reports nothing
        # rather than guessing: with the store unreadable there is no list of
        # libraries to name, and naming none is more honest than naming all.
        logger.exception("could not list provider grants for %s", username)
        return [], [], []

    for provider_name in providers:
        if provider_name not in configured:
            # A grant at a node this deploy no longer configures -- not the
            # patron's problem, and not something they can act on.
            continue
        if time.monotonic() >= deadline:
            logger.warning("lenny token phase hit its deadline; %s not resolved", provider_name)
            unreachable.append(provider_name)
            continue
        try:
            token = access_token_for(username, provider_name)
        except Exception:
            # access_token_for already absorbs TokenRefreshFailed, so anything
            # arriving here is the store or the node misbehaving rather than
            # the patron needing to reconnect.
            logger.exception("could not resolve a lenny token for %s at %s", username, provider_name)
            unreachable.append(provider_name)
            continue
        if token:
            holdings.append((provider_name, token))
        else:
            unauthorized.append(provider_name)

    return holdings, unreachable, unauthorized


async def _gather_node_loans(
    holdings: list[tuple[str, str]],
    issuers: dict[str, str],
    budget: float,
) -> list[list[dict[str, Any]] | BaseException]:
    """Every node at once, each with its own timeout.

    ``return_exceptions`` so one dead node costs its own loans rather than the
    page. No aggregate timeout wrapping the gather: one that fired would throw
    away the answers the healthy nodes had already given, which is the opposite
    of degrading gracefully. Concurrency is what bounds the total.
    """
    per_call = max(0.1, min(LOANS_TIMEOUT_SECONDS, budget))
    return await asyncio.gather(
        *(fetch_node_loans(issuers[provider_name], token, per_call) for provider_name, token in holdings),
        return_exceptions=True,
    )


def provider_loans(username: str) -> ProviderLoans:
    """Every loan this patron holds at a configured Lenny node.

    The merge side of #13687. Two phases, because they fail differently:
    resolve the patron's tokens (sequential, synchronous, usually no network),
    then ask every node for its loans at once.

    **It does not raise.** A node that is slow, down, or answering nonsense
    costs its own entry in ``unreachable`` and nothing more. The Internet
    Archive loans this is merged alongside come from a different call that this
    one cannot fail.
    """
    deadline = time.monotonic() + LOANS_DEADLINE_SECONDS
    holdings, unreachable, unauthorized = _patron_tokens(username, deadline)
    if not holdings:
        return ProviderLoans([], unreachable, unauthorized)

    configured = nodes()
    issuers = {provider_name: configured[provider_name]["issuer"] for provider_name, _ in holdings}
    budget = deadline - time.monotonic()
    if budget <= 0:
        logger.warning("lenny loans deadline spent before any node was asked")
        return ProviderLoans([], unreachable + [p for p, _ in holdings], unauthorized)

    results = async_bridge.run(_gather_node_loans(holdings, issuers, budget))

    loans: list[dict[str, Any]] = []
    for (provider_name, _), result in zip(holdings, results, strict=True):
        if isinstance(result, BaseException):
            logger.warning("lenny loans lookup failed for %s: %r", provider_name, result)
            unreachable.append(provider_name)
            continue
        for payload in result:
            if not isinstance(payload, dict):
                logger.info("lenny loans from %s contained a %s where an object was promised", provider_name, type(payload).__name__)
                continue
            if loan := loan_from_node(provider_name, issuers[provider_name], username, payload):
                loans.append(loan)

    return ProviderLoans(loans, unreachable, unauthorized)


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


def authorize_url(
    metadata: dict[str, Any],
    node: dict[str, str],
    state: str,
    challenge: str,
    email: str | None = None,
) -> str:
    """Where to send the patron to authorize a borrow.

    Split out from the handler because these parameters are the whole security
    surface of this leg -- the scopes asked for, the challenge method, and what
    the node is told about the patron -- and a web request is a poor place to
    assert on them.
    """
    params = {
        "response_type": "code",
        "client_id": node["client_id"],
        "redirect_uri": _redirect_uri(),
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": REQUIRED_CODE_CHALLENGE_METHOD,
    }
    if email:
        # RFC 6749 s3.1 extension parameter: the address the patron should be
        # signed in as, so a node need not ask for one they just proved on
        # Open Library.
        #
        # **A node running ArchiveLabs/lenny origin/main ignores this**, which
        # as of 75b0906 is every node in service. Three places drop it:
        # ``authorize`` does not declare the parameter
        # (``lenny/routes/oauth2.py:203-212``); ``_echo``'s allow-list excludes
        # it, so it never reaches the login page (``oauth2.py:294-299``); and
        # the OTP form's email box is filled only from a POST body
        # (``lenny/routes/oauth.py:110-117``, ``post_email``). Sending it is
        # safe regardless: unknown parameters are ignored rather than refused,
        # verified live -- ``/v1/api/oauth2/authorize?client_id=nope`` answers
        # identically with and without it.
        #
        # Node-side support is written and not yet released, so this is
        # unshipped rather than unsupported. Do not describe it as pre-filling
        # anything until a node in service reads it; and even then it pre-fills
        # only. It deliberately does not let the patron skip the email step,
        # because ``/oauth2/authorize`` is an unauthenticated GET and mailing a
        # one-time code on arrival would let a link or a prefetch send one to
        # any address a caller chose.
        #
        # **The cost, which is the part worth a human decision:** this hands
        # the node the patron's email before they consent, including when they
        # abandon the flow. A patron who finishes discloses it anyway, because
        # the node's read gate keys on ``sha256(lowercased email)``, so the
        # delta is the abandoned case -- small, real, and not ours to settle.
        params["login_hint"] = email
    return f"{metadata['authorization_endpoint']}?{urlencode(params)}"


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
                # The bare username, not ``user.key``: it is the key the
                # ``provider_tokens`` row and ``anonymize`` both use.
                "username": user.get_username(),
            },
            expires=STATE_TTL_SECONDS,
        )

        raise web.seeother(authorize_url(metadata, node, state, challenge, user.get_email()))


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
            grant = exchange_code(pending, i.code)
        except Exception:
            logger.exception("lenny token exchange failed for %s", pending["provider_name"])
            return render_error("That library could not complete the loan. Please try again later.")

        # Stored before the loan is created, not after. A loan made with a grant
        # Open Library failed to keep is a live credential at a third-party
        # library that Open Library holds no record of -- it cannot be
        # refreshed, revoked, or shown to the patron. Failing here costs one
        # borrow, which is recoverable; the other order is not.
        try:
            ProviderToken.upsert(pending["username"], pending["provider_name"], grant)
        except Exception:
            logger.exception("lenny grant could not be stored for %s", pending["provider_name"])
            return render_error("That library could not complete the loan. Please try again later.")

        edition_id = int(extract_numeric_id_from_olid(pending["edition_key"]))
        try:
            loan = borrow(pending, grant.access_token, edition_id)
        except LennyBorrowError as e:
            logger.info("lenny borrow refused (%s/%s)", e.status, e.error)
            return render_error(e.message)
        except Exception:
            logger.exception("lenny borrow failed for %s", pending["provider_name"])
            return render_error("That library could not complete the loan. Please try again later.")

        logger.info("lenny loan created on %s for %s", pending["provider_name"], pending["edition_key"])
        return render_borrowed(pending["edition_key"], loan, read_url(pending, loan))


def read_url(pending: dict[str, Any], loan: dict[str, Any]) -> str:
    """Where the patron reads what they just borrowed.

    They authenticated at the node a moment ago, so their browser already holds
    that node's session -- which is what its reader requires, and what an API
    token could not have given them.
    """
    edition_id = loan.get("edition_id") or extract_numeric_id_from_olid(pending["edition_key"])
    return item_read_url(pending["issuer"], edition_id)


def item_read_url(issuer: str, edition_id: Any) -> str:
    """A node's reader URL for one item."""
    return f"{issuer.rstrip('/')}/v1/api/items/{edition_id}/read"


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
