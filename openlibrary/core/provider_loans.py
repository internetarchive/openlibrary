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

    The borrow flow should call this once a borrow succeeds. Without it the CTA
    can keep offering Borrow for up to :data:`PROVIDER_LOANS_TTL` seconds on the
    very page the patron just borrowed from.
    """
    try:
        get_cached_provider_loans.memcache_delete_by_args(username)
    except Exception:
        logger.exception("could not invalidate cached provider loans for %s", username)


def _is_readable_loan(loan: object, edition_key: str) -> bool:
    """Is this a loan on ``edition_key`` that we can actually offer a link to?

    A loan without a usable ``read_url`` is treated as no loan: showing Read
    with nowhere to send the patron is worse than showing Borrow, which at
    least works.
    """
    if not isinstance(loan, dict) or loan.get("book") != edition_key:
        return False
    read_url = loan.get("read_url")
    return isinstance(read_url, str) and read_url.lower().startswith(SAFE_URL_SCHEMES)


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
