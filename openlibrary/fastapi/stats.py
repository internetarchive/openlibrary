"""Catalog statistics backed by the daily count documents."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from openlibrary.admin.numbers import TAG_STATS_FIELDS
from openlibrary.core import admin, cache
from openlibrary.core.helpers import commify
from openlibrary.core.jinja import render_jinja_template
from openlibrary.core.shell.request import PageMeta
from openlibrary.fastapi.shared.site_page import SitePage, SitePageRoute
from openlibrary.i18n import gettext as _
from openlibrary.utils.dateutil import MINUTE_SECS
from openlibrary.utils.request_context import get_request_lang, site

router = APIRouter()
pages = APIRouter(route_class=SitePageRoute)

# Enough for a 12-month view with a previous period to compare the first weeks against.
MAX_DAYS = 400
# The keys the page may ask for. `_1d` keys are per day; 7d and 28d are rolling windows ending that day; the
# initiatives' snapshots come separately. All written by scripts/store_counts.py from openlibrary/admin/numbers.py.
SERIES_KEYS = (
    "book_edits",
    "book_editors_1d",
    "book_editors_7d",
    "book_editors_28d",
    "new_book_editors_1d",
    "new_book_editors_7d",
    "new_book_editors_28d",
    "tasks_saves_1d",
    "tasks_saves_28d",
    "tasks_saves_undone_28d",
    "other_fills_28d",
    "other_fills_undone_28d",
    "tasks_editors_1d",
    "tasks_editors_7d",
    "tasks_editors_28d",
)


class TasksSeries(BaseModel):
    dates: list[str]
    """One ISO date per calendar day, oldest first, ending today, which is still being gathered. Every list below lines up with it."""
    series: dict[str, list[int | None]]
    """Each key in `SERIES_KEYS`; None on a day without a count."""
    saves_by_field: list[dict[str, int] | None]
    """The day's Tasks saves by field filled."""
    initiatives: dict[str, list[int | None]]
    """Details still open on each initiative's list, by slug; None on a day without its snapshot."""


# Plain def: the store reads are blocking I/O, so the route runs in the threadpool.
@cache.memoize(engine="memcache", key="stats.tasks_count_docs", expires=15 * MINUTE_SECS)
def _count_docs_by_day() -> dict[str, dict]:
    """The last `MAX_DAYS` count docs, by date. Gathered hourly, so a quarter hour of staleness is within noise."""
    return {doc["_key"].removeprefix("counts-"): doc for doc in admin.read_count_docs(site.get(), MAX_DAYS)}


def initiative_series(day_docs: list[dict]) -> dict[str, list[int | None]]:
    """Each initiative's open details across ``day_docs``, for every initiative any of them has a snapshot of."""
    by_day = [admin.initiative_counts(doc) for doc in day_docs]
    slugs = dict.fromkeys(slug for counts in by_day for slug in counts)
    return {slug: [counts.get(slug, {}).get("open") for counts in by_day] for slug in slugs}


@router.get("/stats/tasks.json", response_model=TasksSeries)
def tasks_series(
    days: Annotated[int, Query(gt=0, le=MAX_DAYS, description="How many days up to today.")] = 90,
) -> TasksSeries:
    """The counts behind /stats/tasks as aligned daily series, one entry per calendar day whether or not it was gathered."""
    docs = _count_docs_by_day()
    today = date.today()
    dates = [(today - timedelta(days=i)).isoformat() for i in reversed(range(days))]
    day_docs = [docs.get(d, {}) for d in dates]
    return TasksSeries(
        dates=dates,
        series={key: [doc.get(key) for doc in day_docs] for key in SERIES_KEYS},
        saves_by_field=[doc.get("tasks_saves_by_field_1d") for doc in day_docs],
        initiatives=initiative_series(day_docs),
    )


def _tag_creation_cards(docs: list[dict], today: date) -> list[dict]:
    lang = get_request_lang()
    periods = [(7, _("Last 7 days")), (28, _("Last 28 days")), (365, _("Last 365 days"))]
    cards = []
    for days, label in periods:
        since = f"counts-{today - timedelta(days=days - 1)}"
        daily = [doc for doc in docs if doc["_key"] >= since and "tags" in doc]
        stats = admin.Stats(daily, "tags", "total_tags")
        cards.append(
            {
                "label": label,
                "value": commify(stats.get_summary(days), lang) if len(daily) == days else None,
                "chart": stats.get_bar_chart(days, width=250, height=35) if daily else None,
                "chart_label": _("Tags created per day"),
            }
        )
    total_docs = [doc for doc in docs if "total_tags" in doc]
    totals = admin.Stats(total_docs, "total_tags", "total_tags")
    cards.append(
        {
            "label": _("All time"),
            "value": commify(totals.total, lang) if total_docs else None,
            "chart": totals.get_bar_chart(365, width=250, height=35) if total_docs else None,
            "chart_label": _("Total tags by day"),
        }
    )
    return cards


def _tagged_work_rows(docs: list[dict]) -> list[dict]:
    label_by_field = {
        "genres": _("Genres"),
        "subgenres": _("Subgenres"),
        "literary_forms": _("Literary forms"),
        "audiences": _("Audiences"),
        "content_warnings": _("Content warnings"),
        "content_formats": _("Content formats"),
        "awards": _("Awards"),
    }
    key = "total_tagged_works"
    windows = [admin.rolling_counts(docs, [key], lookback=days)[key] for days in (7, 28, 365)]
    latest = windows[0]["latest"] if windows[0] else {}
    earlier = [window["earlier"] if window else None for window in windows]
    lang = get_request_lang()
    rows = []
    for field in TAG_STATS_FIELDS:
        count = latest.get(field)
        changes = [count - past[field] if count is not None and past is not None and field in past else None for past in earlier]
        rows.append(
            {
                "label": label_by_field[field],
                "total": commify(count, lang) if count is not None else None,
                "changes": [("+" if change > 0 else "") + commify(change, lang) if change is not None else None for change in changes],
            }
        )
    return rows


@pages.get("/stats/tags")
def tags_stats() -> SitePage:
    docs = admin.get_count_docs(MAX_DAYS)
    body = render_jinja_template(
        "stats/tags.html.jinja",
        cards=_tag_creation_cards(docs, date.today()),
        rows=_tagged_work_rows(docs),
    )
    return SitePage(body, page=PageMeta(title=_("Book Tag Stats"), cssfile="admin"))
