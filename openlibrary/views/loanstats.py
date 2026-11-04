"""Loan Stats"""

import contextlib
import datetime as dt
from collections.abc import Iterable
from math import ceil
from typing import TypedDict

import web

from infogami.utils import delegate

from .. import app
from ..contribute import initiatives, tasks
from ..contribute.field_guides import get_field_guides
from ..core import cache
from ..core.admin import get_count_docs, rolling_counts
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
from ..plugins.worksearch.code import get_solr_works, work_search_async
from ..utils import dateutil
from ..utils.async_utils import async_bridge

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


# The chart is the top 200 of a period: ten pages of twenty. A book's "weeks on list" is its streak
# of consecutive periods in that top 200, so each period looks back `blocks` periods to count it.
TRENDING_LIST_SIZE = 200
CHART_PERIODS: dict[str, tuple[int | None, int]] = {
    "daily": (dateutil.DAY_SECS, 30),
    "weekly": (dateutil.WEEK_SECS, 52),
    "monthly": (30 * dateutil.DAY_SECS, 24),
    "yearly": (365 * dateutil.DAY_SECS, 10),
    "forever": (None, 1),
}
# Another view of the weekly chart. The remaining tabs, rising (Solr's z-score) and now (the live
# stream), aren't charts.
CHART_VIEWS = ("breakouts",)


class ChartEntry(TypedDict):
    work_id: int
    rank: int
    cnt: int
    delta: int | None
    """Places climbed since the previous period, negative for a fall; None when new to the list."""
    streak: int
    """Consecutive periods on the list, counting this one."""


def build_chart(rows: Iterable[dict]) -> list[ChartEntry]:
    """Rank the current block of ``Bookshelves.period_rankings`` rows, with each book's move and streak."""
    by_block: dict[int, dict[int, dict]] = {}
    for row in rows:
        by_block.setdefault(row["block"], {})[row["work_id"]] = row
    previous = by_block.get(1, {})
    chart: list[ChartEntry] = []
    for work_id, row in sorted(by_block.get(0, {}).items(), key=lambda item: item[1]["rank"]):
        streak = 1
        while work_id in by_block.get(streak, {}):
            streak += 1
        prev = previous.get(work_id)
        chart.append({"work_id": work_id, "rank": row["rank"], "cnt": row["cnt"], "delta": prev["rank"] - row["rank"] if prev else None, "streak": streak})
    return chart


@cache.memoize(
    "memcache",
    key=lambda period: cache.build_memcache_key("stats.trending_chart", period=period),
    expires=dateutil.HOUR_SECS,
)
def cached_chart(period: str) -> list[ChartEntry]:
    period_secs, blocks = CHART_PERIODS[period]
    # `created` is a naive UTC timestamp.
    now = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    rows = async_bridge.run(Bookshelves.period_rankings(DEFAULT_TRENDING_SHELF_IDS, period_secs, blocks, TRENDING_LIST_SIZE, now))
    return build_chart(rows)


def chart_for(mode: str) -> list[ChartEntry]:
    if mode == "breakouts":
        # This week without the all-time favourites, so the perennials don't own every list.
        perennial = {entry["work_id"] for entry in cached_chart("forever")}
        return [entry for entry in cached_chart("weekly") if entry["work_id"] not in perennial]
    return cached_chart(mode)


async def rising_work_ids(limit: int, page: int) -> list[dict]:
    """Works by Solr's trending z-score: unusual attention in the last day against the book's own past week."""
    results = await work_search_async({"q": "*:*"}, sort="trending", page=page, limit=limit, fields="key", facet=False, request_label="TRENDING_PAGE")
    return [{"work_id": int(doc["key"].split("/OL")[1][:-1])} for doc in results.get("docs", []) if doc.get("key", "").endswith("W")]


@cache.memoize(
    "memcache",
    key=lambda limit, page: cache.build_memcache_key("stats.trending_rising", limit=int(limit), page=int(page)),
    expires=dateutil.MINUTE_SECS * 10,
)
def cached_rising_work_ids(limit: int, page: int) -> list[dict]:
    return async_bridge.run(rising_work_ids(limit, page))


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
            raise web.seeother("/trending/rising")
        mode = mode[1:]  # remove slash
        limit = TRENDING_NOW_LIMIT
        total_pages = TRENDING_LIST_SIZE // limit
        if mode == "now":
            logged_books = cached_get_trending_now(limit=limit, page=page)
        elif mode == "rising":
            logged_books = cached_rising_work_ids(limit, page)
        elif mode in CHART_PERIODS or mode in CHART_VIEWS:
            chart = chart_for(mode)
            total_pages = ceil(len(chart) / limit)
            logged_books = chart[(page - 1) * limit : page * limit]
        else:
            raise web.notfound()
        Bookshelves.add_solr_works(logged_books)
        return app.render_template("trending", logged_books=logged_books, mode=mode, page=page, total_pages=total_pages, rank_offset=(page - 1) * limit)


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


