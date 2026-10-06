"""Core Vitals Retention Score -- how much value patrons are accessing (#11956).

    E_tau(t)   = sum_e [C(e,tau,t) x w_e] / P_tau(t)
    R_total(t) = sum_tau [w_tau x P_tau(t) x E_tau(t)]

where tau is a patron class, P_tau its unique active patrons, and w_e the
engagement point value of event e. See ``ol-kb/wiki/core-vitals.md``.

**This module deliberately imports nothing from Open Library.** Retention is
computed entirely from Matomo, and the intent is for it to move into a
standalone Core Vitals service that runs as independently of openlibrary.org
as possible. Keeping the import graph clean means that move is a file copy
rather than an untangling -- and
``openlibrary/tests/core/test_retention.py::TestImportIndependence`` fails if
anyone couples it back to the app.

Contrast ``openlibrary/admin/vitals.py``, which computes participation scores
and is genuinely app-coupled: those come from Open Library's own database.
"""

import datetime
import logging
import os
import re
from urllib.parse import urlsplit

import yaml
from statsd import StatsClient

from openlibrary.core.matomo import MatomoClient

logger = logging.getLogger("openlibrary.retention")

RETENTION_EVENT_PREFIX = "stats.ol.retention"


def configure_statsd(configfile) -> StatsClient:
    """Build a statsd client from an openlibrary.yml-shaped config file.

    Deliberately duplicated from ``openlibrary/admin/vitals.py`` rather than
    imported: importing that module pulls in 80+ app and infobase modules, which
    would defeat this module's independence for the sake of eight lines.
    """
    with open(configfile) as f:
        configs = yaml.safe_load(f)
    url = configs.get("admin", {}).get("statsd_server", None)
    if not url:
        raise KeyError("StatsD server not configured")
    host, _, port = url.partition(":")
    return StatsClient(host, port)


def resolve_token(configfile: str) -> str:
    """The Matomo token, from the environment or the config file.

    MATOMO_TOKEN wins so a developer never has to edit a tracked config to run
    a scoring pass.
    """
    if token := os.environ.get("MATOMO_TOKEN"):
        return token
    with open(configfile) as f:
        return (yaml.safe_load(f) or {}).get("matomo_api") or ""


# Custom dimension 1 ("Days Since Registration"), set by get_days_registered()
# in openlibrary/accounts/__init__.py. Buckets are discrete and mutually
# exclusive, NOT cumulative -- "d1+" means 1-6 days, not "1 or more days".
COHORTS = ["visitor", "d0", "d1+", "d7+", "d14+", "d30+", "d90+"]

# Patron classes and their weights w_tau, per the Core Vitals spec:
# visitors=0.01, registrants=0.2, returning=0.5, retained=1.
#
# The spec fixes the four weights but not where the returning/retained line
# falls across the seven cohorts. We treat "retained" as an account that has
# survived 90+ days; everything from the day after registration up to that
# point is "returning". This is the one judgement call in the mapping -- it is
# isolated here deliberately, and because every raw cohort is also emitted to
# statsd individually, the boundary can be re-cut later without losing history.
PATRON_CLASSES: dict[str, dict] = {
    "visitor": {"weight": 0.01, "cohorts": ["visitor"]},
    "registrant": {"weight": 0.20, "cohorts": ["d0"]},
    "returning": {"weight": 0.50, "cohorts": ["d1+", "d7+", "d14+", "d30+"]},
    "retained": {"weight": 1.00, "cohorts": ["d90+"]},
}

# Engagement point values, straight from the Score Schemas spreadsheet
# (docs.google.com/spreadsheets/d/1tt9ekWRMVaNiMc3GKMP09W3YmBeMXoTwKJnxuaispRA,
# gid=41518278). Mirrored in ol-kb/raw/google-docs/ and asserted by a test, so
# the code and the schema cannot drift apart silently.
EVENT_POINTS: dict[str, int] = {
    "import_goodreads": 200,
    "set_reading_goal": 150,
    "read": 100,
    "search_inside": 75,
    "list_create": 50,
    "follow": 50,
    "edit": 25,
    "readlog_completion": 20,
    "star_rating": 20,
    "readlog_currently_reading": 15,
    "readlog_want_to_read": 10,
    "checkin": 10,
    "explorer_view": 10,
    "search": 5,
    "book_view": 5,
    "author_view": 5,
    "mybooks_view": 5,
}

