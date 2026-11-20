"""Daily change counts behind the chart on /recentchanges and its per-kind pages."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from openlibrary.core import cache
from openlibrary.core.async_db import fetch_all
from openlibrary.utils.async_utils import async_bridge
from openlibrary.utils.dateutil import HALF_HOUR_SECS

router = APIRouter()

MAX_DAYS = 365

# Bot accounts are flagged in the account store; their edits are attributed to the matching /people/ thing.
_DAILY_COUNTS_SQL = """
WITH bots AS (
    SELECT thing.id FROM store
    JOIN store_index ON store_index.store_id = store.id
    JOIN thing ON thing.key = '/people/' || split_part(store.key, '/', 2)
    WHERE store_index.type = 'account' AND store_index.name = 'bot' AND store_index.value = 'true'
)
SELECT
    created::date AS day,
    COALESCE(author_id IN (SELECT id FROM bots), false) AS is_bot,
    COALESCE(action, 'edit') AS kind,
    count(*) AS n
FROM transaction
WHERE created >= %(since)s AND (%(kind)s::text IS NULL OR action = %(kind)s)
GROUP BY day, is_bot, kind
"""


class RecentChangesCounts(BaseModel):
    dates: list[str]
    """One ISO date (UTC) per calendar day, oldest first, ending today, which is still being counted."""
    humans: list[int]
    bots: list[int]
    kinds: dict[str, list[int]]
    """Counts per change kind (infobase's `action`; `edit` where it has none)."""


async def daily_change_counts(kind: str | None, days: int) -> dict[str, Any]:
    today = date.today()
    dates = [today - timedelta(days=i) for i in reversed(range(days))]
    rows = await fetch_all(_DAILY_COUNTS_SQL, {"since": dates[0], "kind": kind})
    index = {d: i for i, d in enumerate(dates)}
    humans, bots = [0] * days, [0] * days
    kinds: dict[str, list[int]] = {}
    for row in rows:
        i = index[row["day"]]
        (bots if row["is_bot"] else humans)[i] += row["n"]
        kinds.setdefault(row["kind"], [0] * days)[i] += row["n"]
    return {"dates": [d.isoformat() for d in dates], "humans": humans, "bots": bots, "kinds": kinds}


@cache.memoize(engine="memcache", key="recentchanges.daily_counts_v2", expires=HALF_HOUR_SECS)
def _cached_daily_change_counts(kind: str | None, days: int) -> dict[str, Any]:
    return async_bridge.run(daily_change_counts(kind, days))


# Plain def: the memcache client is blocking, so the route runs in the threadpool.
@router.get("/stats/recentchanges.json", response_model=RecentChangesCounts)
def recentchanges_counts(
    kind: Annotated[str | None, Query(max_length=64, description="Change kind, e.g. add-book; all kinds if omitted.")] = None,
    days: Annotated[int, Query(gt=0, le=MAX_DAYS, description="How many days up to today.")] = 28,
) -> RecentChangesCounts:
    """Changes per day, split into human and bot edits."""
    return RecentChangesCounts(**_cached_daily_change_counts(kind or None, days))
