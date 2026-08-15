"""Minimal read-only Matomo Reporting API client, for Core Vitals retention scoring.

Groundwork for the Core Vitals Retention Score (issue #11956): the scorer that
consumes this lands separately, so that the access layer -- where the token
handling and the read-only guarantees live -- can be reviewed on its own terms
rather than alongside a scoring formula. See ``ol-kb/wiki/core-vitals.md``.

Deliberately knows nothing about scoring. Retention is computed entirely from
Matomo and is intended to move into a standalone Core Vitals service, so this
module imports nothing from Open Library and should stay that way -- the move
should be a file copy, not an untangling.

The Matomo instance (``matomo.archive.org``, site ID 6 = openlibrary.org) is
restricted to Internet Archive's internal network. Production runs on IA
infrastructure and reaches it directly. From a developer machine, set
``HTTPS_PROXY`` to an allowlisted forward proxy -- ``requests`` picks that up
from the environment automatically, so nothing here needs to know about it.

To work with no Matomo access at all, point ``MATOMO_URL`` at the mock in
``docker/mockservices``, which serves the same wire format from a small,
predictable visit feed::

    MATOMO_URL=http://mockservices:8090/matomo
"""

import datetime
import logging
import os
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("openlibrary.matomo")

MATOMO_URL = "https://matomo.archive.org"
MATOMO_SITE_ID = 6

# Live.getLastVisitsDetails is paginated; cap total pages so a runaway
# response can never spin a scheduled job forever. See also `budget_seconds`,
# which bounds wall-clock rather than request count.
MAX_PAGES = 200

# Matomo's own raw-log retention is finite, and a longer request is far more
# likely to be a mistake than an intent.
MAX_WINDOW = datetime.timedelta(days=7)


class MatomoError(Exception):
    pass