# (Matomo eventCategory, eventAction) -> event name. Every tuple here was
# checked against a full day of real Matomo traffic; a mapping that matches
# nothing scores nothing, silently, which is how `read` came to be worth zero.
RETENTION_EVENTS: dict[tuple[str, str], str] = {
    ("PatronImports", "Goodreads"): "import_goodreads",
    ("MyBooksLandingPage", "SetReadingGoal"): "set_reading_goal",
    ("OnboardingCarouselClick", "YearlyReadingGoals"): "set_reading_goal",
    # Every way a patron actually reaches the content counts as `read`. Borrow
    # is a read behind a lending gate, not a lesser signal: ReadButton.html
    # picks the label purely from whether a loan is needed, and both paths land
    # on the same /borrow/ia/{ocaid} reader. The *Listen variants are the same
    # buttons with read-aloud, and PrintDisabled is the same grant of access.
    ("CTAClick", "Read"): "read",
    ("CTAClick", "Borrow"): "read",
    ("CTAClick", "PrintDisabled"): "read",
    ("CTAClick", "ReadListen"): "read",
    ("CTAClick", "BorrowListen"): "read",
    ("CTAClick", "Listen"): "read",
    # follow and readlog_* have been tracked app-side since PR #12367.
    # FollowsPage and MyBooksPageHeader are wired but produced no events in the
    # sampled day -- kept because they are correct, just low-traffic.
    ("FollowsPage", "Follow"): "follow",
    ("MyBooksPageHeader", "Follow"): "follow",
    ("ListCardCarousel", "Follow"): "follow",
    ("PatronPage", "Follow"): "follow",
    ("CTAClick", "Edit"): "edit",
    ("CTAClick", "StickyEdit"): "edit",
    ("ReadingLog", "AlreadyRead"): "readlog_completion",
    ("ReadingLog", "CurrentlyReading"): "readlog_currently_reading",
    ("ReadingLog", "WantToRead"): "readlog_want_to_read",
    ("CheckInForm", "SubmitCheckIn"): "checkin",
    ("MainNav", "Explore"): "explorer_view",
    ("MainNav", "MyBooks"): "mybooks_view",
}

# Engagement events tracked as page views (URL-triggered tags) rather than
# custom events, matched against the URL's *path* by prefix -- see
# _score_page_url, which sorts these longest-first so `/search/inside` cannot be
# scored as `search`.
PAGE_EVENTS: dict[str, str] = {
    "/search": "search",
    "/books/": "book_view",
    "/works/": "book_view",
    "/authors/": "author_view",
}

# Paths that would otherwise match a PAGE_EVENTS prefix but are not that event.
# `/people/{user}/books/...` and `/account/books/...` are the reading-log shelves
# (openlibrary/plugins/upstream/mybooks.py); they contain "/books/" but are not
# book views, and being logged-in-only they would bias the heavily weighted
# classes upward. `/search/inside` is search_inside, which has no Matomo source
# yet and is declared in UNTRACKED_EVENTS -- scoring it as `search` would
# quietly contradict that.
NON_SCORING_PATHS: tuple[str, ...] = (
    "/account/books/",
    "/search/inside",
)

# The same reading-log shelves under their per-patron URL, which is dynamic
# (`/people/{username}/books/already-read`) so it cannot be a static prefix.
NON_SCORING_PATH_RE = re.compile(r"^/people/[^/]+/books(/|$)")

# Matomo action types that represent a page view. "search" appears when a site
# has search-parameter detection enabled server-side, in which case /search?q=
# arrives as this type rather than "action" -- accepting it costs nothing and
# avoids `search` silently scoring zero the way `read` did.
PAGE_ACTION_TYPES: tuple[str, ...] = ("action", "page", "search")

