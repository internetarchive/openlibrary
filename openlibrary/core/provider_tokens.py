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

Where the grants live is a seam, :class:`TokenStore`, with two backends:

:class:`DbTokenStore`
    **The default, and the one that ships.** One row per
    ``(username, provider_name)`` in ``provider_tokens``, each token Fernet
    encrypted at rest, with :meth:`ProviderToken.get_fresh` single-flighted by
    ``SELECT ... FOR UPDATE`` on the patron's own row. The table is declared in
    ``openlibrary/core/schema.sql``.

:class:`CookieTokenStore`
    The whole grant set, JSON, Fernet-encrypted into one cookie in the patron's
    own browser. Nothing server-side, so it needs no table -- which is what
    makes it useful for a demo or a test against a database that has not had
    the DDL applied yet. **It is not the default and must not be read as one.**

``schema.sql`` is applied at database *init* only, and Open Library has no
DDL-migration mechanism: every script under ``scripts/migrations/`` migrates
data, not schema. So an existing deployment -- production, or
``testing.openlibrary.org`` -- gets this table when an operator runs the
``CREATE TABLE`` by hand, and not before. Until they have,
:class:`DbTokenStore` raises on a missing relation, which is the correct and
visible failure; see the deploy steps on the pull request.

What the cookie backend gives up
================================

Stated here rather than discovered later, because the cookie is still a
selectable backend and the differences are not cosmetic:

* **It cannot single-flight a rotating refresh token.** Lenny rotates refresh
  tokens and revokes the whole family when a spent one is presented again. Two
  concurrent requests carry the same cookie, so both hold the same ``R0``;
  whichever refreshes second presents a spent ``R0`` and loses the family. A
  server-side row can be locked ``FOR UPDATE`` and re-read; a cookie cannot be,
  because the winner's ``R1`` exists only in its own HTTP *response* to the
  other tab. :meth:`CookieTokenStore.get_fresh` therefore narrows the window
  and documents it; :meth:`DbTokenStore.get_fresh` closes it.
* **Cookies are bounded.** Browsers cap a cookie near 4 KiB, so a patron with
  grants at many nodes will eventually lose the oldest.
  :data:`MAX_COOKIE_BYTES` makes that a logged, deliberate eviction rather than
  a silently truncated cookie.
* **``delete_all_by_username`` can only reach the patron whose request is in
  flight.** There is no server-side row for an operator to delete on someone
  else's behalf.
* **Clearing cookies forgets every grant.** The patron re-authorizes. That is a
  click, not a dead end.

See https://github.com/internetarchive/openlibrary/issues/13685 and
``ol-kb/wiki/lenny-oauth.md``.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import TYPE_CHECKING, Protocol

import web

from openlibrary.accounts.model import decrypt_token, encrypt_token

from . import db

if TYPE_CHECKING:
    from web.db import DB

logger = logging.getLogger("openlibrary.provider_tokens")

TABLENAME = "provider_tokens"

COOKIE_NAME = "ptok"
"""The cookie :class:`CookieTokenStore` holds a patron's grants in."""

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
    """Timezone-naive UTC now, matching the table's ``timestamp`` columns.

    Naive throughout this module, deliberately: the node sends timezone-aware
    timestamps and comparing the two raises ``TypeError`` rather than returning
    a wrong answer, so every aware value is normalised on the way in (see
    :func:`openlibrary.plugins.upstream.lenny._grant_from_payload`).
    """
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