class MatomoClient:
    """Read-only client for the Matomo Reporting API.

    READ-ONLY BY INTENT.

    This client must never call a Matomo API method that writes, deletes, or
    otherwise mutates data -- the instance holds production analytics for
    openlibrary.org and a destructive call would be irreversible.

    :attr:`_ALLOWED_METHODS` is an exact-match allowlist, and :meth:`_post`
    applies caller params before the fixed keys so nothing can redirect the
    request at another module, site, or token. Treat that as a guardrail against
    mistakes, **not** as a security boundary: the token itself is the only real
    control, so the credential in ``matomo_api`` should be a view-only Matomo
    user. An earlier prefix-based allowlist here was bypassable via
    ``API.getBulkRequest``, which tunnels arbitrary methods inside an ``API.``
    call -- hence exact matching.
    """

    # Extend only with methods this codebase actually calls, and only read ones.
    _ALLOWED_METHODS = frozenset({"Live.getLastVisitsDetails"})

    def __init__(self, token: str, url: str = "", site_id: int = 0, budget_seconds: int = 300) -> None:
        if not token:
            raise MatomoError("A Matomo API token is required (set `matomo_api` in openlibrary.yml)")
        self._token = token
        # Read the environment here rather than at import time so a test or a
        # dev shell can retarget the client without reimporting the module. An
        # unset environment always means production, never something in between.
        self.url = (url or os.environ.get("MATOMO_URL") or MATOMO_URL).rstrip("/")
        self.site_id = site_id or int(os.environ.get("MATOMO_SITE_ID") or MATOMO_SITE_ID)
        self.timeout = 30
        # `timeout` is per socket read, so it bounds no overall duration. This is
        # the real wall clock, checked between pages.
        self.budget_seconds = budget_seconds
        # Set when a fetch stops early; callers surface it rather than reporting
        # a truncated hour as a quiet one.
        self.truncated = False
        # One connection reused across pages instead of a fresh TLS handshake per
        # request, with a short retry so a single transient 5xx mid-pagination
        # does not leave a hole in the series.
        self._session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=(502, 503, 504), allowed_methods=frozenset({"POST"}))
        self._session.mount("https://", HTTPAdapter(max_retries=retries))
        self._session.mount("http://", HTTPAdapter(max_retries=retries))

    def _post(self, method: str, **params) -> list | dict:
        """Issue a single read-only Reporting API call.

        Uses POST rather than GET so the auth token travels in the request body
        instead of the query string, keeping it out of access and proxy logs.

        Caller params are applied *before* the fixed keys, so no caller can
        redirect this at another ``module``, site, or token.
        """
        if method not in self._ALLOWED_METHODS:
            raise MatomoError(f"BLOCKED: {method!r} is not in the read-only allowlist; this client must never mutate Matomo data")

        payload = {
            **params,
            "module": "API",
            "method": method,
            "format": "json",
            "idSite": self.site_id,
            "token_auth": self._token,
        }
        try:
            response = self._session.post(f"{self.url}/index.php", data=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            raise MatomoError(f"Matomo API request failed ({method}): {exc}") from exc
        except ValueError as exc:
            raise MatomoError(f"Matomo API returned a non-JSON response ({method})") from exc

        if isinstance(data, dict) and data.get("result") == "error":
            raise MatomoError(f"Matomo API error ({method}): {data.get('message')}")
        return data

    def get_visits_since(self, since: datetime.datetime, page_size: int = 500) -> list[dict]:
        """Return every visit active since ``since``, paginating as needed.

        Each visit dict carries a flat top-level ``dimension1`` field holding the
        patron's "Days Since Registration" bucket (visitor/d0/d1+/d7+/d14+/d30+/d90+,
        set by ``get_days_registered()`` in ``openlibrary/accounts/__init__.py``) and
        an ``actionDetails`` list of that visit's page views and custom events.

        Note ``dimension1`` is flat, NOT nested under a ``customDimensions`` key --
        ``Live.getLastVisitsDetails`` does not return that structure, and reading it
        as though it did silently classifies every visit as ``visitor``.
        """
        if since > (now := datetime.datetime.now(datetime.UTC)):
            raise MatomoError(f"`since` is in the future ({since.isoformat()})")
        if (now - since) > MAX_WINDOW:
            raise MatomoError(f"Windows longer than {MAX_WINDOW.days} days are not supported; asked for {(now - since).days} days")

        since_timestamp = int(since.timestamp())
        # Bound the date range by `since` rather than a fixed `last7`, which
        # silently clamped any longer window to 7 days while still reporting the
        # window that was asked for.
        #
        # Padded by a day at each end because Matomo interprets `date` in the
        # *site's* configured timezone while `since` is UTC. Without the padding a
        # site behind UTC drops the earliest hours of the window: measured
        # 2026-07-31, an exact UTC range returned 0 visits for the 06:00 hour
        # because 06:00 UTC is the previous day in the site's timezone.
        # `minTimestamp` still does the precise filtering; this only has to be
        # wide enough not to exclude anything.
        day = datetime.timedelta(days=1)
        date_range = f"{(since - day).date().isoformat()},{(now + day).date().isoformat()}"

        visits: list[dict] = []
        seen_visit_ids: set[str] = set()
        deadline = time.monotonic() + self.budget_seconds
        self.truncated = False

        for _page in range(MAX_PAGES):
            if time.monotonic() > deadline:
                self.truncated = True
                logger.warning("Matomo fetch exceeded its %ds budget after %d visits; results are truncated", self.budget_seconds, len(visits))
                break

            batch = self._post(
                "Live.getLastVisitsDetails",
                period="range",
                date=date_range,
                minTimestamp=since_timestamp,
                filter_limit=page_size,
                # Offset by what we actually hold: Matomo enforces server-side row
                # caps, so a page can legitimately be shorter than `page_size`, and
                # stepping by `page * page_size` would skip records.
                filter_offset=len(visits),
            )
            # Stop only on an empty page. A short-but-non-empty page means the
            # server capped the row count, not that the feed is exhausted --
            # treating it as the end silently truncates the score.
            if not batch:
                break
            if not isinstance(batch, list):
                raise MatomoError(f"Expected a list of visits, got {type(batch).__name__}")

            # The feed is newest-first and live, so visits arriving mid-pagination
            # shift the window and re-present records we already hold. Patron
            # counts survive that (they are sets) but points would double-count.
            fresh = [visit for visit in batch if str(visit.get("idVisit", "")) not in seen_visit_ids]
            seen_visit_ids.update(str(visit.get("idVisit", "")) for visit in batch)
            visits.extend(fresh)
            if not fresh:
                break
        else:
            self.truncated = True
            logger.warning("Matomo visit pagination hit the %d-page cap; results are truncated", MAX_PAGES)

        return visits