# Schema events with no working Matomo source, so they contribute 0 today.
# Each needs app-side instrumentation or a corrected tag, not a code change here:
#   list_create   -- no tracking attribute anywhere (#12366)
#   search_inside -- no event fires; CTAClick|Preview and SearchInsideSuggestion|*
#                    both exist but neither unambiguously means "read inside"
#   star_rating   -- StarRating|StatsComponentClick is a stats-panel click, not a
#                    rating; ratings are captured in Postgres but not in Matomo
UNTRACKED_EVENTS: dict[str, int] = {
    "search_inside": EVENT_POINTS["search_inside"],
    "list_create": EVENT_POINTS["list_create"],
    "star_rating": EVENT_POINTS["star_rating"],
}


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _statsd_safe(name: str) -> str:
    """Make a cohort name safe for a statsd/Graphite metric path (`d1+` -> `d1_plus`)."""
    return name.replace("+", "_plus")


def _cohort_to_class(cohort: str) -> str:
    for cls, info in PATRON_CLASSES.items():
        if cohort in info["cohorts"]:
            return cls
    return "visitor"


def _score_visit(visit: dict) -> dict[str, int]:
    """Return the engagement events earned in one visit, as {event_name: points}.

    Each event type counts at most once per visit: a patron clicking the same
    button ten times expressed one intent, not ten.
    """
    earned: dict[str, int] = {}
    for action in visit.get("actionDetails") or []:
        name = None
        action_type = action.get("type", "")
        if action_type == "event":
            name = RETENTION_EVENTS.get((action.get("eventCategory", ""), action.get("eventAction", "")))
        elif action_type in PAGE_ACTION_TYPES:
            name = _score_page_url(action.get("url") or "")
        if name:
            earned[name] = EVENT_POINTS[name]
    return earned


def _score_page_url(url: str) -> str | None:
    """Match a page view against PAGE_EVENTS on its *path*, most specific first.

    Matching the whole URL as a substring is wrong in both directions: it scores
    ``/account/books/want-to-read`` as a `book_view` because that path contains
    ``/books/``, and it would score any third-party URL containing ``/works/``.
    The first error is the damaging one, since reading-log pages are logged-in
    only and land on the classes weighted 20-100x above `visitor`.
    """
    parts = urlsplit(url)
    # Matomo should only ever report URLs for the tracked site, but a host check
    # costs nothing and stops an off-site URL that happens to contain /works/
    # from scoring as a book view.
    if parts.netloc and not (parts.netloc == "openlibrary.org" or parts.netloc.endswith(".openlibrary.org")):
        return None
    path = parts.path
    if not path.startswith("/"):
        return None
    if any(path.startswith(prefix) for prefix in NON_SCORING_PATHS) or NON_SCORING_PATH_RE.match(path):
        return None
    # Sorted longest-first so `/search/inside` never matches `/search`.
    for prefix in sorted(PAGE_EVENTS, key=len, reverse=True):
        if path.startswith(prefix):
            return PAGE_EVENTS[prefix]
    return None


def _patron_id(visit: dict) -> str:
    """Identify the patron behind a visit, or "" when it cannot be identified.

    `userId` is preferred so one logged-in patron across two devices counts
    once, but it is only populated if Matomo's setUserId is wired -- which it
    is not yet -- so in practice this falls back to the per-device visitorId.

    An empty result must not be added to a patron set: every unidentifiable
    visit would collapse into one phantom patron carrying all of their points,
    which inflates E_tau for whichever class it lands in. Callers count these
    separately instead.
    """
    return visit.get("userId") or visit.get("visitorId") or ""


def _visit_hour(visit: dict) -> datetime.datetime | None:
    """The clock hour a visit belongs to, from its first action.

    `firstActionTimestamp` is a Unix int on every visit `Live.getLastVisitsDetails`
    returns; `serverTimestamp` is the fallback. A visit straddling an hour boundary
    is attributed wholly to the hour it started in.
    """
    timestamp = visit.get("firstActionTimestamp") or visit.get("serverTimestamp")
    if timestamp is None:
        return None
    try:
        started = datetime.datetime.fromtimestamp(int(timestamp), datetime.UTC)
    except TypeError, ValueError, OSError:
        return None
    return started.replace(minute=0, second=0, microsecond=0)


