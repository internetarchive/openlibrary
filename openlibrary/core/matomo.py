"""Read-only Matomo Reporting API client.

Groundwork for the Core Vitals Retention Score (issue #11956); the scorer that
consumes it lands separately. See ``ol-kb/wiki/core-vitals.md`` for the formulas.

Imports nothing from Open Library, deliberately: retention is computed entirely
from Matomo and is intended to move into a standalone Core Vitals service, so
that move should be a file copy rather than an untangling.

The instance (``matomo.archive.org``, site 6 = openlibrary.org) is restricted to
Internet Archive's network; production reaches it directly. From a developer
machine either set ``HTTPS_PROXY`` to an allowlisted forward proxy, which
``requests`` picks up on its own, or point ``MATOMO_URL`` at the fake in
``docker/mockservices`` to work with no Matomo access at all::

    MATOMO_URL=http://mockservices:8090/matomo
"""

import datetime
import logging
import os
import time
from dataclasses import dataclass, field

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("openlibrary.matomo")

DEFAULT_MATOMO_URL = "https://matomo.archive.org"
DEFAULT_SITE_ID = 6

# A loop guard, not the operative limit: `if not batch` and `if not fresh`
# already terminate against any well-behaved server. `budget_seconds` is the
# bound an operator should actually tune.
MAX_PAGES = 200

# Matomo's own raw-log retention is finite, so a longer request is far more
# likely to be a mistake than an intent.
MAX_WINDOW = datetime.timedelta(days=7)


class MatomoError(Exception):
    """Matomo was unreachable, or answered with something unusable."""


class MatomoMethodNotAllowed(MatomoError):
    """A method outside the read-only allowlist was requested.

    Distinct so that a caller handling "Matomo is flaky" cannot accidentally
    swallow a programming error.
    """


@dataclass(frozen=True)
class VisitFetch:
    """The result of one fetch: the visits, and whether they are all of them.

    `truncated_reason` carries the signal in the return value rather than as
    state on the client, so a caller cannot read it a call too late and a type
    checker can see it exists.
    """

    visits: list[dict] = field(default_factory=list)
    truncated_reason: str | None = None

    @property
    def truncated(self) -> bool:
        return self.truncated_reason is not None

    def __len__(self) -> int:
        return len(self.visits)


