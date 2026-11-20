"""Daily change counts behind the chart on /recentchanges and its per-kind pages."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from psycopg.errors import QueryCanceled
from pydantic import BaseModel

from openlibrary.core import cache
from openlibrary.core.async_db import connection, fetch_all
from openlibrary.fastapi.auth import LibrarianDep  # noqa: TC001
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


# Edits where any record they saved contains the text, in the revision that edit wrote. `transaction.changes` lists
# the (key, revision) pairs each edit saved and `data` holds every revision in full. The lookups are scalar subqueries
# so each one is a single index probe per saved record: as joins, the planner may hash or scan `thing` or `data`.
# Still reads the full JSON of every record edited in the range.
_MATCH_COUNTS_SQL = """
SELECT t.created::date AS day, count(*) AS n
FROM transaction t
WHERE t.created >= %(since)s AND (%(kind)s::text IS NULL OR t.action = %(kind)s)
AND EXISTS (
    SELECT 1 FROM jsonb_array_elements(t.changes::jsonb) AS change
    WHERE strpos(lower((
        SELECT data.data FROM data
        WHERE data.thing_id = (SELECT thing.id FROM thing WHERE thing.key = change->>'key')
        AND data.revision = (change->>'revision')::int
    )), %(text)s) > 0
)
GROUP BY day
"""
MATCH_TIMEOUT = "60s"


class RecentChangesMatches(BaseModel):
    dates: list[str]
    """One ISO date (UTC) per calendar day, oldest first, ending today."""
    matches: list[int]
    """Changes per day that saved a record containing the text."""


async def daily_match_counts(text: str, kind: str | None, days: int) -> dict[str, Any]:
    today = date.today()
    dates = [today - timedelta(days=i) for i in reversed(range(days))]
    async with connection() as conn:
        await conn.execute(f"SET LOCAL statement_timeout = '{MATCH_TIMEOUT}'")
        cursor = await conn.execute(_MATCH_COUNTS_SQL, {"since": dates[0], "kind": kind, "text": text.lower()})
        counts = {row["day"]: row["n"] for row in await cursor.fetchall()}
    return {"dates": [d.isoformat() for d in dates], "matches": [counts.get(d, 0) for d in dates]}


@cache.memoize(engine="memcache", key="recentchanges.daily_match_counts", expires=HALF_HOUR_SECS)
def _cached_daily_match_counts(text: str, kind: str | None, days: int) -> dict[str, Any]:
    return async_bridge.run(daily_match_counts(text, kind, days))


# Librarians only: each uncached search reads every record edited in the range.
@router.get("/stats/recentchanges/matches.json", response_model=RecentChangesMatches)
def recentchanges_matches(
    _: LibrarianDep,
    q: Annotated[str, Query(min_length=3, max_length=100, description="Text to look for, case-insensitively, in each edited record as that edit saved it.")],
    kind: Annotated[str | None, Query(max_length=64, description="Change kind, e.g. add-book; all kinds if omitted.")] = None,
    days: Annotated[int, Query(gt=0, le=MAX_DAYS, description="How many days up to today.")] = 28,
) -> RecentChangesMatches:
    """Changes per day whose saved records contain `q`."""
    try:
        return RecentChangesMatches(**_cached_daily_match_counts(q.strip().lower(), kind or None, days))
    except QueryCanceled:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=f"Search took longer than {MATCH_TIMEOUT}; try a shorter range.")
