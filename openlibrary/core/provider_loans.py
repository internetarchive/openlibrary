"""The patron's provider loans, shaped for the book page's CTA.

``lenny.provider_loans`` is built for the loans page, where spending its whole
``LOANS_DEADLINE_SECONDS`` budget is acceptable. The book page cannot afford
that: it is a hot render path, and one slow node must not delay it.

So the book page never fetches inline. It reads memcache, and when there is
nothing cached -- or what is cached has gone stale -- it starts the fetch on
another thread and answers with what it has. Note that calling the memoized
function itself would *not* be enough:
:meth:`cache.memcache_memoize.__call__` fetches synchronously on a miss and
only refreshes in the background for a value that is already cached, so a cold
cache would put the provider's full deadline in front of the render.

Answering "no loans" leaves the CTA saying Borrow for a book the patron already
holds. That is wrong but harmless: Lenny's borrow is idempotent for an existing
loan, so the patron just gets that loan back. Blocking or raising on the book
page would not be harmless, which is why nothing here propagates and nothing
here waits.

This deliberately does not go through ``AbstractBookProvider.get_acquisitions``.
That call feeds Solr's ``ebook_access``, so making it per-patron would bake loan
state -- which changes by the hour -- into an index rebuilt far more slowly.
"""

from __future__ import annotations

import importlib
import logging
import time
from typing import TYPE_CHECKING, Any

from openlibrary.core import cache
from openlibrary.utils import dateutil

if TYPE_CHECKING:
    from openlibrary.core.models import User

logger = logging.getLogger("openlibrary.provider_loans")

# How long a cached answer is served before a refresh is started behind it.
# Short, because a loan that has expired should stop being offered soon; the
# refresh costs the render nothing, so this is a staleness bound, not a budget.
PROVIDER_LOANS_TTL = dateutil.MINUTE_SECS

# A node supplies ``read_url``, so it is never interpolated into a link without
# being checked first.
SAFE_URL_SCHEMES = ("http://", "https://")


def _fetch_provider_loans(username: str) -> list[dict[str, Any]]:
    """Every provider loan this patron holds, or ``[]`` if the lookup failed.

    Returns a plain list rather than the ``ProviderLoans`` tuple because
    :class:`cache.memcache_memoize` round-trips values through JSON.

    ``unreachable`` and ``unauthorized`` are dropped on purpose: the loans page
    reports them to the patron, but the book page has nowhere to say it and
    nothing to say it about -- a node it could not reach is indistinguishable,
    from here, from a node at which the patron holds no loan.
    """
    try:
        # Imported by name, not statically: the Lenny integration is optional,
        # so this module must load and answer "no loans" without it.
        lenny = importlib.import_module("openlibrary.plugins.upstream.lenny")
    except ImportError:
        return []

    try:
        return list(lenny.provider_loans(username).loans)
    except Exception:
        logger.exception("provider loan lookup failed for %s; treating it as no loans", username)
        return []


get_cached_provider_loans = cache.memcache_memoize(
    _fetch_provider_loans,
    key_prefix="lending.provider_loans",
    timeout=PROVIDER_LOANS_TTL,
)


def _refresh_in_background(username: str) -> None:
    """Start a fetch on another thread, and never make the caller wait for it."""
    try:
        get_cached_provider_loans.update_async(username)
    except Exception:
        logger.exception("could not start a provider loan refresh for %s", username)


def _cached_loans(username: str) -> list[dict[str, Any]]:
    """This patron's loans as memcache currently has them -- no inline fetch."""
    try:
        cached = get_cached_provider_loans.memcache_get((username,), {})
    except Exception:
        logger.exception("provider loan cache read failed for %s; treating it as no loans", username)
        return []

    if cached is None:
        _refresh_in_background(username)
        return []

    loans, fetched_at = cached
    if fetched_at + get_cached_provider_loans.timeout < time.time():
        _refresh_in_background(username)
    return loans or []


