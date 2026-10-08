"""Encrypted storage for a patron's OAuth token at each trusted book provider.

Open Library holds a patron's grant at a provider (a Lenny node, say) so it can
later borrow on their behalf and read their loans back. A patron may hold
grants at several nodes at once, keyed by ``provider_name``.

**The tokens are encrypted, not hashed.** Open Library *presents* them to the
provider, so they have to be recoverable. A digest would be useless here.
Hashing is right on the provider's side, which verifies, and wrong on this
side, which sends. Encryption reuses the Fernet secret and pattern already used
for the S3 keys -- see :func:`openlibrary.accounts.model.encrypt_token`.

Storage
=======

The store is a seam -- :class:`TokenStore` -- and the backend that ships here is
:class:`CookieTokenStore`: the whole grant set, JSON, Fernet-encrypted into one
cookie in the patron's own browser. Nothing is written server-side, so **this
module needs no table and no migration.**

That is a deliberate choice for a demo, and it buys the demo at a price that is
stated here rather than discovered later:

* **It cannot single-flight a rotating refresh token.** Lenny rotates refresh
  tokens and revokes the whole family when a spent one is presented again. Two
  concurrent requests carry the same cookie, so both hold the same ``R0``;
  whichever refreshes second presents a spent ``R0`` and loses the family. A
  server-side row could be locked ``FOR UPDATE`` and re-read; a cookie cannot
  be, because the winner's ``R1`` exists only in its own HTTP *response* to the
  other tab. :meth:`ProviderToken.get_fresh` therefore narrows the window and
  documents it, but does not close it. **This is a demo-scoped trade-off, not a
  design decision for production.**
* **Cookies are bounded.** Browsers cap a cookie near 4 KiB. Each stored grant
  costs roughly ``len(access_token) + len(refresh_token)`` before a ~1.4x
  Fernet/base64 expansion, so a patron with grants at many nodes will eventually
  lose the oldest. :data:`MAX_COOKIE_BYTES` makes that a logged, deliberate
  eviction rather than a silently truncated cookie.
* **Clearing cookies forgets every grant.** The patron re-authorizes. That is a
  click, not a dead end.

Swapping in a server-side store is one class, not a rewrite: implement
:class:`TokenStore` and call :func:`set_store`. A durable backend should also
add a lock around :meth:`ProviderToken.get_fresh`, which is the one thing the
cookie cannot provide.

See https://github.com/internetarchive/openlibrary/issues/13685 and
``ol-kb/wiki/lenny-oauth.md``.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Protocol

import web

from openlibrary.accounts.model import decrypt_token, encrypt_token

logger = logging.getLogger("openlibrary.provider_tokens")

COOKIE_NAME = "ptok"
"""The cookie holding every provider grant this patron has authorized."""

COOKIE_MAX_AGE = 3600 * 24 * 30
"""Thirty days. A refresh token outlives its access token by a long way, and a
patron who borrowed a month ago should not have to re-authorize to see that the
loan is still open."""

MAX_COOKIE_BYTES = 3800
"""Stay under the ~4 KiB per-cookie cap browsers enforce, with headroom for the
cookie's own name and attributes. See :meth:`CookieTokenStore.save`."""

EXPIRY_SKEW = datetime.timedelta(seconds=60)
"""Treat an access token as expired this far before its stated expiry.

A token that is valid when we check it and expired when the provider sees it is
a failed borrow. Lenny's access tokens last an hour (``wiki/lenny-oauth.md``,
"Lifetimes"), so a minute of headroom costs ~1.7% of each token's life.
"""


def _utcnow() -> datetime.datetime:
    """Timezone-naive UTC now.

    Naive throughout this module, deliberately: the node sends timezone-aware
    timestamps and comparing the two raises ``TypeError`` rather than returning
    a wrong answer, so every aware value is normalised on the way in (see
    :func:`openlibrary.plugins.upstream.lenny._grant_from_payload`).
    """
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


class TokenRefreshFailed(Exception):
    """A refresh failed and the patron's stored grant has been deleted.

    The only correct response is to send the patron back through
    authorization. Do not retry -- see :meth:`ProviderToken.get_fresh`.
    """


class Grant:
    """A patron's decrypted grant at one provider.

    Plaintext credentials, so ``__repr__`` redacts them: these objects travel
    through logs, tracebacks and ``pytest`` assertion output, none of which are
    places a bearer token should turn up.
    """

    __slots__ = ("access_token", "expires", "refresh_token", "scope")

    def __init__(
        self,
        access_token: str,
        refresh_token: str | None = None,
        expires: datetime.datetime | None = None,
        scope: str = "",
    ) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires = expires
        self.scope = scope

    def is_expired(self, now: datetime.datetime | None = None) -> bool:
        """Whether this access token should be treated as spent.

        A grant with no stated expiry is never expired: the provider did not
        say, so guessing would retire a working token.
        """
        if self.expires is None:
            return False
        return (now or _utcnow()) >= self.expires - EXPIRY_SKEW

    def __repr__(self) -> str:
        return f"<Grant access_token=<redacted> refresh_token={'<redacted>' if self.refresh_token else 'None'} expires={self.expires!r} scope={self.scope!r}>"


