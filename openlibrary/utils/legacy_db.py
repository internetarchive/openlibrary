"""Recover web.py database connections retained by FastAPI threads."""

from functools import wraps

from web.db import DB, Transaction

_installed = False


def _discard_closed_connection(ctx) -> bool:
    if (conn := ctx.get("db")) is None or not getattr(conn, "closed", False):
        return False
    del ctx.db
    ctx.transactions = []
    return True


def install_connection_recovery() -> None:
    """Install once per FastAPI process, including covers and in-process Infobase.

    Unlike web.py, FastAPI does not clear web.py's thread-locals per request.
    Keep healthy connections, but let the next query replace a closed one.
    Never replace a connection while its transaction is still active: the
    transaction must fail and unwind first. No query is retried.

    See https://github.com/internetarchive/openlibrary/issues/14126.
    """
    global _installed
    if _installed:
        return

    original_getctx = DB._getctx
    original_commit = Transaction.commit
    original_rollback = Transaction.rollback

    @wraps(original_getctx)
    def getctx(self):
        if not self._ctx.get("transactions"):
            _discard_closed_connection(self._ctx)
        return original_getctx(self)

    @wraps(original_commit)
    def commit(self):
        try:
            return original_commit(self)
        finally:
            # A failed commit must not leave a dead connection and transaction
            # stack attached to this thread forever.
            _discard_closed_connection(self.ctx)

    @wraps(original_rollback)
    def rollback(self):
        # A disconnected session cannot roll back or use a savepoint. Discard
        # local state without masking the original query error.
        if _discard_closed_connection(self.ctx):
            return None
        try:
            return original_rollback(self)
        finally:
            _discard_closed_connection(self.ctx)

    DB._getctx = getctx
    # The property captures its getter when the class is defined; replacing
    # _getctx alone does not change accesses through self.ctx.
    DB.ctx = property(getctx)
    Transaction.commit = commit
    Transaction.rollback = rollback
    _installed = True