def invalidate_provider_loans(username: str) -> None:
    """Forget this patron's cached loans, so the next page asks the node again.

    For a grant that has gone away -- a revoked token, a node removed from the
    config -- where there is no replacement to write.

    **Not what the borrow flow wants.** Dropping the entry does not make the
    next render show the new loan: a cold entry answers "no loans" and only
    *starts* the fetch, by design, because this module never blocks a render on
    a provider. So an invalidation leaves the CTA saying Borrow on the very
    page the patron just borrowed from, one request later and for as long as
    the fetch takes. :func:`prime_provider_loans` is the one to call there.
    """
    try:
        get_cached_provider_loans.memcache_delete_by_args(username)
    except Exception:
        logger.exception("could not invalidate cached provider loans for %s", username)


PRIMED_AT = 0.0
"""The ``fetched_at`` a primed entry carries: stale the instant it is written.

A borrow knows about one loan; the node is the authority on the patron's
holdings. Writing an epoch-zero timestamp means :func:`_cached_loans` serves
the primed value to the render that needs it *and* starts a real fetch behind
it, so the partial set this writes is replaced rather than held for
:data:`PROVIDER_LOANS_TTL`.
"""


def prime_provider_loans(username: str, loan: dict[str, Any]) -> None:
    """Record a loan the borrow flow just created, for the next render.

    Called once a borrow succeeds. What it fixes, reported by Mek walking the
    live flow on 2026-10-09: the loan was created, the book page refreshed
    itself, and the CTA still said Borrow; a manual refresh a moment later said
    Read. The page was re-rendering from the entry written before the borrow,
    and nothing in the flow had told this module otherwise.

    Merged into whatever is cached rather than replacing it, and keyed on
    ``book`` so a patron who borrows the same edition twice -- Lenny's borrow
    is idempotent, so a second click is a real path -- ends with one entry.
    """
    if not _has_usable_read_url(loan) or not loan.get("book"):
        # `get_provider_loan` would drop this anyway. Writing it would mask the
        # patron's real holdings behind a row that renders nothing.
        logger.info("not priming a provider loan with no usable read_url for %s", username)
        return
    try:
        cached = get_cached_provider_loans.memcache_get((username,), {})
        existing = (cached[0] if cached else None) or []
        loans = [held for held in existing if not (isinstance(held, dict) and held.get("book") == loan["book"])]
        loans.append(loan)
        get_cached_provider_loans.memcache_set((username,), {}, loans, PRIMED_AT)
    except Exception:
        # The loan exists at the node by the time this is called, so the borrow
        # has already succeeded. Raising would turn it into an error page.
        logger.exception("could not prime cached provider loans for %s", username)


def _has_usable_read_url(loan: object) -> bool:
    """Can this loan be offered as a link at all?

    One definition, shared by the read side and by :func:`prime_provider_loans`,
    so the borrow flow cannot write a row the book page will silently refuse.
    """
    if not isinstance(loan, dict):
        return False
    read_url = loan.get("read_url")
    return isinstance(read_url, str) and read_url.lower().startswith(SAFE_URL_SCHEMES)


def _is_readable_loan(loan: object, edition_key: str) -> bool:
    """Is this a loan on ``edition_key`` that we can actually offer a link to?

    A loan without a usable ``read_url`` is treated as no loan: showing Read
    with nowhere to send the patron is worse than showing Borrow, which at
    least works.
    """
    if not isinstance(loan, dict) or loan.get("book") != edition_key:
        return False
    return _has_usable_read_url(loan)


def get_provider_loan(edition_key: str | None, user: User | None = None) -> dict[str, Any] | None:
    """The patron's live provider loan on ``edition_key``, or None.

    ``edition_key`` is a full Open Library key (``/books/OL1M``), which is what
    ``lenny.provider_loans`` puts on each loan's ``book`` field.

    Never raises and never blocks: every caller is a render path that must
    survive a provider being slow, broken, or absent.
    """
    if not edition_key:
        return None

    if user is None:
        from openlibrary.accounts import get_current_user

        user = get_current_user()
    if not user:
        return None

    try:
        username = user.get_username()
    except Exception:
        logger.exception("could not resolve a username for a provider loan lookup")
        return None
    if not username:
        return None

    return next((loan for loan in _cached_loans(username) if _is_readable_loan(loan, edition_key)), None)