def _summarize_visits(
    visits: list[dict],
    hours: int,
    since: datetime.datetime,
    dropped_no_timestamp: int = 0,
    started_before_window: int = 0,
    truncated: bool = False,
) -> dict:
    """Score a set of visits into cohort, class, and overall retention numbers.

    `dropped_no_timestamp` and `truncated` describe the *fetch* rather than these
    visits, and are threaded through so they reach `warnings` -- a score computed
    from a truncated or partly-unusable feed must not look like a quiet hour.
    """
    seen_patrons: dict[str, set[str]] = {cohort: set() for cohort in COHORTS}
    weighted_totals: dict[str, int] = dict.fromkeys(COHORTS, 0)
    events: dict[str, dict] = {}
    # Counted so a cohort dimension that stops arriving, or starts arriving with
    # different labels, shows up as a warning rather than as a quietly smaller
    # score. Renumbering dimension1 to dimension2 collapsed R_total ~54x with no
    # warning at all before these existed.
    missing_dimension = 0
    unknown_cohort = 0
    unidentified_patrons = 0

    for visit in visits:
        raw_cohort = visit.get("dimension1")
        if not raw_cohort:
            missing_dimension += 1
            cohort = "visitor"
        elif raw_cohort not in seen_patrons:
            # An unrecognised bucket is treated as logged-out rather than
            # dropped, so the visit still shows up somewhere in the totals.
            unknown_cohort += 1
            cohort = "visitor"
        else:
            cohort = raw_cohort

        if patron := _patron_id(visit):
            seen_patrons[cohort].add(patron)
        else:
            # Adding "" would merge every anonymous visit into one patron holding
            # all their points, inflating E_tau for this cohort.
            unidentified_patrons += 1

        for name, points in _score_visit(visit).items():
            weighted_totals[cohort] += points
            entry = events.setdefault(name, {"count": 0, "points": points, "total": 0})
            entry["count"] += 1
            entry["total"] += points

    cohorts = {
        cohort: {
            "patrons": len(seen_patrons[cohort]),
            "weighted_total": weighted_totals[cohort],
            "engagement": (weighted_totals[cohort] / len(seen_patrons[cohort]) if seen_patrons[cohort] else 0.0),
        }
        for cohort in COHORTS
    }

    classes = {}
    for cls, info in PATRON_CLASSES.items():
        patrons = sum(cohorts[cohort]["patrons"] for cohort in info["cohorts"])
        weighted_total = sum(cohorts[cohort]["weighted_total"] for cohort in info["cohorts"])
        engagement = weighted_total / patrons if patrons else 0.0
        classes[cls] = {
            "weight": info["weight"],
            "cohorts": info["cohorts"],
            "patrons": patrons,
            "weighted_total": weighted_total,
            "engagement": engagement,
            # w_tau x P_tau x E_tau -- this class's share of R_total.
            "contribution": info["weight"] * weighted_total,
        }

    r_total = sum(cls["contribution"] for cls in classes.values())
    # Counted across all cohorts at once, not summed per class: a patron who
    # appears in two cohorts within the window (an unknown-cohort fallback, or a
    # d30+ -> d90+ crossing over a long window) would otherwise be counted twice
    # and halve r_per_patron.
    total_patrons = len(set().union(*seen_patrons.values())) if visits else 0

    scores = {
        "window_hours": hours,
        "since": since.isoformat(),
        "visits": len(visits),
        "cohorts": cohorts,
        "classes": classes,
        # Which engagement events actually produced the score, most valuable
        # first. This is what makes R_total explainable rather than just a number.
        "events": dict(sorted(events.items(), key=lambda kv: -kv[1]["total"])),
        "r_total": r_total,
        "r_per_patron": r_total / total_patrons if total_patrons else 0.0,
        "total_patrons": total_patrons,
        # Data-quality counters. Non-zero values do not invalidate the score, but
        # a large share of any of them means it is measuring less than it looks.
        "data_quality": {
            "missing_dimension": missing_dimension,
            "unknown_cohort": unknown_cohort,
            "unidentified_patrons": unidentified_patrons,
            "dropped_no_timestamp": dropped_no_timestamp,
            "started_before_window": started_before_window,
            "truncated": truncated,
        },
    }
    scores["warnings"] = _sanity_warnings(scores)
    return scores


