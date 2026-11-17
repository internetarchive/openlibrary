"""Loan Stats"""

import contextlib
import datetime as dt
from collections.abc import Iterable

import web

from infogami.utils import delegate
from openlibrary.utils.request_context import site

from .. import app
from ..contribute import initiatives
from ..contribute.field_guides import get_field_guides
from ..core import cache
from ..core.admin import get_count_docs, initiative_counts, rolling_counts
from ..core.booknotes import Booknotes
from ..core.bookshelves import Bookshelves
from ..core.follows import PubSub
from ..core.helpers import commify, format_date
from ..core.lending import get_availabilities
from ..core.observations import Observations
from ..core.ratings import Ratings
from ..core.yearly_reading_goals import YearlyReadingGoals
from ..i18n import gettext as _
from ..i18n import ungettext
from ..plugins.admin.code import get_counts
from ..plugins.worksearch.code import get_solr_works
from ..utils import dateutil
from ..utils.request_context import set_context_from_legacy_web_py

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
        set_context_from_legacy_web_py()

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
        set_context_from_legacy_web_py()

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
        # one site.get().get() per work (N+1).
        miss_keys = [key for key in all_keys if key not in solr_docs]
        db_works = {w.key: w for w in site.get().get_many(miss_keys)} if miss_keys else {}

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


def card(metric: str, label: str, note: str, value: str, change: dict | None = None, detail: str = "", split: dict | None = None) -> dict:
    "One metric card. `metric` is the main chart's name for it, and `note` says what one of its bars counts."
    return {"metric": metric, "label": label, "note": note, "value": value, "change": change, "detail": detail, "split": split}


def counted(counts: dict, key: str) -> tuple[int | None, dict | None]:
    "A rolling count's latest value and its change from the 28 days before."
    value = latest(counts, key)
    return value, format_change(value, (counts.get(key) or {}).get("earlier"))


def share(part: float | None, whole: float | None) -> str | None:
    return f"{part / whole:.1%}" if part is not None and whole else None


def window_sum(docs: list[dict], key: str, days: list[str]) -> int | None:
    "`key` added up over `days` (count doc keys), None unless every one of them has it: a partial sum would read as a drop."
    by_key = {d["_key"]: d for d in docs}
    values: list[int | None] = [by_key.get(day, {}).get(key) for day in days]
    return None if any(v is None for v in values) else sum(v or 0 for v in values)


def day_keys(end: dt.date, days: int = 28) -> list[str]:
    return [(end - dt.timedelta(days=i)).strftime("counts-%Y-%m-%d") for i in range(days)]


def build_editing_cards(counts: dict, docs: list[dict], today: dt.date) -> list[dict]:
    "The All editing cards, each on the trailing 28 days."
    editors, editors_change = counted(counts, "catalog_editors_28d")
    first_time = latest(counts, "new_catalog_editors_28d")
    edits = window_sum(docs, "catalog_edits", day_keys(today))
    edits_change = format_change(edits, window_sum(docs, "catalog_edits", day_keys(today - dt.timedelta(days=28))))
    tasks_saves, tasks_editors = latest(counts, "tasks_saves_28d"), latest(counts, "tasks_editors_28d")
    split = None
    if editors and first_time is not None:
        split = {
            "returning": commify(editors - first_time),
            "first_time": commify(first_time),
            "first_time_width": round(first_time / editors * 100, 1),
        }
    return [
        card(
            "editors",
            _("Editors"),
            _("People who changed a book, work or author record, and those whose first edit ever it was. Week and month views count each person once."),
            format_count(editors),
            editors_change,
            split=split,
        ),
        card(
            "edits",
            _("Edits"),
            _("Edits saved by people, not bots: to books, works, authors and other pages, to lists, and from the Tasks page."),
            format_count(edits),
            edits_change,
            detail=_("≈ %(count)s per editor", count=commify(round(edits / editors))) if edits and editors else "",
        ),
        card(
            "tasks_share",
            _("Through Tasks"),
            _("The share of edits saved from the Tasks page."),
            share(tasks_saves, edits) or "—",
            # "of edits" belongs to the value, so it shows only with one.
            detail=_("of edits · %(share)s of editors", share=share(tasks_editors, editors))
            if share(tasks_saves, edits) and share(tasks_editors, editors)
            else "",
        ),
    ]


def build_tasks_stats_cards(counts: dict, edits: int | None) -> list[dict]:
    "The Through Tasks cards, each on the trailing 28 days."
    saves, saves_change = counted(counts, "tasks_saves_28d")
    editors, editors_change = counted(counts, "tasks_editors_28d")
    all_editors = latest(counts, "catalog_editors_28d")
    return [
        card(
            "saves",
            _("Tasks saves"),
            _("Edits saved from the Tasks page."),
            format_count(saves),
            saves_change,
            detail=_("%(share)s of all edits", share=share(saves, edits)) if share(saves, edits) else "",
        ),
        card(
            "tasks_editors",
            _("Tasks editors"),
            _("People who saved an edit from the Tasks page. In week and month views, someone who saved on several days counts once."),
            format_count(editors),
            editors_change,
            detail=_("%(share)s of all editors", share=share(editors, all_editors)) if share(editors, all_editors) else "",
        ),
        card(
            "saves_per_editor",
            _("Saves per Tasks editor"),
            _("Tasks saves for each person who saved one."),
            f"{saves / editors:.1f}" if saves is not None and editors else "—",
            detail=_("vs ≈ %(count)s edits per editor overall", count=commify(round(edits / all_editors))) if edits and all_editors else "",
        ),
    ]


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


