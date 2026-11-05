"""Recover web.py database connections that FastAPI keeps between requests."""

from functools import wraps

from web import DB

_installed = False


def install_connection_recovery() -> None:
    """Drop a thread's web.py connection once it is closed, so the next query reconnects.

    web.py clears its thread-locals after every request; FastAPI doesn't, so without
    this a dropped connection fails every later request on that thread. web.py only
    calls ``ctx.commit``/``ctx.rollback`` for the outermost transaction, so a
    connection lost inside a savepoint keeps failing until the outer transaction
    unwinds. Nothing is retried. See https://github.com/internetarchive/openlibrary/issues/14126.
    """
    global _installed
    if _installed:
        return
    original_load_context = DB._load_context

    @wraps(original_load_context)
    def load_context(self, ctx):
        original_load_context(self, ctx)
        commit, rollback = ctx.commit, ctx.rollback

        def closed() -> bool:
            return bool(getattr(ctx.get("db"), "closed", False))

        def discard_if_closed():
            if closed():
                del ctx.db
                ctx.transactions = []

        def recovering_commit(unload=True):
            try:
                commit(unload)
            finally:
                discard_if_closed()

        def recovering_rollback():
            try:
                # Rolling back a closed connection would raise and mask the original
                # error; the server has already discarded the transaction.
                if not closed():
                    rollback()
            finally:
                discard_if_closed()

        ctx.commit, ctx.rollback = recovering_commit, recovering_rollback

    DB._load_context = load_context
    _installed = True