def latest(counts: dict, key: str) -> int | None:
    "A rolling count's latest value, None if the stats script hasn't written it."
    return (counts.get(key) or {}).get("latest")


def build_tasks_stats_cards(counts: dict) -> list[dict]:
    """One card per metric the main chart can show, each on the trailing 28 days. `metric` is the chart's name for it, and
    `note` says what one of its bars counts."""
    cards = {
        "editors": (
            "catalog_editors_28d",
            _("Editors"),
            _("People who changed a book, work or author record. In week and month views, someone who edited on several days counts once."),
        ),
        "new_editors": (
            "new_catalog_editors_28d",
            _("First-time editors"),
            _("People who made their first edit ever on that day. Each person is counted once, on the day of their first edit."),
        ),
        "saves": ("tasks_saves_28d", _("Tasks saves"), _("Edits saved from the Tasks page.")),
        "tasks_editors": (
            "tasks_editors_28d",
            _("Tasks editors"),
            _("People who saved an edit from the Tasks page. In week and month views, someone who saved on several days counts once."),
        ),
    }
    result = []
    for metric, (key, label, note) in cards.items():
        value, earlier = latest(counts, key), (counts.get(key) or {}).get("earlier")
        result.append({"metric": metric, "label": label, "note": note, "value": format_count(value), "change": format_change(value, earlier)})
    return result


# Below this many saves (or fills) in the window, a share is mostly noise, so the page leaves it out.
GUARDRAIL_MIN_SAMPLE = 20


def build_undone_rate(counts: dict, undone_key: str, total_key: str) -> dict:
    "An undone count over the trailing 28 days, its total and the share: None without `GUARDRAIL_MIN_SAMPLE` behind it."
    undone, total = latest(counts, undone_key), latest(counts, total_key)
    share = f"{undone / total:.1%}" if undone is not None and total is not None and total >= GUARDRAIL_MIN_SAMPLE else None
    return {"undone": format_count(undone), "total": format_count(total), "share": share}


def build_guardrail(counts: dict) -> dict:
    """Tasks saves undone, beside the same check on the same fields filled outside Tasks, so the rate has something to
    be compared with."""
    return {
        "tasks": build_undone_rate(counts, "tasks_saves_undone_28d", "tasks_saves_28d"),
        "other": build_undone_rate(counts, "other_fills_undone_28d", "other_fills_28d"),
        "min_sample": GUARDRAIL_MIN_SAMPLE,
    }


def build_initiative(counts: dict) -> dict:
    "The active initiative's latest snapshot. Each key is `None` until the stats script has taken one."
    open_gaps, editions = latest(counts, "initiative_open_gaps"), latest(counts, "initiative_editions")
    slots = (editions or 0) * len(tasks.OFFERED)
    return {
        "title": _("Most-read %(count)s", count=commify(initiatives.ACTIVE.size)),
        "open": format_count(open_gaps),
        "done": format_count(latest(counts, "initiative_done_editions")),
        "not_found": format_count(latest(counts, "initiative_not_found")),
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
        "tasksUndone": _("Tasks: %(share)s undone, %(undone)s of %(total)s saves"),
        "otherUndone": _("Outside Tasks: %(share)s undone, %(undone)s of %(total)s fills"),
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
        "other_fills_28d",
        "other_fills_undone_28d",
        "initiative_open_gaps",
        "initiative_done_editions",
        "initiative_not_found",
        "initiative_editions",
    ]
    # 29 days: today, and the day 28 before it to compare with. The field breakdown takes the last 28.
    docs = get_count_docs(29)
    counts = rolling_counts(docs, keys)
    since = (dt.date.today() - dt.timedelta(days=27)).strftime("counts-%Y-%m-%d")
    return {
        "cards": build_tasks_stats_cards(counts),
        "guardrail": build_guardrail(counts),
        "initiative": build_initiative(counts),
        "saves_by_field": build_saves_by_field([d for d in docs if d["_key"] >= since]),
        "i18n": build_tasks_stats_i18n(),
    }


class tasks_stats(app.view):
    path = "/stats/tasks"

    def GET(self):
        return app.render_template("stats/tasks", page=build_tasks_stats_page())