def gather_retention_scores(matomo_token: str = "", hours: int = 1, client: MatomoClient | None = None) -> dict:
    """Compute the Core Vitals Retention Score over the last `hours` hours as one window.

    Returns per-cohort and per-class patron counts (P_tau), engagement (E_tau), the
    events behind the score, the weighted overall score (R_total), and any sanity
    warnings. Pass `client` to score against a stub instead of live Matomo.
    """
    client = client or MatomoClient(matomo_token)
    since = _utcnow() - datetime.timedelta(hours=hours)
    fetch = client.get_visits_since(since)
    return _summarize_visits(fetch.visits, hours, since, truncated=fetch.truncated)


def gather_retention_scores_by_hour(matomo_token: str = "", hours: int = 2, client: MatomoClient | None = None) -> list[dict]:
    """Score each of the last `hours` clock hours separately, most recent first.

    One Matomo fetch covers the whole span; visits are then bucketed by the hour
    they started in. The first entry is the hour in progress and is flagged
    `partial` -- it covers only the minutes elapsed so far, so it is not
    comparable to a complete hour and should not be read as a drop.
    """
    client = client or MatomoClient(matomo_token)
    current_hour = _utcnow().replace(minute=0, second=0, microsecond=0)
    earliest = current_hour - datetime.timedelta(hours=hours - 1)

    buckets: dict[datetime.datetime, list[dict]] = {earliest + datetime.timedelta(hours=n): [] for n in range(hours)}
    fetch = client.get_visits_since(earliest)
    no_timestamp = 0
    started_earlier = 0
    for visit in fetch.visits:
        hour = _visit_hour(visit)
        if hour in buckets:
            buckets[hour].append(visit)
        elif hour is None:
            no_timestamp += 1
        else:
            # `minTimestamp` selects visits whose *last* action falls in the
            # window, so a session that began earlier and is still active is
            # returned but starts outside every bucket. Counted, not silently
            # dropped -- measured at ~2% of a real 3-hour fetch.
            started_earlier += 1

    truncated = fetch.truncated
    summaries = []
    for hour_start in sorted(buckets, reverse=True):
        summary = _summarize_visits(
            buckets[hour_start], 1, hour_start, dropped_no_timestamp=no_timestamp, started_before_window=started_earlier, truncated=truncated
        )
        summary["hour_start"] = hour_start.isoformat()
        summary["partial"] = hour_start == current_hour
        summaries.append(summary)
    return summaries


# Share of visits that may show a given data-quality problem before it is worth
# a warning. Some noise is normal; a tenth of the feed is not.
QUALITY_WARN_FRACTION = 0.10

# Above this share of patrons in `visitor`, the cohort dimension has almost
# certainly stopped arriving rather than the traffic having genuinely changed.
VISITOR_SHARE_WARN = 0.99


def _sanity_warnings(scores: dict) -> list[str]:
    """Flag results that look like an instrumentation failure rather than a quiet hour.

    Every bug this pipeline has shipped presented as a plausible number rather
    than an error: a cohort dimension read from the wrong place, and an event
    mapped to a category that does not exist. Both produced a *smaller* score,
    never a failure, so the checks here are deliberately about shape and data
    quality rather than correctness -- which cannot be checked from inside.
    """
    warnings = []
    visits = scores["visits"]
    quality = scores["data_quality"]

    if not visits:
        warnings.append(f"Matomo returned no visits for the last {scores['window_hours']}h")

    if quality["truncated"]:
        warnings.append(f"the Matomo fetch was truncated, so this score covers only part of the window ({visits} visits)")

    # Checked outside the `if visits` guard below: a bucket can be empty *because*
    # its visits were dropped, which is exactly when this matters most.
    if quality["dropped_no_timestamp"]:
        warnings.append(f"{quality['dropped_no_timestamp']} visits had no usable timestamp and were not counted in any hour")
    if quality["started_before_window"]:
        warnings.append(f"{quality['started_before_window']} visits were still active in the window but began before it, so they were not counted in any hour")

    if visits:
        threshold = visits * QUALITY_WARN_FRACTION
        if quality["missing_dimension"] > threshold:
            warnings.append(
                f"{quality['missing_dimension']}/{visits} visits had no `dimension1` cohort and were counted as `visitor` "
                "-- if custom dimension 1 has been renumbered or disabled in Matomo, this score is badly understated"
            )
        if quality["unknown_cohort"] > threshold:
            warnings.append(
                f"{quality['unknown_cohort']}/{visits} visits had a `dimension1` value outside {COHORTS} and were counted as `visitor` "
                "-- the cohort labels may have changed in get_days_registered()"
            )
        if quality["unidentified_patrons"] > threshold:
            warnings.append(f"{quality['unidentified_patrons']}/{visits} visits had neither userId nor visitorId, so they scored points but no patron")
        # The check that would have caught both historical bugs: a real hour of
        # openlibrary.org traffic always contains some logged-in patrons.
        total = scores["total_patrons"]
        visitors = scores["cohorts"]["visitor"]["patrons"]
        if total and visitors / total >= VISITOR_SHARE_WARN:
            warnings.append(f"{visitors}/{total} patrons are `visitor` -- expected some logged-in traffic, so cohort tracking may be broken")

    for cls, data in scores["classes"].items():
        if data["patrons"] and not data["weighted_total"]:
            warnings.append(f"{cls}: {data['patrons']} active patrons but zero scored engagement")
    return warnings


