"""Loan Stats"""

import contextlib
import datetime as dt
from collections.abc import Iterable

import web

from infogami.utils import delegate

from .. import app
from ..contribute import initiatives, tasks
from ..contribute.field_guides import get_field_guides
from ..core import cache
from ..core.admin import get_count_docs, get_rolling_counts
from ..core.booknotes import Booknotes
from ..core.bookshelves import Bookshelves
from ..core.follows import PubSub
from ..core.helpers import commify
from ..core.lending import get_availabilities
from ..core.observations import Observations
from ..core.ratings import Ratings
from ..core.yearly_reading_goals import YearlyReadingGoals
from ..i18n import gettext as _
from ..plugins.admin.code import get_counts
from ..plugins.worksearch.code import get_solr_works
from ..utils import dateutil

LENDING_TYPES = "(libraries|regions|countries|collections|subjects|format)"


SINCE_DAYS: dict[str, int | None] = {
    "now": 0,
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
    "yearly": 365,
    "forever": None,
}


@cache.memoize("memcache", "stats.reading_log_summary", expires=dateutil.HOUR_SECS)
def reading_log_summary():
    # enable to work w/ cached
    if "env" not in web.ctx:
        delegate.fakeload()

    stats = Bookshelves.summary()
    stats.update(YearlyReadingGoals.summary_sync())
    stats.update(Ratings.summary_sync())
    stats.update(Observations.summary_sync())
    stats.update(Booknotes.summary_sync())
    stats.update(PubSub.summary_sync())
    return stats


DEFAULT_TRENDING_SHELF_IDS = [
    Bookshelves.PRESET_BOOKSHELVES["Want to Read"],
    Bookshelves.PRESET_BOOKSHELVES["Currently Reading"],
    Bookshelves.PRESET_BOOKSHELVES["Already Read"],
]
TRENDING_NOW_LIMIT = 20
TRENDING_NOW_CACHE_SECS = 10


@cache.memoize(
    "memcache",
    key=lambda limit=TRENDING_NOW_LIMIT, page=1: cache.build_memcache_key("stats.trending_now", limit=int(limit), page=int(page)),
    expires=TRENDING_NOW_CACHE_SECS,
)
def _cached_get_trending_now(limit: int = TRENDING_NOW_LIMIT, page: int = 1) -> list[dict]:
    rows = Bookshelves.get_recently_logged_books(shelf_ids=DEFAULT_TRENDING_SHELF_IDS, limit=limit, page=page)
    result = []
    for row in rows:
        d = dict(row)
        if isinstance(d.get("created"), dt.date):
            d["created"] = d["created"].isoformat()
        if isinstance(d.get("updated"), dt.date):
            d["updated"] = d["updated"].isoformat()
        result.append(d)
    return result


def cached_get_trending_now(limit: int = TRENDING_NOW_LIMIT, page: int = 1) -> list[web.storage]:
    items = _cached_get_trending_now(limit=limit, page=page)
    result = []
    for item in items:
        d = web.storage(item)
        if isinstance(d.get("created"), str):
            with contextlib.suppress(ValueError):
                d["created"] = dt.datetime.fromisoformat(d["created"])
        if isinstance(d.get("updated"), str):
            with contextlib.suppress(ValueError):
                d["updated"] = dt.datetime.fromisoformat(d["updated"])
        result.append(d)
    return result


async def get_trending_books(
    since_days=1,
    since_hours=0,
    limit=18,
    page=1,
    sort_by_count=True,
    minimum=0,
    fields: Iterable[str] | None = None,
):
    logged_books = (
        cached_get_trending_now(limit=limit, page=page)
        if (since_days == 0 and since_hours == 0)
        else Bookshelves.most_logged_books(
            shelf_ids=DEFAULT_TRENDING_SHELF_IDS,
            since=dateutil.todays_date_minus(days=since_days, hours=since_hours),
            limit=limit,
            page=page,
            sort_by_count=sort_by_count,
            minimum=minimum,
        )
    )
    await Bookshelves.add_solr_works_async(logged_books, fields=fields)

    return [book["work"] for book in logged_books if book.get("work")]


@cache.memoize("memcache", "stats.trending", expires=dateutil.HOUR_SECS)
def cached_get_most_logged_books(
    shelf_ids: list[int] | None = None,
    since_days: int | None = 1,
    limit: int = 20,
    page: int = 1,
):
    return Bookshelves.most_logged_books(
        shelf_ids=shelf_ids,
        since=dateutil.date_n_days_ago(since_days),
        limit=limit,
        page=page,
    )