def format_people(people: int | None) -> str:
    "How many people have saved for an initiative, as a figure line: a bold count and its noun."
    if people is None:
        return _("<b>—</b> people have helped")
    return ungettext("<b>%(count)s</b> person has helped", "<b>%(count)s</b> people have helped", people, count=commify(people))


def build_initiatives(docs: list[dict]) -> list[dict]:
    """Every initiative in the registry with its latest snapshot, headline one first selected. A figure is a dash until the
    stats script has counted that initiative, which it does from the first run after its list is frozen."""
    by_day = [initiative_counts(doc) for doc in reversed(docs)]
    result = []
    headline = initiatives.headline().slug
    for initiative in initiatives.listed():
        snap = next((day[initiative.slug] for day in by_day if initiative.slug in day), {})
        open_gaps, editions = snap.get("open"), snap.get("editions")
        slots = (editions or 0) * len(initiative.fields)
        result.append(
            initiatives.describe(initiative)
            | {
                "slug": initiative.slug,
                "on": initiative.slug == headline,
                "finished": initiative.status() == "ended",
                "open": format_count(open_gaps),
                "done": format_count(snap.get("done")),
                "not_found": format_count(snap.get("not_found")),
                "editions": format_count(editions),
                "people": format_people(snap.get("people")),
                # Rounded down, like initiatives.progress, so it only reads 100% when nothing is left.
                # Snapshots since work details were counted once per work carry the percent; older ones are worked out here.
                "percent": f"{snap['percent']}%" if "percent" in snap else f"{(slots - open_gaps) * 100 // slots}%" if open_gaps is not None and slots else "—",
            }
        )
    return result


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
        "earlier7": _("A week earlier"),
        "earlier28": _("4 weeks earlier"),
        "earlierValue7": _("A week earlier: %(count)s"),
        "earlierValue28": _("4 weeks earlier: %(count)s"),
        "earlierChange7": _("%(change)s vs a week earlier"),
        "earlierChange28": _("%(change)s vs 4 weeks earlier"),
        "cardChange7": _("%(change)s vs previous 7 days"),
        "cardChange28": _("%(change)s vs previous 28 days"),
        "split": _("%(returning)s returning · %(first_time)s first-time"),
        "perEditor": _("≈ %(count)s per editor"),
        "tasksShareDetail": _("of edits · %(share)s of editors"),
        "shareOfEdits": _("%(share)s of all edits"),
        "shareOfEditors": _("%(share)s of all editors"),
        "perEditorOverall": _("vs ≈ %(count)s edits per editor overall"),
        "todaySoFar": _("Today so far, updated hourly"),
        "periodSoFar": _("Still in progress"),
        "openDetails": _("%(count)s details still open"),
        "tasksUndone": _("Tasks: %(share)s undone, %(undone)s of %(total)s saves"),
        "otherUndone": _("Outside Tasks: %(share)s undone, %(undone)s of %(total)s fills"),
        "noData": _("No counts for this range yet."),
        "returning": _("Returning"),
        "firstTime": _("First edit ever"),
        "otherEdits": _("Records and other pages"),
        "lists": _("Lists"),
        "tasks": _("Tasks"),
        "total": _("Total: %(count)s"),
        "ofEdits": _("Of edits"),
        "ofEditors": _("Of editors"),
        "loadFailed": _("The charts couldn't load. Reload the page to try again."),
    }


SCOPES = ("all", "tasks")
# The first day the stats script wrote `catalog_edits` (openlibrary/admin/numbers.py), so edit charts start there.
EDITS_COUNTED_SINCE = dt.datetime(2026, 10, 15)


def build_tasks_stats_page(scope: str = "all") -> dict:
    keys = [
        "catalog_editors_28d",
        "new_catalog_editors_28d",
        "tasks_saves_28d",
        "tasks_editors_28d",
        "tasks_saves_undone_28d",
        "other_fills_28d",
        "other_fills_undone_28d",
    ]
    # 56 days: two 28-day windows of daily edits to compare. Rolling counts compare today with 28 days before.
    docs = get_count_docs(56)
    counts = rolling_counts(docs, keys)
    today = dt.date.today()
    edits = window_sum(docs, "catalog_edits", day_keys(today))
    since = (today - dt.timedelta(days=27)).strftime("counts-%Y-%m-%d")
    return {
        "scope": scope if scope in SCOPES else "all",
        "cards": {
            "all": build_editing_cards(counts, docs, today),
            "tasks": build_tasks_stats_cards(counts, edits),
        },
        "guardrail": build_guardrail(counts),
        "initiatives": build_initiatives(docs),
        "saves_by_field": build_saves_by_field([d for d in docs if d["_key"] >= since]),
        "i18n": build_tasks_stats_i18n(),
        "edits_since": format_date(EDITS_COUNTED_SINCE),
    }


class tasks_stats(app.view):
    path = "/stats/tasks"

    def GET(self):
        return app.render_template("stats/tasks", page=build_tasks_stats_page(web.input(scope="all", _method="GET").scope))
