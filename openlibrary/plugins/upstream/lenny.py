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

import base64
import datetime
import hashlib
import logging
import secrets
from typing import Any
from urllib.parse import urlencode

import requests
import web

from infogami import config
from infogami.utils import delegate
from infogami.utils.view import add_flash_message
from openlibrary.accounts import get_current_user
from openlibrary.core import cache
from openlibrary.core.acquisitions import Acquisition
from openlibrary.core.jinja import render_jinja_template
from openlibrary.core.provider_tokens import (
    Grant,
    ProviderToken,
    Refresher,
    TokenRefreshFailed,
)
from openlibrary.i18n import gettext as _
from openlibrary.utils import extract_numeric_id_from_olid

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


def node_display_name(provider_name: str, node: dict[str, str]) -> str:
    """What to call this node to a patron.

    From the node's own config, because a node *is* a library: "Archive Labs
    Lenny" names one operator, not the software, and a second node will want
    its own name in the same sentence. Falls back to the feed's provider name,
    so an operator who set no ``name`` gets "Lenny" rather than a sentence with
    a hole in it.
    """
    return node.get("name") or provider_name.replace("_", " ").title()


def borrow_path(edition_olid: str) -> str:
    """Where a borrow of this edition starts, as one definition.

    :class:`lenny_borrow` serves it, :func:`mediated_borrow` hands it to the
    interstitial, and the handler hands it back to itself through the sign-in
    redirect. Three spellings of one path is how one of them ends up wrong.
    """
    return f"/borrow/lenny/{edition_olid}"


def mediated_borrow(edition_key: str) -> tuple[str, str] | None:
    """``(url, library_name)`` for a borrow Open Library runs itself, else None.

    ``url`` is an Open Library path -- :class:`lenny_borrow`, which turns a
    click into an authorization request -- so the patron's browser only ever
    navigates to Open Library and to the node holding the book.

    None means no *configured* node lends this edition. A harvested row can
    name a Lenny node Open Library holds no credentials for, and then there is
    no handshake to run: the caller falls back to the feed's own URL, which is
    the node's sign-in and completes a loan with nothing built on this side
    (#13686).
    """
    if not nodes():
        # Checked before `node_for_edition`, which reads the acquisitions
        # table whether or not any node is configured. Every borrow click on
        # every provider reaches this function, and on an Open Library with no
        # Lenny node that query cannot return a usable answer.
        return None
    if not (found := node_for_edition(edition_key)):
        return None
    provider_name, node = found
    return borrow_path(edition_key.rsplit("/", maxsplit=1)[-1]), node_display_name(provider_name, node)


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
            # Back here, not to the book: returning them to the book page drops
            # the thing they asked for and they have to find the button again.
            # It matters more inside the popup (#13688), where finishing on the
            # book page means finishing in a 520px window -- but it was already
            # a lost click in a tab.
            raise web.seeother(f"/account/login?redirect={borrow_path(edition_olid)}")
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
            return render_error("The library did not authorize this loan.", pending["edition_key"])

        try:
            check_issuer(pending, i.iss)
        except ValueError:
            logger.exception("lenny callback failed the issuer check")
            return render_error("That borrow request could not be verified. Please try again.", pending["edition_key"])

        if not i.code:
            return render_error("That borrow request expired. Please try borrowing again.", pending["edition_key"])

        try:
            grant = exchange_code(pending, i.code)
        except Exception:
            logger.exception("lenny token exchange failed for %s", pending["provider_name"])
            return render_error("That library could not complete the loan. Please try again later.", pending["edition_key"])

        # Stored before the loan is created, not after. A loan made with a grant
        # Open Library failed to keep is a live credential at a third-party
        # library that Open Library holds no record of -- it cannot be
        # refreshed, revoked, or shown to the patron. Failing here costs one
        # borrow, which is recoverable; the other order is not.
        try:
            ProviderToken.upsert(pending["username"], pending["provider_name"], grant)
        except Exception:
            logger.exception("lenny grant could not be stored for %s", pending["provider_name"])
            return render_error("That library could not complete the loan. Please try again later.", pending["edition_key"])

        edition_id = int(extract_numeric_id_from_olid(pending["edition_key"]))
        try:
            loan = borrow(pending, grant.access_token, edition_id)
        except LennyBorrowError as e:
            logger.info("lenny borrow refused (%s/%s)", e.status, e.error)
            return render_error(e.message, pending["edition_key"])
        except Exception:
            logger.exception("lenny borrow failed for %s", pending["provider_name"])
            return render_error("That library could not complete the loan. Please try again later.", pending["edition_key"])

        logger.info("lenny loan created on %s for %s", pending["provider_name"], pending["edition_key"])
        # The node's config, not `pending`: `state` is a ten-minute-old
        # snapshot of the credentials this flow needed, and a display name is
        # the one thing here that an operator may have corrected since.
        library = node_display_name(pending["provider_name"], nodes().get(pending["provider_name"], {}))
        return render_borrowed(pending["edition_key"], loan, read_url(pending, loan), library)