def reading_log_leaderboard(limit: int):
    # enable to work w/ cached
    if "env" not in web.ctx:
        delegate.fakeload()

    most_read = Bookshelves.most_logged_books(shelf_ids=[Bookshelves.PRESET_BOOKSHELVES["Already Read"]], limit=limit)
    most_wanted_all = Bookshelves.most_logged_books(shelf_ids=[Bookshelves.PRESET_BOOKSHELVES["Want to Read"]], limit=limit)
    most_wanted_month = Bookshelves.most_logged_books(
        shelf_ids=[Bookshelves.PRESET_BOOKSHELVES["Want to Read"]],
        limit=limit,
        since=dateutil.DATE_ONE_MONTH_AGO,
    )
    return {
        "leaderboard": {
            "most_read": most_read,
            "most_wanted_all": most_wanted_all,
            "most_wanted_month": most_wanted_month,
            "most_rated_all": Ratings.most_rated_books_sync(),
        }
    }


def get_cached_reading_log_stats(limit: int):
    @cache.memoize("memcache", "stats.readling_log_leaderboard", expires=dateutil.HOUR_SECS)
    def cached_reading_log_leaderboard(limit: int):
        return reading_log_leaderboard(limit)

    stats = reading_log_summary()
    stats.update(cached_reading_log_leaderboard(limit))
    return stats


class stats(app.view):
    path = "/stats"

    def GET(self):
        counts = get_counts()
        counts.reading_log = reading_log_summary()
        return app.render_template("admin/index", counts)


class lending_stats(app.view):
    path = "/stats/lending(?:/%s/(.+))?" % LENDING_TYPES

    def GET(self, key, value):
        raise web.seeother("/")


class activity_stream(app.view):
    path = "/trending(/?.*)"

    def GET(self, mode=""):
        i = web.input(page=1)
        page = int(i.page or 1)
        if not mode:
            raise web.seeother("/trending/now")
        mode = mode[1:]  # remove slash
        limit = TRENDING_NOW_LIMIT
        if mode == "now":
            logged_books = cached_get_trending_now(limit=limit, page=page)
        else:
            logged_books = cached_get_most_logged_books(
                shelf_ids=DEFAULT_TRENDING_SHELF_IDS,
                since_days=SINCE_DAYS[mode],
                limit=limit,
                page=page,
            )
        Bookshelves.add_solr_works(logged_books)
        return app.render_template("trending", logged_books=logged_books, mode=mode)


class readinglog_stats(app.view):
    path = "/stats/readinglog"

    def GET(self):
        MAX_LEADERBOARD_SIZE = 50
        i = web.input(limit="10", mode="all")
        limit = min(int(i.limit), MAX_LEADERBOARD_SIZE)

        stats = get_cached_reading_log_stats(limit)

        all_keys = {f"/works/OL{item['work_id']}W" for leaderboard in stats["leaderboard"].values() for item in leaderboard}
        solr_docs = get_solr_works(all_keys)

        # Batch-fetch any works Solr missed in a single call instead of
        # one web.ctx.site.get() per work (N+1).
        miss_keys = [key for key in all_keys if key not in solr_docs]
        db_works = {w.key: w for w in web.ctx.site.get_many(miss_keys)} if miss_keys else {}

        # Fetch works from solr and inject into leaderboard
        for leaderboard in stats["leaderboard"].values():
            for item in leaderboard:
                key = f"/works/OL{item['work_id']}W"
                if key in solr_docs:
                    item["work"] = solr_docs[key]
                else:
                    item["work"] = db_works.get(key)

        works = [item["work"] for leaderboard in stats["leaderboard"].values() for item in leaderboard]

        availabilities = get_availabilities(works)
        for leaderboard in stats["leaderboard"].values():
            for item in leaderboard:
                if availabilities.get(item["work"]["key"]):
                    item["availability"] = availabilities.get(item["work"]["key"])

        return app.render_template("stats/readinglog", stats=stats)


def format_count(value: int | None) -> str:
    return "—" if value is None else commify(value)


def format_change(latest: int | None, earlier: int | None) -> dict | None:
    "The change from `earlier` to `latest` as a percentage, for a card's delta line. None without an earlier value to compare."
    if latest is None or not earlier:
        return None
    change = (latest - earlier) / earlier * 100
    direction = "up" if change >= 0.5 else "down" if change <= -0.5 else "flat"
    return {"direction": direction, "text": f"{abs(change):.1f}%"}