class MatomoClient:
    """Read-only client for the Matomo Reporting API.

    Must never call a method that writes, deletes, or otherwise mutates: the
    instance holds production analytics for openlibrary.org.

    :attr:`_ALLOWED_METHODS` matches exactly, and :meth:`_post` applies caller
    params before the fixed keys so nothing can redirect a request at another
    module, site, or token. Both are guardrails against mistakes rather than a
    security boundary -- the credential is the only real control, so the
    configured token should belong to a view-only Matomo user.
    """

    # Extend only with read methods this codebase actually calls. Exact matching
    # rather than by prefix: `API.getBulkRequest` sits under `API.` and tunnels
    # arbitrary methods through its own `urls[]` parameter.
    _ALLOWED_METHODS = frozenset({"Live.getLastVisitsDetails"})

    def __init__(self, token: str, url: str | None = None, site_id: int | None = None) -> None:
        if not token:
            raise ValueError("A Matomo API token is required")
        self._token = token
        # Resolved here rather than at import time so a test or dev shell can
        # retarget the client without reimporting. An unset environment always
        # means production.
        self.url = (url or os.environ.get("MATOMO_URL") or DEFAULT_MATOMO_URL).rstrip("/")
        self.site_id = site_id if site_id is not None else int(os.environ.get("MATOMO_SITE_ID") or DEFAULT_SITE_ID)
        self.timeout = 30
        # One connection reused across pages, with a short retry so a single
        # transient 5xx mid-pagination does not leave a hole in the series.
        self._session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=(502, 503, 504), allowed_methods=frozenset({"POST"}))
        self._session.mount("https://", HTTPAdapter(max_retries=retries))
        self._session.mount("http://", HTTPAdapter(max_retries=retries))

    def _post(self, method: str, **params) -> list[dict]:
        """Issue one read-only Reporting API call and return its rows.

        POST rather than GET so the token travels in the body instead of the
        query string, where proxies and access logs would capture it.
        """
        if method not in self._ALLOWED_METHODS:
            raise MatomoMethodNotAllowed(f"{method!r} is not in the read-only allowlist; this client must never mutate Matomo data")

        payload = {
            # Caller params first, so the fixed keys below always win.
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
        if not isinstance(data, list):
            # Checked here rather than in the caller: an empty dict is falsy, so
            # a caller testing emptiness first would read it as "end of feed".
            raise MatomoError(f"Matomo API returned {type(data).__name__}, expected a list of rows ({method})")
        return data

    def _window(self, since: datetime.datetime) -> tuple[int, str]:
        """Validate the requested window; return (minTimestamp, Matomo date range).

        The range is padded a day either side because Matomo reads `date` in the
        *site's* timezone while `since` is UTC -- an exact range drops the
        earliest hours for any site behind UTC. `minTimestamp` does the precise
        filtering, so this only has to be wide enough not to exclude anything.
        """
        now = datetime.datetime.now(datetime.UTC)
        if since > now:
            raise ValueError(f"`since` is in the future ({since.isoformat()})")
        if (now - since) > MAX_WINDOW:
            raise ValueError(f"Windows longer than {MAX_WINDOW.days} days are not supported; asked for {(now - since).days} days")

        day = datetime.timedelta(days=1)
        return int(since.timestamp()), f"{(since - day).date().isoformat()},{(now + day).date().isoformat()}"

    def get_visits_since(self, since: datetime.datetime, page_size: int = 500, budget_seconds: int = 300) -> VisitFetch:
        """Fetch every visit active since ``since``.

        Each visit carries a flat top-level ``dimension1`` holding the patron's
        "Days Since Registration" bucket, and an ``actionDetails`` list of that
        visit's page views and custom events. ``dimension1`` is flat, *not*
        nested under ``customDimensions`` -- this endpoint does not return that
        structure, and reading it as though it did yields no cohort at all.

        ``budget_seconds`` bounds one fetch; ``timeout`` is per socket read and
        bounds nothing overall. The budget is checked between pages, and a
        single page can spend up to ``timeout`` x retries inside the loop, so
        treat it as approximate rather than a hard deadline.
        """
        since_timestamp, date_range = self._window(since)
        visits: list[dict] = []
        seen: set[str] = set()
        # Rows the server has served, including duplicates. The offset must
        # track this rather than len(visits): dedupe makes the two diverge, and
        # offsetting by the deduped count re-requests rows already consumed.
        consumed = 0
        deadline = time.monotonic() + budget_seconds

        for page in range(MAX_PAGES):
            if time.monotonic() > deadline:
                return self._truncated(visits, f"exceeded the {budget_seconds}s budget after {page} pages")

            batch = self._post(
                "Live.getLastVisitsDetails",
                period="range",
                date=date_range,
                minTimestamp=since_timestamp,
                filter_limit=page_size,
                # Offset by rows consumed, not page x page_size: Matomo enforces
                # server-side row caps, so a page can come back short.
                filter_offset=consumed,
            )
            if not batch:
                break
            consumed += len(batch)

            # The feed is live and newest-first, so visits arriving mid-fetch
            # shift the window and re-present rows already consumed. An
            # all-duplicate page therefore means the window moved, NOT that the
            # feed ended -- breaking here silently dropped everything past the
            # shift, with no truncation reported.
            fresh = [visit for visit in batch if str(visit.get("idVisit", "")) not in seen]
            seen.update(str(visit.get("idVisit", "")) for visit in batch)
            visits.extend(fresh)
        else:
            return self._truncated(visits, f"hit the {MAX_PAGES}-page cap")

        return VisitFetch(visits)

    @staticmethod
    def _truncated(visits: list[dict], reason: str) -> VisitFetch:
        logger.warning("Matomo fetch truncated after %d visits: %s", len(visits), reason)
        return VisitFetch(visits, truncated_reason=reason)