class Refresher(Protocol):
    """Exchanges a refresh token for a new grant at one provider.

    Raises on any failure. :meth:`ProviderToken.get_fresh` treats every
    exception the same way, because from here a timeout and a rejection are
    indistinguishable and both mean the stored grant is no longer trustworthy.
    """

    def __call__(self, refresh_token: str) -> Grant: ...


class TokenStore(Protocol):
    """Where a patron's grants live.

    Deliberately coarse -- load and save the patron's whole grant set rather
    than one provider's row. A cookie can only be written whole, and the
    coarseness is what keeps the seam honest about that; a finer interface
    would imply a per-provider atomicity the shipped backend does not have.
    """

    def load(self, username: str) -> dict[str, Grant]:
        """Every grant this patron holds, by provider name. ``{}`` if none."""
        ...

    def save(self, username: str, grants: dict[str, Grant]) -> None:
        """Replace this patron's whole grant set."""
        ...


def _encode(grant: Grant) -> dict:
    return {
        "a": grant.access_token,
        "r": grant.refresh_token,
        "e": grant.expires.isoformat() if grant.expires else None,
        "s": grant.scope or "",
    }


def _decode(raw: dict) -> Grant:
    expires = raw.get("e")
    return Grant(
        access_token=raw["a"],
        refresh_token=raw.get("r"),
        expires=datetime.datetime.fromisoformat(expires) if expires else None,
        scope=raw.get("s") or "",
    )


class CookieTokenStore:
    """Grants held in one Fernet-encrypted cookie in the patron's browser.

    The *whole* payload is encrypted as a unit, username included, so nothing
    about which libraries a patron borrows from is readable from the cookie.

    The stored username is checked on read. A cookie outlives a logout, and a
    grant belongs to the patron who authorized it -- so a cookie naming someone
    else reads as no grants at all rather than as this patron's.
    """

    def _read_raw(self) -> str | None:
        try:
            return web.cookies().get(COOKIE_NAME)
        except AttributeError:
            # No request context (a cron, a shell, a unit test that did not
            # ask for one). No cookie is the honest answer, not a crash.
            return None

    def load(self, username: str) -> dict[str, Grant]:
        raw = self._read_raw()
        if not raw:
            return {}
        try:
            payload = json.loads(decrypt_token(raw))
        except Exception:  # noqa: BLE001 - tampered, truncated, or key rotated
            logger.info("discarding an unreadable %s cookie", COOKIE_NAME)
            return {}
        if payload.get("u") != username:
            return {}
        out: dict[str, Grant] = {}
        for provider_name, raw_grant in (payload.get("g") or {}).items():
            try:
                out[provider_name] = _decode(raw_grant)
            except Exception:  # noqa: BLE001 - one bad entry is not all of them
                logger.info("discarding a malformed grant for %s", provider_name)
        return out

    def save(self, username: str, grants: dict[str, Grant]) -> None:
        if not grants:
            self._set("", expires=-1)
            return

        # Newest last, so the oldest grant is the one dropped if the cookie
        # will not fit. Dropping *something* deliberately and saying so beats
        # handing the browser an oversized cookie, which it discards whole --
        # taking the grant the patron just authorized with it.
        ordered = list(grants.items())
        while ordered:
            payload = {"u": username, "g": {name: _encode(g) for name, g in ordered}}
            # No `default=` fallback: a value this cannot serialise must raise
            # here rather than be coerced to its repr, which for a Grant is the
            # *redacted* one -- a cookie that round-trips and holds no tokens.
            token = encrypt_token(json.dumps(payload, separators=(",", ":")))
            if len(token) <= MAX_COOKIE_BYTES:
                self._set(token, expires=COOKIE_MAX_AGE)
                return
            dropped, _ = ordered.pop(0)
            logger.warning(
                "%s cookie full at %d bytes; dropped the %s grant for %s",
                COOKIE_NAME,
                len(token),
                dropped,
                username,
            )
        # Nothing fit, not even the grant just authorized on its own. Louder
        # than the eviction above, because the patron completed a sign-in and
        # has nothing to show for it; evicting an older grant is a trim, this
        # is a failure.
        logger.error(
            "%s: not even one grant fits in %d bytes for %s; stored nothing",
            COOKIE_NAME,
            MAX_COOKIE_BYTES,
            username,
        )
        self._set("", expires=-1)

    def _set(self, value: str, expires: int) -> None:
        web.setcookie(
            COOKIE_NAME,
            value,
            expires=expires,
            secure=_is_https(),
            httponly=True,
            samesite="Lax",
        )


