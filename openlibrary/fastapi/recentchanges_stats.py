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


# One page of a walk back through the changes, newest first: whether any record each change saved contains the text,
# in the revision that change wrote. `transaction.changes` lists the (key, revision) pairs each change saved and `data`
# holds every revision in full. The lookups are scalar subqueries so each is a single index probe per saved record: as
# joins, the planner may hash or scan `thing` or `data`. The page is materialized first so only its rows are searched.
_MATCH_PAGE_SQL = """
WITH page AS MATERIALIZED (
    SELECT id, created, changes FROM transaction
    WHERE (%(before)s::int IS NULL OR id < %(before)s) AND (%(kind)s::text IS NULL OR action = %(kind)s)
    ORDER BY id DESC
    LIMIT %(limit)s
)
SELECT page.id, page.created, EXISTS (
    SELECT 1 FROM jsonb_array_elements(page.changes::jsonb) AS change
    WHERE strpos(lower((
        SELECT data.data FROM data
        WHERE data.thing_id = (SELECT thing.id FROM thing WHERE thing.key = change->>'key')
        AND data.revision = (change->>'revision')::int
    )), %(text)s) > 0
) AS matched
FROM page
"""
# Per page, so one slow page fails fast and the walk can retry it smaller.
MATCH_PAGE_TIMEOUT = "20s"
MAX_PAGE_SIZE = 5000


class RecentChangesMatchPage(BaseModel):
    counts: dict[str, int]
    """Matching changes per ISO date (UTC), for the days this page reached; days without a match are left out."""
    checked: dict[str, int]
    """Changes this page checked per ISO date (UTC)."""
    scanned: int
    """How many changes this page checked."""
    next: int | None
    """Pass as `before` for the next, older page; None once there are no older changes."""
    oldest: str | None
    """When the oldest change on this page was made (ISO, UTC): the walk has covered everything since."""


async def match_page(text: str, kind: str | None, before: int | None, limit: int) -> RecentChangesMatchPage:
    async with connection() as conn:
        await conn.execute(f"SET LOCAL statement_timeout = '{MATCH_PAGE_TIMEOUT}'")
        cursor = await conn.execute(_MATCH_PAGE_SQL, {"text": text, "kind": kind, "before": before, "limit": limit})
        rows = await cursor.fetchall()
    counts: dict[str, int] = {}
    checked: dict[str, int] = {}
    for row in rows:
        day = row["created"].date().isoformat()
        checked[day] = checked.get(day, 0) + 1
        if row["matched"]:
            counts[day] = counts.get(day, 0) + 1
    return RecentChangesMatchPage(
        counts=counts,
        checked=checked,
        scanned=len(rows),
        next=min(row["id"] for row in rows) if len(rows) == limit else None,
        oldest=min(row["created"] for row in rows).isoformat() if rows else None,
    )


# Librarians only: each page reads the full record of every change it covers.
@router.get("/stats/recentchanges/matches.json", response_model=RecentChangesMatchPage)
async def recentchanges_matches(
    _: LibrarianDep,
    q: Annotated[str, Query(min_length=3, max_length=100, description="Text to look for, case-insensitively, in each edited record as that change saved it.")],
    kind: Annotated[str | None, Query(max_length=64, description="Change kind, e.g. add-book; all kinds if omitted.")] = None,
    before: Annotated[int | None, Query(gt=0, description="Only changes with an id below this: the previous page's `next`.")] = None,
    limit: Annotated[int, Query(gt=0, le=MAX_PAGE_SIZE, description="How many changes to check.")] = 200,
) -> RecentChangesMatchPage:
    """One page of a newest-first walk through the changes, counting those whose saved records contain `q`."""
    try:
        return await match_page(q.strip().lower(), kind or None, before, limit)
    except QueryCanceled:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=f"This page took longer than {MATCH_PAGE_TIMEOUT}; try a smaller one.")
