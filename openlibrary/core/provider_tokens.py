"""Encrypted storage for a patron's OAuth token at each trusted book provider.

Open Library holds a patron's grant at a provider (a Lenny node, say) so it can
later borrow on their behalf and read their loans back. One row per
``(username, provider_name)``; a patron may hold grants at several nodes.

**The tokens are encrypted, not hashed.** Open Library *presents* them to the
provider, so they have to be recoverable. A digest would be useless here.
Hashing is right on the provider's side, which verifies, and wrong on this
side, which sends. Encryption reuses the Fernet secret and pattern already used
for the S3 keys -- see :func:`openlibrary.accounts.model.encrypt_token`.

The hazard this module exists to contain is refresh rotation: see
:meth:`ProviderToken.get_fresh`.

See https://github.com/internetarchive/openlibrary/issues/13685 and
``ol-kb/wiki/lenny-oauth.md``.
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Protocol

from openlibrary.accounts.model import decrypt_token, encrypt_token

from . import db

if TYPE_CHECKING:
    import web
    from web.db import DB

logger = logging.getLogger("openlibrary.provider_tokens")

TABLENAME = "provider_tokens"

EXPIRY_SKEW = datetime.timedelta(seconds=60)
"""Treat an access token as expired this far before its stated expiry.

A token that is valid when we check it and expired when the provider sees it is
a failed borrow. Lenny's access tokens last an hour (``wiki/lenny-oauth.md``,
"Lifetimes"), so a minute of headroom costs ~1.7% of each token's life.
"""


def _utcnow() -> datetime.datetime:
    """Timezone-naive UTC now, matching the table's ``timestamp`` columns."""
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
        """Has the access token expired, or is it about to?

        A grant with no stated expiry is treated as live: a provider that does
        not say when a token dies has not given us grounds to throw it away.
        """
        if self.expires is None:
            return False
        return self.expires - EXPIRY_SKEW <= (now or _utcnow())

    def __repr__(self) -> str:
        refresh = "<redacted>" if self.refresh_token else None
        return f"Grant(access_token=<redacted>, refresh_token={refresh}, expires={self.expires!r}, scope={self.scope!r})"


class Refresher(Protocol):
    """Exchanges a refresh token with the provider for a new :class:`Grant`.

    Supplied by the caller so this module holds no provider HTTP client. It is
    called with the lock on the patron's row held, so it **must** impose its own
    network timeout: whatever it waits for, the row waits for too.

    And do not call :meth:`ProviderToken.get_fresh` on a worker thread to get
    several providers refreshed in parallel. ``web.db.DB`` keeps its connection
    in a ``threadeddict`` and ``_unload_context`` only runs when pooling is on,
    which it is not here (no ``dbutils``), so every new thread that reaches
    :func:`openlibrary.core.db.get_db` opens a Postgres connection that is never
    released. Resolve tokens sequentially and put a deadline over the phase --
    ``openlibrary/plugins/upstream/lenny.py`` does this for #13687.
    """

    def __call__(self, refresh_token: str) -> Grant: ...


class ProviderToken:
    """The ``provider_tokens`` table."""

    @staticmethod
    def _decrypt(row: web.storage) -> Grant:
        return Grant(
            access_token=decrypt_token(row.access_token),
            refresh_token=decrypt_token(row.refresh_token) if row.refresh_token else None,
            expires=row.expires,
            scope=row.scope or "",
        )

    @staticmethod
    def get(username: str, provider_name: str) -> Grant | None:
        """The patron's stored grant at a provider, decrypted, or None.

        Does not check expiry; use :meth:`get_fresh` when you are about to
        present the token.
        """
        rows = list(
            db.query(
                f"SELECT * FROM {TABLENAME} WHERE username=$username AND provider_name=$provider_name",
                vars={"username": username, "provider_name": provider_name},
            )
        )
        return ProviderToken._decrypt(rows[0]) if rows else None

    @staticmethod
    def get_providers(username: str) -> list[str]:
        """Every provider this patron holds a grant at, for a merged loan lookup."""
        rows = db.query(
            f"SELECT provider_name FROM {TABLENAME} WHERE username=$username ORDER BY provider_name",
            vars={"username": username},
        )
        return [row.provider_name for row in rows]

    @staticmethod
    def upsert(username: str, provider_name: str, grant: Grant) -> Grant:
        """Store, or replace, the patron's grant at a provider.

        Replacing is right, not merging: a provider issues a whole grant at a
        time, and half of an old one beside half of a new one is not a grant
        either side would honour.
        """
        with db.transaction():
            ProviderToken._write(db.get_db(), username, provider_name, grant)
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

    @staticmethod
    def delete(username: str, provider_name: str) -> int:
        """Forget the patron's grant at a provider. Returns rows deleted."""
        with db.transaction():
            return ProviderToken._delete(db.get_db(), username, provider_name)

    @staticmethod
    def _delete(oldb: DB, username: str, provider_name: str) -> int:
        return oldb.delete(
            TABLENAME,
            where="username=$username AND provider_name=$provider_name",
            vars={"username": username, "provider_name": provider_name},
        )

    @staticmethod
    def delete_all_by_username(username: str) -> int:
        """Forget every grant this patron holds.

        **Nothing calls this yet, and something must.**
        ``OpenLibraryAccount.anonymize`` (``openlibrary/accounts/model.py:485-493``)
        renames a patron's rows in every other table it touches; renaming is
        the wrong verb here, because a renamed row still holds a live bearer
        token for a library the patron has left. Deleting is right.

        It is not wired up in this commit because the table does not exist yet
        -- ``anonymize`` would raise on a missing relation. It goes in with the
        migration.
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

    @staticmethod
    def get_fresh(username: str, provider_name: str, refresher: Refresher) -> Grant | None:
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
            row = ProviderToken._select_locked(oldb, username, provider_name)
            if row is None:
                return None

            grant = ProviderToken._decrypt(row)
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
                ProviderToken._delete(oldb, username, provider_name)
                failure = exc
            else:
                ProviderToken._write(oldb, username, provider_name, refreshed)
                return refreshed

        # Outside the `with`, so the delete above is committed before this
        # raises.
        logger.info("cleared %s grant for %s after a failed refresh", provider_name, username)
        raise TokenRefreshFailed(f"refresh failed for {provider_name}; grant cleared") from failure