def retention_gauges(rscores: dict) -> dict[str, float]:
    """Map a score result to the exact statsd gauges the hourly cron emits.

    Kept as a pure function separate from the write so the same mapping can be
    inspected, tested, or pointed at a different sink (a local SQLite table, for
    instance) without duplicating the metric names.

    Every raw cohort is emitted alongside the four-class rollup: the cohorts are
    the storage primitive, so the D0 -> D1 -> D7 -> D30 curve stays visible and
    the class boundaries can be redrawn later without losing history. Cohorts
    and classes live under separate prefixes because `visitor` is the name of
    both and would otherwise collide.

    `points` (the unweighted event total) is emitted next to `patrons` and
    `engagement` so re-weighting from history is exact arithmetic rather than a
    reconstruction from `patrons x engagement`.
    """
    gauges: dict[str, float] = {}

    for cohort, data in rscores["cohorts"].items():
        safe = _statsd_safe(cohort)
        gauges[f"{RETENTION_EVENT_PREFIX}.cohort.{safe}.patrons.hourly.total"] = data["patrons"]
        gauges[f"{RETENTION_EVENT_PREFIX}.cohort.{safe}.engagement.hourly"] = data["engagement"]
        gauges[f"{RETENTION_EVENT_PREFIX}.cohort.{safe}.points.hourly.total"] = data["weighted_total"]

    for cls, data in rscores["classes"].items():
        gauges[f"{RETENTION_EVENT_PREFIX}.class.{cls}.patrons.hourly.total"] = data["patrons"]
        gauges[f"{RETENTION_EVENT_PREFIX}.class.{cls}.engagement.hourly"] = data["engagement"]
        gauges[f"{RETENTION_EVENT_PREFIX}.class.{cls}.points.hourly.total"] = data["weighted_total"]

    # The north-star number. This is the series to watch over the year.
    gauges[f"{RETENTION_EVENT_PREFIX}.total_score.hourly"] = rscores["r_total"]
    gauges[f"{RETENTION_EVENT_PREFIX}.per_patron.hourly"] = rscores["r_per_patron"]
    gauges[f"{RETENTION_EVENT_PREFIX}.patrons.hourly.total"] = rscores["total_patrons"]

    # Emitted so a broken feed is visible on the dashboard rather than only in a
    # log line nobody reads. A rising `missing_dimension` alongside a falling
    # score is the signature of instrumentation breaking, not engagement falling.
    for name, value in rscores["data_quality"].items():
        gauges[f"{RETENTION_EVENT_PREFIX}.quality.{name}.hourly"] = int(value)
    return gauges


def write_retention_to_statsd(configfile, rscores: dict) -> None:
    """Push the retention gauges for one scored window to statsd."""
    statsd = configure_statsd(configfile)
    for key, value in retention_gauges(rscores).items():
        statsd.gauge(key, value)