class TokenRefreshFailed(Exception):
    """A refresh failed and the patron's stored grant has been deleted.

    The only correct response is to send the patron back through
    authorization. Do not retry -- see :meth:`DbTokenStore.get_fresh`.
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
    """Exchanges a refresh token with the provider for a new :class:`Grant`.

    Supplied by the caller so this module holds no provider HTTP client. Under
    :class:`DbTokenStore` it is called with the lock on the patron's row held,
    so it **must** impose its own network timeout: whatever it waits for, the
    row waits for too.

    And do not call :meth:`ProviderToken.get_fresh` on a worker thread to get
    several providers refreshed in parallel. ``web.db.DB`` keeps its connection
    in a ``threadeddict`` and ``_unload_context`` only runs when pooling is on,
    which it is not here (no ``dbutils``), so every new thread that reaches
    :func:`openlibrary.core.db.get_db` opens a Postgres connection that is never
    released. Resolve tokens sequentially and put a deadline over the phase --
    ``openlibrary/plugins/upstream/lenny.py`` does this for #13687.

    Raises on any failure. ``get_fresh`` treats every exception the same way,
    because from here a timeout and a rejection are indistinguishable and both
    mean the stored grant is no longer trustworthy.
    """

    def __call__(self, refresh_token: str) -> Grant: ...


class TokenStore(Protocol):
    """Where a patron's grants live.

    The whole operation set, not just load and save: ``get_fresh`` is on the
    seam because single-flighting a rotating refresh token is the one thing the
    two backends do *differently*, and expressing it in terms of a coarser
    load/save pair would quietly impose the cookie's limitation on the table.
    """

    def get(self, username: str, provider_name: str) -> Grant | None:
        """The patron's grant at a provider, or None. Does not check expiry."""
        ...

    def get_providers(self, username: str) -> list[str]:
        """Every provider this patron holds a grant at, sorted."""
        ...

    def upsert(self, username: str, provider_name: str, grant: Grant) -> Grant:
        """Store, or replace, the patron's grant at a provider."""
        ...

    def delete(self, username: str, provider_name: str) -> int:
        """Forget one grant. Returns the number removed (0 or 1)."""
        ...

    def delete_all_by_username(self, username: str) -> int:
        """Forget every grant this patron holds. Returns the number removed."""
        ...

    def get_fresh(self, username: str, provider_name: str, refresher: Refresher) -> Grant | None:
        """The patron's grant, refreshed first if its access token has expired."""
        ...