def read_url(pending: dict[str, Any], loan: dict[str, Any]) -> str:
    """Where the patron reads what they just borrowed.

    They authenticated at the node a moment ago, so their browser already holds
    that node's session -- which is what its reader requires, and what an API
    token could not have given them.
    """
    issuer = pending["issuer"].rstrip("/")
    edition_id = loan.get("edition_id") or extract_numeric_id_from_olid(pending["edition_key"])
    return f"{issuer}/v1/api/items/{edition_id}/read"


POPUP_MESSAGE_TYPE = "ol-provider-borrow"
"""The ``postMessage`` type the callback sends to the page that opened the popup.

Shared with ``openlibrary/plugins/openlibrary/js/provider_borrow_popup.js``,
which drops any message whose ``type`` is not this string. Renaming it on one
side only leaves the loan created and the book page never refreshed, which is
the failure the patron sees as "nothing happened".
"""


def _popup_page(**kwargs: Any) -> delegate.RawText:
    """One of the popup's two endings, as a page with no site layout.

    ``RawText`` rather than a returned string, and the reason is not weight:
    it is the only way the flash message survives the popup.

    ``flash_processor`` writes the flash cookie only when ``web.ctx.flash``
    differs from what arrived in the request, and ``get_flash_messages()``
    *drains* ``web.ctx.flash`` as a side effect of reading it
    (``vendor/infogami/infogami/utils/flash.py:18-21, 42-50``). The site layout
    calls it on every render (``openlibrary/core/layout.py:101-112``). So a
    page that renders the layout shows the message here -- inside a window that
    is about to close -- and leaves ``web.ctx.flash`` empty, matching the empty
    request value, so no cookie is written and the page that opened the popup
    never hears about the loan. Skipping ``render_site`` is what keeps the
    message for the opener (``utils/delegate.py:89-92``).

    The popup is also the one place in Open Library where dropping the layout
    costs nothing: it is 520px wide, it closes on its own, and the patron is
    looking at the real Open Library page behind it the whole time.
    """
    return delegate.RawText(render_jinja_template("borrow/provider_popup_result.html.jinja", **kwargs))


def render_error(message: str, return_url: str = "/") -> delegate.RawText:
    """The popup's failure page. See the template for why it is not a bare 303.

    No flash, unlike :func:`render_borrowed`, and the asymmetry is the point:
    this page stays on screen to be read, so flashing the same sentence onto
    the page behind it would show the patron one failure twice.
    """
    return _popup_page(
        ok=False,
        message=message,
        return_url=return_url,
        read_url=None,
        due=None,
        message_type=POPUP_MESSAGE_TYPE,
    )


def render_borrowed(edition_key: str, loan: dict[str, Any], read: str, library: str) -> delegate.RawText:
    """The popup's success page: it closes itself and refreshes the book page.

    The flash is the confirmation the patron actually reads, because the popup
    closes before it can be read there. It is plain text on purpose -- the
    layout renders it escaped (``site.html.jinja``), so it cannot carry the
    "Read it now" link.

    Which is why ``read`` is kept on this page rather than dropped: it is the
    only route to the book on the paths where there is no opener to refresh --
    no JavaScript, or the CTA's ``target="_blank"`` fallback, which has no
    opener by construction. Open Library's own button cannot serve as that
    route yet. It renders from the harvested ``acquisitions`` row and a loan
    does not touch that row, so the refreshed book page still says "Borrow".
    Closing that gap needs per-patron loan state on the book page and is not
    this module's to fix; see the PR for #13688.
    """
    if due := loan.get("due_at"):
        add_flash_message("info", _("Borrowed from %(library)s. Your loan is due %(due)s.", library=library, due=due))
    else:
        add_flash_message("info", _("Borrowed from %(library)s.", library=library))
    return _popup_page(
        ok=True,
        message=None,
        return_url=edition_key,
        read_url=read,
        due=due,
        message_type=POPUP_MESSAGE_TYPE,
    )