def build_tasks_stats_cards(counts: dict) -> list[dict]:
    """One card per metric the main chart can show, each on the trailing 28 days. `metric` is the chart's name for it."""
    cards = {
        "editors": ("catalog_editors_28d", _("Editors")),
        "new_editors": ("new_catalog_editors_28d", _("First-time editors")),
        "saves": ("tasks_saves_28d", _("Tasks saves")),
        "tasks_editors": ("tasks_editors_28d", _("Tasks editors")),
    }
    result = []
    for metric, (key, label) in cards.items():
        latest, earlier = (counts.get(key) or {}).get("latest"), (counts.get(key) or {}).get("earlier")
        result.append({"metric": metric, "label": label, "value": format_count(latest), "change": format_change(latest, earlier)})
    return result


def build_undone(counts: dict) -> dict:
    "Undone Tasks saves over the trailing 28 days, with their share of all Tasks saves in the same window."
    undone, saves = (counts.get("tasks_saves_undone_28d") or {}).get("latest"), (counts.get("tasks_saves_28d") or {}).get("latest")
    return {"undone": format_count(undone), "saves": format_count(saves), "share": f"{undone / saves:.1%}" if undone is not None and saves else "—"}


def build_initiative(counts: dict) -> dict:
    "The active initiative's latest snapshot. Each key is `None` until the stats script has taken one."

    def latest(key: str) -> int | None:
        return (counts.get(key) or {}).get("latest")

    open_gaps, editions = latest("initiative_open_gaps"), latest("initiative_editions")
    slots = (editions or 0) * len(tasks.POINTS)
    return {
        "title": _("Most-read %(count)s", count=commify(initiatives.ACTIVE.size)),
        "open": format_count(open_gaps),
        "done": format_count(latest("initiative_done_editions")),
        "not_found": format_count(latest("initiative_not_found")),
        "editions": format_count(editions),
        # Rounded down, like initiatives.progress, so it only reads 100% when nothing is left.
        "percent": f"{(slots - open_gaps) * 100 // slots}%" if open_gaps is not None and slots else "—",
    }


def build_saves_by_field(docs: list[dict]) -> list[dict]:
    "Tasks saves over `docs` by the field they filled, most first, each with its share of the total."
    totals: dict[str, int] = {}
    for doc in docs:
        for field, count in (doc.get("tasks_saves_by_field_1d") or {}).items():
            totals[field] = totals.get(field, 0) + count
    total, peak = sum(totals.values()), max(totals.values(), default=0)
    guides = get_field_guides()
    return [
        {
            "label": guides[field].label if field in guides else field,
            "count": commify(count),
            "share": f"{count / total:.0%}",
            "width": round(count / peak * 100),
        }
        for field, count in sorted(totals.items(), key=lambda item: -item[1])
    ]


def build_tasks_stats_i18n() -> dict[str, str]:
    "Strings the page's script draws on its charts. Keys and English text match DEFAULT_STRINGS in tasks_stats.js."
    return {
        "perDay": _("Per day"),
        "perWeek": _("Per week"),
        "perMonth": _("Per 4 weeks"),
        "previousPeriod": _("Previous period"),
        "previousValue": _("Previous period: %(count)s"),
        "change": _("%(change)s vs previous period"),
        "todaySoFar": _("Today so far, updated hourly"),
        "periodSoFar": _("Still in progress"),
        "openDetails": _("%(count)s details still open"),
        "initiativeSaves": _("%(count)s saves on the list"),
        "undoneShare": _("%(share)s undone: %(undone)s of %(saves)s saves in the 28 days to this day"),
        "noData": _("No counts for this range yet."),
        "loadFailed": _("The charts couldn't load. Reload the page to try again."),
    }


def build_tasks_stats_page() -> dict:
    keys = [
        "catalog_editors_28d",
        "new_catalog_editors_28d",
        "tasks_saves_28d",
        "tasks_editors_28d",
        "tasks_saves_undone_28d",
        "initiative_open_gaps",
        "initiative_done_editions",
        "initiative_not_found",
        "initiative_editions",
    ]
    counts = get_rolling_counts(keys, 1)
    return {
        "cards": build_tasks_stats_cards(counts),
        "undone": build_undone(counts),
        "initiative": build_initiative(counts),
        "saves_by_field": build_saves_by_field(get_count_docs(28)),
        "i18n": build_tasks_stats_i18n(),
    }


class tasks_stats(app.view):
    path = "/stats/tasks"

    def GET(self):
        return app.render_template("stats/tasks", page=build_tasks_stats_page())