class DbTokenStore:
    """Grants in the ``provider_tokens`` table, one row per patron per provider.

    The shipped default. Requires the table; see the module docstring on how an
    existing deployment gets it.
    """

    @staticmethod
    def _decrypt(row: web.storage) -> Grant:
        return Grant(
            access_token=decrypt_token(row.access_token),
            refresh_token=decrypt_token(row.refresh_token) if row.refresh_token else None,
            expires=row.expires,
            scope=row.scope or "",
        )

    def get(self, username: str, provider_name: str) -> Grant | None:
        rows = list(
            db.query(
                f"SELECT * FROM {TABLENAME} WHERE username=$username AND provider_name=$provider_name",
                vars={"username": username, "provider_name": provider_name},
            )
        )
        return self._decrypt(rows[0]) if rows else None

    def get_providers(self, username: str) -> list[str]:
        rows = db.query(
            f"SELECT provider_name FROM {TABLENAME} WHERE username=$username ORDER BY provider_name",
            vars={"username": username},
        )
        return [row.provider_name for row in rows]

    def upsert(self, username: str, provider_name: str, grant: Grant) -> Grant:
        with db.transaction():
            self._write(db.get_db(), username, provider_name, grant)
        return grant

    @staticmethod
    def _write(oldb: DB, username: str, provider_name: str, grant: Grant) -> None:
        oldb.query(
            f"""
            INSERT INTO {TABLENAME}
                (username, provider_name, access_token, refresh_token, expires, scope, updated)
            VALUES
                ($username, $provider_name, $access_token, $refresh_token, $expires, $scope, $updated)
            ON CONFLICT (username, provider_name) DO UPDATE SET
                access_token = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token,
                expires = EXCLUDED.expires,
                scope = EXCLUDED.scope,
                updated = EXCLUDED.updated
            """,
            vars={
                "username": username,
                "provider_name": provider_name,
                "access_token": encrypt_token(grant.access_token),
                "refresh_token": encrypt_token(grant.refresh_token) if grant.refresh_token else None,
                "expires": grant.expires,
                "scope": grant.scope,
                "updated": _utcnow(),
            },
        )

    def delete(self, username: str, provider_name: str) -> int:
        with db.transaction():
            return self._delete(db.get_db(), username, provider_name)

    @staticmethod
    def _delete(oldb: DB, username: str, provider_name: str) -> int:
        return oldb.delete(
            TABLENAME,
            where="username=$username AND provider_name=$provider_name",
            vars={"username": username, "provider_name": provider_name},
        )

    def delete_all_by_username(self, username: str) -> int:
        """Forget every grant this patron holds.

        **Nothing calls this yet, and something must.**
        ``OpenLibraryAccount.anonymize`` renames a patron's rows in every other
        table it touches; renaming is the wrong verb here, because a renamed row
        still holds a live bearer token for a library the patron has left.
        Deleting is right.

        It is still not wired into ``anonymize``, and deliberately so: adding
        the ``CREATE TABLE`` to ``schema.sql`` does not put the table in a
        database that already exists, so on production today ``anonymize`` would
        raise on a missing relation and take account deletion down with it. It
        goes in once an operator has run the DDL -- which is a one-line follow-up
        and is on the pull request's next-steps list, not a design question.
        """
        with db.transaction():
            return db.get_db().delete(TABLENAME, where="username=$username", vars={"username": username})

    @staticmethod
    def _select_locked(oldb: DB, username: str, provider_name: str) -> web.storage | None:
        """Read the patron's row, holding an exclusive lock on it until commit.

        ``FOR UPDATE`` is what makes :meth:`get_fresh` single-flight across
        Open Library's several web processes, so an in-process threading lock
        would not do. Precedent for the clause: ``openlibrary/data/db.py:143``.

        SQLite has no ``FOR UPDATE``. The tests that exercise the locking itself
        run against Postgres and skip elsewhere; the tests that run everywhere
        exercise the protocol built on top of it.
        """
        locking = " FOR UPDATE" if getattr(oldb, "dbname", None) == "postgres" else ""
        rows = list(
            oldb.query(
                f"SELECT * FROM {TABLENAME} WHERE username=$username AND provider_name=$provider_name{locking}",
                vars={"username": username, "provider_name": provider_name},
            )
        )
        return rows[0] if rows else None

    def get_fresh(self, username: str, provider_name: str, refresher: Refresher) -> Grant | None:
        """The patron's grant, refreshed first if its access token has expired.

        Returns None if the patron holds no usable grant at this provider --
        either none is stored, or the access token has expired with no refresh
        token to renew it. Either way the caller must re-authorize.

        Raises :class:`TokenRefreshFailed` if a refresh was attempted and
        failed. The stored grant has been deleted by then.

        **Refresh rotation is destructive on reuse.** A provider that rotates
        refresh tokens revokes the entire token family when a spent one is
        presented again, which logs the patron out with no error anyone can
        trace. Three things follow, and this method is where all three live:

        1. The new pair is written in the *same* transaction that consumed the
           old one, so there is no window in which the spent token is the
           stored one.
        2. The row is locked for the whole exchange, so a patron's second tab
           blocks rather than presenting the same refresh token. It then
           re-reads under the lock, finds the grant already fresh, and returns
           it without touching the network.
        3. A failed refresh deletes the grant. It is **not** retried.

        On (3), because it reads like a missing feature: a timeout and a
        rejection are indistinguishable from here. The provider may well have
        rotated the token and lost the response on the way back, in which case
        the token we hold is already spent and presenting it again is the
        precise act that destroys the family. Re-authorization costs the patron
        a click; a retry can cost them every loan they hold.

        Optimistic concurrency -- write only if ``updated`` has not moved --
        does not substitute for the lock: the damage is done by the network
        call, which happens before any write.

        **The lock is taken on every call, including the common one where the
        token is live and nothing is written. That is deliberate and measured,
        not an oversight.** The obvious alternative is to read without the lock
        and take it only when a refresh looks necessary, which would make the
        read-only path lock-free. Measured against ``postgres:18.3``, on one
        patron's row:

        * uncontended, live token: ``0.446ms`` with the lock, ``0.375ms``
          without. The rewrite recovers **0.071ms** per call.
        * contended -- a refresh holding the lock for 250ms while a second
          caller arrives 20ms in: ``233.6ms`` with the lock, ``244.2ms``
          without.

        The contended case does not improve because it cannot. A caller
        arriving mid-refresh reads, without the lock, the *pre-refresh* row --
        which is expired, since that is why the first caller is refreshing --
        so it concludes a refresh is needed and queues on the same lock for the
        same duration, having paid for an extra query first. So the rewrite buys
        71 microseconds on the path that is already fast and nothing on the path
        that is slow, in exchange for a second decision point whose safety
        depends on a later reader knowing the unlocked read must be discarded.
        That is the trade that produces check-then-act, and check-then-act here
        is what destroys token families.

        At page-render frequency (#13687 reads this for the patron's loans page)
        eight threads contending on a single row sustained ~3,400 calls/s at a
        p95 of 2.6ms, which is far past any real load on one patron's row.
        """
        oldb = db.get_db()
        failure: Exception
        with oldb.transaction():
            row = self._select_locked(oldb, username, provider_name)
            if row is None:
                return None

            grant = self._decrypt(row)
            # Read under the lock, never before it: another flight may have
            # refreshed while this one waited, in which case its stored pair is
            # live and the one this caller started with is spent.
            if not grant.is_expired():
                return grant

            if not grant.refresh_token:
                return None

            try:
                refreshed = refresher(grant.refresh_token)
            except Exception as exc:  # noqa: BLE001 - every failure means the same thing
                self._delete(oldb, username, provider_name)
                failure = exc
            else:
                self._write(oldb, username, provider_name, refreshed)
                return refreshed

        # Outside the `with`, so the delete above is committed before this
        # raises.
        logger.info("cleared %s grant for %s after a failed refresh", provider_name, username)
        raise TokenRefreshFailed(f"refresh failed for {provider_name}; grant cleared") from failure


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

    **Not the default.** Install it with :func:`set_store` where there is no
    ``provider_tokens`` table to write to -- a demo, or a dev container whose
    database predates the DDL. The module docstring lists what it gives up.

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
        """Every grant this patron holds, by provider name. ``{}`` if none."""
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
        """Replace this patron's whole grant set."""
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

    def get(self, username: str, provider_name: str) -> Grant | None:
        return self.load(username).get(provider_name)

    def get_providers(self, username: str) -> list[str]:
        return sorted(self.load(username))

    def upsert(self, username: str, provider_name: str, grant: Grant) -> Grant:
        grants = self.load(username)
        # Re-inserted at the end so the most recently authorized grant is the
        # last one evicted when the cookie fills.
        grants.pop(provider_name, None)
        grants[provider_name] = grant
        self.save(username, grants)
        return grant

    def delete(self, username: str, provider_name: str) -> int:
        grants = self.load(username)
        if grants.pop(provider_name, None) is None:
            return 0
        self.save(username, grants)
        return 1

    def delete_all_by_username(self, username: str) -> int:
        """Forget every grant this patron holds.

        This backend can only reach the patron whose request is in flight:
        there is no server-side row for an operator to delete on someone else's
        behalf, so ``anonymize`` cannot be served from here at all.
        """
        count = len(self.load(username))
        self.save(username, {})
        return count

    def get_fresh(self, username: str, provider_name: str, refresher: Refresher) -> Grant | None:
        """The patron's grant, refreshed first if its access token has expired.

        **Refresh rotation is destructive on reuse, and this backend cannot
        fully prevent it.** Two concurrent requests from the same patron carry
        the same cookie, so both read the same refresh token; the second to
        reach the provider presents a spent one and loses the family. A
        server-side row can be locked for the whole exchange and re-read under
        that lock, which is the step that makes the second flight find the
        *new* pair instead -- see :meth:`DbTokenStore.get_fresh`. A cookie has
        nowhere to re-read from: the new pair exists only in the winner's HTTP
        response to the other tab.

        What is done here instead, which narrows the window without closing it:

        1. The cookie is re-read immediately before the refresh, so a refresh
           that completed between this request's start and this line is seen.
        2. The new pair is saved before returning, so the spent token stops
           being the stored one as soon as this process can make that true.
        3. A failed refresh clears the grant and is **not** retried.
        """
        grants = self.load(username)
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
            self.save(username, grants)
            logger.info("cleared %s grant for %s after a failed refresh", provider_name, username)
            raise TokenRefreshFailed(f"refresh failed for {provider_name}; grant cleared") from exc

        grants[provider_name] = refreshed
        self.save(username, grants)
        return refreshed


