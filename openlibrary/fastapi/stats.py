"""The daily series behind /stats/tasks, for a chart that can pick its own range and granularity."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from openlibrary.core import admin, cache
from openlibrary.utils.dateutil import MINUTE_SECS
from openlibrary.utils.request_context import site

router = APIRouter()

# Enough for a 12-month view with a previous period to compare the first weeks against.
MAX_DAYS = 400
# The keys the page may ask for. `_1d` keys are per day; 7d and 28d are rolling windows ending that day; the
# `initiative_*` keys are nightly snapshots. All written by scripts/store_counts.py from openlibrary/admin/numbers.py.
SERIES_KEYS = (
    "catalog_editors_1d",
    "catalog_editors_7d",
    "catalog_editors_28d",
    "new_catalog_editors_1d",
    "new_catalog_editors_7d",
    "new_catalog_editors_28d",
    "tasks_saves_1d",
    "tasks_saves_28d",
    "tasks_saves_undone_28d",
    "tasks_editors_1d",
    "tasks_editors_7d",
    "tasks_editors_28d",
    "tasks_saves_initiative_1d",
    "initiative_open_gaps",
    "initiative_done_editions",
    "initiative_not_found",
    "initiative_editions",
)


class TasksSeries(BaseModel):
    dates: list[str]
    """One ISO date per calendar day, oldest first, ending today, which is still being gathered. Every list below lines up with it."""
    series: dict[str, list[int | None]]
    """Each key in `SERIES_KEYS`; None on a day the stats script hadn't written it."""
    saves_by_field: list[dict[str, int] | None]
    """The day's Tasks saves by field filled."""
    initiative: list[str | None]
    """Which initiative the day's `initiative_*` values describe."""


# Plain def: the store reads are blocking I/O, so the route runs in the threadpool.
@cache.memoize(engine="memcache", key="stats.tasks_count_docs", expires=15 * MINUTE_SECS)
def _count_docs_by_day() -> dict[str, dict]:
    """The last `MAX_DAYS` count docs, by date. Gathered hourly, so a quarter hour of staleness is within noise."""
    return {doc["_key"].removeprefix("counts-"): doc for doc in admin.read_count_docs(site.get(), MAX_DAYS)}


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
        initiative=[doc.get("initiative_slug") for doc in day_docs],
    )