def _is_https() -> bool:
    """Whether to mark the cookie ``Secure``.

    Unconditional ``secure=True`` -- what the ``s3`` cookie does -- means the
    browser silently drops the cookie on ``http://localhost``, which is exactly
    where this flow is demonstrated. Keying on the request's own scheme keeps
    ``Secure`` everywhere it can be honoured and keeps the dev flow working.
    """
    try:
        return web.ctx.get("protocol", "http") == "https"
    except AttributeError:
        return False


_store: TokenStore = CookieTokenStore()


def get_store() -> TokenStore:
    return _store


def set_store(store: TokenStore) -> TokenStore:
    """Swap the backend. Returns the one replaced, so a caller can restore it."""
    global _store
    previous, _store = _store, store
    return previous


class ProviderToken:
    """A patron's grants, over whatever :class:`TokenStore` is installed."""

    @staticmethod
    def get(username: str, provider_name: str) -> Grant | None:
        """The patron's stored grant at a provider, or None.

        Does not check expiry; use :meth:`get_fresh` when you are about to
        present the token.
        """
        return get_store().load(username).get(provider_name)

    @staticmethod
    def get_providers(username: str) -> list[str]:
        """Every provider this patron holds a grant at, for a merged loan lookup."""
        return sorted(get_store().load(username))

    @staticmethod
    def upsert(username: str, provider_name: str, grant: Grant) -> Grant:
        """Store, or replace, the patron's grant at a provider.

        Replacing is right, not merging: a provider issues a whole grant at a
        time, and half of an old one beside half of a new one is not a grant
        either side would honour.
        """
        store = get_store()
        grants = store.load(username)
        # Re-inserted at the end so the most recently authorized grant is the
        # last one evicted when the cookie fills.
        grants.pop(provider_name, None)
        grants[provider_name] = grant
        store.save(username, grants)
        return grant

    @staticmethod
    def delete(username: str, provider_name: str) -> int:
        """Forget the patron's grant at a provider. Returns grants removed."""
        store = get_store()
        grants = store.load(username)
        if grants.pop(provider_name, None) is None:
            return 0
        store.save(username, grants)
        return 1

    @staticmethod
    def delete_all_by_username(username: str) -> int:
        """Forget every grant this patron holds.

        ``OpenLibraryAccount.anonymize`` renames a patron's rows in the tables
        it touches; renaming would be the wrong verb here, because a renamed
        grant still holds a live bearer token for a library the patron has
        left. Deleting is right.

        With the cookie backend this can only clear the grants of the patron
        whose request is in flight -- there is no server-side row for an
        operator to delete on someone else's behalf. A durable backend must
        wire this into ``anonymize``; this one cannot, and that is one of the
        things the cookie gives up.
        """
        store = get_store()
        count = len(store.load(username))
        store.save(username, {})
        return count

    @staticmethod
    def get_fresh(username: str, provider_name: str, refresher: Refresher) -> Grant | None:
        """The patron's grant, refreshed first if its access token has expired.

        Returns None if the patron holds no usable grant at this provider --
        either none is stored, or the access token has expired with no refresh
        token to renew it. Either way the caller must re-authorize.

        Raises :class:`TokenRefreshFailed` if a refresh was attempted and
        failed. The stored grant has been cleared by then.

        **Refresh rotation is destructive on reuse, and the cookie backend
        cannot fully prevent it.** A provider that rotates refresh tokens
        revokes the entire family when a spent one is presented again. Two
        concurrent requests from the same patron carry the same cookie, so both
        read the same refresh token; the second to reach the provider presents
        a spent one. A server-side row could be locked for the whole exchange
        and re-read under that lock, which is the step that makes the second
        flight find the *new* pair instead. A cookie has nowhere to re-read
        from: the new pair exists only in the winner's HTTP response to the
        other tab.

        What is done here instead, which narrows the window without closing it:

        1. The store is re-read immediately before the refresh, so a refresh
           that completed between this request's start and this line is seen.
        2. The new pair is saved before returning, so the spent token stops
           being the stored one as soon as this process can make that true.
        3. A failed refresh clears the grant and is **not** retried.

        On (3), because it reads like a missing feature: a timeout and a
        rejection are indistinguishable from here. The provider may well have
        rotated the token and lost the response on the way back, in which case
        the token we hold is already spent and presenting it again is the
        precise act that destroys the family. Re-authorization costs the patron
        a click; a retry can cost them every loan they hold.
        """
        store = get_store()
        grants = store.load(username)
        grant = grants.get(provider_name)
        if grant is None:
            return None

        if not grant.is_expired():
            return grant

        if not grant.refresh_token:
            return None

        try:
            refreshed = refresher(grant.refresh_token)
        except Exception as exc:
            grants.pop(provider_name, None)
            store.save(username, grants)
            logger.info("cleared %s grant for %s after a failed refresh", provider_name, username)
            raise TokenRefreshFailed(f"refresh failed for {provider_name}; grant cleared") from exc

        grants[provider_name] = refreshed
        store.save(username, grants)
        return refreshed