def _is_https() -> bool:
    """Whether to mark the cookie ``Secure``.

    Unconditional ``secure=True`` -- what the ``s3`` cookie does -- means the
    browser silently drops the cookie on ``http://localhost``, which is exactly
    where this flow is demonstrated. Keying on the request's own scheme keeps
    ``Secure`` everywhere it can be honoured and keeps the dev flow working.
    ``testing.openlibrary.org`` is https, so it is set there.
    """
    try:
        return web.ctx.get("protocol", "http") == "https"
    except AttributeError:
        return False


_store: TokenStore = DbTokenStore()


def get_store() -> TokenStore:
    return _store


def set_store(store: TokenStore) -> TokenStore:
    """Swap the backend. Returns the one replaced, so a caller can restore it."""
    global _store
    previous, _store = _store, store
    return previous


class ProviderToken:
    """A patron's grants, over whatever :class:`TokenStore` is installed.

    The facade every caller uses. It holds no storage logic of its own, so a
    swap of backend changes behaviour in exactly one place.
    """

    @staticmethod
    def get(username: str, provider_name: str) -> Grant | None:
        """The patron's stored grant at a provider, or None.

        Does not check expiry; use :meth:`get_fresh` when you are about to
        present the token.
        """
        return get_store().get(username, provider_name)

    @staticmethod
    def get_providers(username: str) -> list[str]:
        """Every provider this patron holds a grant at, for a merged loan lookup."""
        return get_store().get_providers(username)

    @staticmethod
    def upsert(username: str, provider_name: str, grant: Grant) -> Grant:
        """Store, or replace, the patron's grant at a provider.

        Replacing is right, not merging: a provider issues a whole grant at a
        time, and half of an old one beside half of a new one is not a grant
        either side would honour.
        """
        return get_store().upsert(username, provider_name, grant)

    @staticmethod
    def delete(username: str, provider_name: str) -> int:
        """Forget the patron's grant at a provider. Returns grants removed."""
        return get_store().delete(username, provider_name)

    @staticmethod
    def delete_all_by_username(username: str) -> int:
        """Forget every grant this patron holds.

        ``OpenLibraryAccount.anonymize`` renames a patron's rows in the tables
        it touches; renaming would be the wrong verb here, because a renamed
        grant still holds a live bearer token for a library the patron has
        left. Deleting is right.
        """
        return get_store().delete_all_by_username(username)

    @staticmethod
    def get_fresh(username: str, provider_name: str, refresher: Refresher) -> Grant | None:
        """The patron's grant, refreshed first if its access token has expired.

        Returns None if the patron holds no usable grant at this provider --
        either none is stored, or the access token has expired with no refresh
        token to renew it. Either way the caller must re-authorize.

        Raises :class:`TokenRefreshFailed` if a refresh was attempted and
        failed; the stored grant has been cleared by then, and it must not be
        retried. Which backend is installed decides whether two concurrent
        flights are single-flighted -- see :meth:`DbTokenStore.get_fresh` and
        :meth:`CookieTokenStore.get_fresh`.
        """
        return get_store().get_fresh(username, provider_name, refresher)
