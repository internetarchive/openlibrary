"""Daily change counts behind the chart on /recentchanges and its per-kind pages."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from psycopg.errors import InvalidRegularExpression, QueryCanceled
from pydantic import BaseModel

from openlibrary.core import cache
from openlibrary.core.async_db import connection, fetch_all
from openlibrary.fastapi.auth import LibrarianDep  # noqa: TC001
from openlibrary.utils.async_utils import async_bridge
from openlibrary.utils.dateutil import HALF_HOUR_SECS

router = APIRouter()

MAX_DAYS = 365
# Hourly slots for longer ranges would be more bars than the chart can show usefully.
MAX_HOURLY_DAYS = 28

# Bot accounts are flagged in the account store; their edits are attributed to the matching /people/ thing.
_BOTS_CTE = """bots AS (
    SELECT thing.id FROM store
    JOIN store_index ON store_index.store_id = store.id
    JOIN thing ON thing.key = '/people/' || split_part(store.key, '/', 2)
    WHERE store_index.type = 'account' AND store_index.name = 'bot' AND store_index.value = 'true'
)"""

_DAILY_COUNTS_SQL = f"""
WITH {_BOTS_CTE}
SELECT
    date_trunc(%(unit)s, created) AS slot,
    COALESCE(author_id IN (SELECT id FROM bots), false) AS is_bot,
    COALESCE(action, 'edit') AS kind,
    count(*) AS n
FROM transaction
WHERE created >= %(since)s AND (%(kind)s::text IS NULL OR action = %(kind)s)
GROUP BY slot, is_bot, kind
"""


class RecentChangesCounts(BaseModel):
    dates: list[str]
    """One slot per day (ISO date) or hour (`YYYY-MM-DDTHH`), UTC, oldest first, ending with the one still being counted."""
    humans: list[int]
    bots: list[int]
    kinds: dict[str, list[int]]
    """Counts per change kind (infobase's `action`; `edit` where it has none)."""
    bot_kinds: dict[str, list[int]]
    """The part of `kinds` made by bots."""


def slot_label(slot: datetime, unit: str) -> str:
    """How a day or hour is keyed in the responses: `YYYY-MM-DD` or `YYYY-MM-DDTHH`, UTC."""
    return slot.strftime("%Y-%m-%dT%H" if unit == "hour" else "%Y-%m-%d")


async def change_counts(kind: str | None, days: int, unit: str) -> dict[str, Any]:
    now = datetime.now(UTC).replace(tzinfo=None)
    since = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    step = timedelta(hours=1) if unit == "hour" else timedelta(days=1)
    slots = []
    slot = since
    while slot <= now:
        slots.append(slot)
        slot += step
    rows = await fetch_all(_DAILY_COUNTS_SQL, {"since": since, "kind": kind, "unit": unit})
    index = {s: i for i, s in enumerate(slots)}
    size = len(slots)
    humans, bots = [0] * size, [0] * size
    kinds: dict[str, list[int]] = {}
    bot_kinds: dict[str, list[int]] = {}
    for row in rows:
        # A change stamped after `now` (clock skew between hosts) has no slot yet
        if (i := index.get(row["slot"])) is None:
            continue
        (bots if row["is_bot"] else humans)[i] += row["n"]
        kinds.setdefault(row["kind"], [0] * size)[i] += row["n"]
        bot_kinds.setdefault(row["kind"], [0] * size)[i] += row["n"] if row["is_bot"] else 0
    return {"dates": [slot_label(s, unit) for s in slots], "humans": humans, "bots": bots, "kinds": kinds, "bot_kinds": bot_kinds}


@cache.memoize(engine="memcache", key="recentchanges.change_counts_v4", expires=HALF_HOUR_SECS)
def _cached_change_counts(kind: str | None, days: int, unit: str) -> dict[str, Any]:
    return async_bridge.run(change_counts(kind, days, unit))


# Plain def: the memcache client is blocking, so the route runs in the threadpool.
@router.get("/stats/recentchanges.json", response_model=RecentChangesCounts)
def recentchanges_counts(
    kind: Annotated[str | None, Query(max_length=64, description="Change kind, e.g. add-book; all kinds if omitted.")] = None,
    days: Annotated[int, Query(gt=0, le=MAX_DAYS, description="How many days up to today.")] = 28,
    unit: Annotated[Literal["day", "hour"], Query(description=f"Count per day, or per hour for up to {MAX_HOURLY_DAYS} days.")] = "day",
) -> RecentChangesCounts:
    """Changes per day or hour, split into human and bot edits and by kind."""
    if unit == "hour" and days > MAX_HOURLY_DAYS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Hourly counts cover at most {MAX_HOURLY_DAYS} days.")
    return RecentChangesCounts(**_cached_change_counts(kind or None, days, unit))


# One page of a walk back through the changes, newest first: whether any record each change saved contains the text,
# in the revision that change wrote. `transaction.changes` lists the (key, revision) pairs each change saved and `data`
# holds every revision in full. The lookups are scalar subqueries so each is a single index probe per saved record: as
# joins, the planner may hash or scan `thing` or `data`. The page is materialized first so only its rows are searched.
_MATCH_PAGE_TEMPLATE = f"""
WITH {_BOTS_CTE}, page AS MATERIALIZED (
    SELECT id, created, changes FROM transaction
    WHERE (%(before)s::int IS NULL OR id < %(before)s) AND (%(kinds)s::text[] IS NULL OR action = ANY(%(kinds)s))
    AND (%(bot)s::boolean IS NULL OR COALESCE(author_id IN (SELECT id FROM bots), false) = %(bot)s)
    ORDER BY id DESC
    LIMIT %(limit)s
)
SELECT page.id, page.created, EXISTS (
    SELECT 1 FROM jsonb_array_elements(page.changes::jsonb) AS change
    WHERE __MATCH__
) AS matched
FROM page
"""
_SAVED_RECORD = """(
        SELECT data.data FROM data
        WHERE data.thing_id = (SELECT thing.id FROM thing WHERE thing.key = change->>'key')
        AND data.revision = (change->>'revision')::int
    )"""
# By (regex, match case). Case-insensitive substrings are lowercased in Python, so only the record needs lower().
_MATCH_PAGE_SQL = {
    (regex, match_case): _MATCH_PAGE_TEMPLATE.replace("__MATCH__", predicate.replace("__RECORD__", _SAVED_RECORD))
    for (regex, match_case), predicate in {
        (False, False): "strpos(lower(__RECORD__), %(text)s) > 0",
        (False, True): "strpos(__RECORD__, %(text)s) > 0",
        (True, False): "__RECORD__ ~* %(text)s",
        (True, True): "__RECORD__ ~ %(text)s",
    }.items()
}
# Per page, so one slow page fails fast and the walk can retry it smaller.
MATCH_PAGE_TIMEOUT = "20s"
MAX_PAGE_SIZE = 5000
MAX_KINDS = 30


class RecentChangesMatchPage(BaseModel):
    counts: dict[str, int]
    """Matching changes per hour (`YYYY-MM-DDTHH`, UTC), for the hours this page reached; hours without a match are left out."""
    checked: dict[str, int]
    """Changes this page checked per hour (`YYYY-MM-DDTHH`, UTC)."""
    matched: list[tuple[int, str]]
    """The matching changes' ids with their hour, newest first."""
    scanned: int
    """How many changes this page checked."""
    next: int | None
    """Pass as `before` for the next, older page; None once there are no older changes."""
    oldest: str | None
    """When the oldest change on this page was made (ISO, UTC): the walk has covered everything since."""


async def match_page(
    text: str, regex: bool, match_case: bool, kinds: list[str] | None, bot: bool | None, before: int | None, limit: int
) -> RecentChangesMatchPage:
    async with connection() as conn:
        await conn.execute(f"SET LOCAL statement_timeout = '{MATCH_PAGE_TIMEOUT}'")
        cursor = await conn.execute(_MATCH_PAGE_SQL[regex, match_case], {"text": text, "kinds": kinds, "bot": bot, "before": before, "limit": limit})
        rows = await cursor.fetchall()
    counts: dict[str, int] = {}
    checked: dict[str, int] = {}
    matched: list[tuple[int, str]] = []
    for row in sorted(rows, key=lambda row: row["id"], reverse=True):
        hour = slot_label(row["created"], "hour")
        checked[hour] = checked.get(hour, 0) + 1
        if row["matched"]:
            counts[hour] = counts.get(hour, 0) + 1
            matched.append((row["id"], hour))
    return RecentChangesMatchPage(
        counts=counts,
        checked=checked,
        matched=matched,
        scanned=len(rows),
        next=min(row["id"] for row in rows) if len(rows) == limit else None,
        oldest=min(row["created"] for row in rows).isoformat() if rows else None,
    )


# Librarians only: each page reads the full record of every change it covers.
@router.get("/stats/recentchanges/matches.json", response_model=RecentChangesMatchPage)
async def recentchanges_matches(
    _: LibrarianDep,
    q: Annotated[str, Query(min_length=3, max_length=100, description="Text to look for in each edited record, as that change saved it (its JSON).")],
    regex: Annotated[bool, Query(description="Treat `q` as a PostgreSQL regular expression.")] = False,
    case: Annotated[bool, Query(description="Match case.")] = False,
    kind: Annotated[list[str] | None, Query(max_length=MAX_KINDS, description="Change kinds, e.g. add-book; repeat for several, all kinds if omitted.")] = None,
    bot: Annotated[bool | None, Query(description="Only bots' changes, or only people's; both if omitted.")] = None,
    before: Annotated[int | None, Query(gt=0, description="Only changes with an id below this: the previous page's `next`.")] = None,
    limit: Annotated[int, Query(gt=0, le=MAX_PAGE_SIZE, description="How many changes to check.")] = 200,
) -> RecentChangesMatchPage:
    """One page of a newest-first walk through the changes, counting those whose saved records contain `q`."""
    try:
        text = q if regex else q.strip()
        return await match_page(text if case or regex else text.lower(), regex, case, kind or None, bot, before, limit)
    except InvalidRegularExpression as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error).splitlines()[0])
    except QueryCanceled:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=f"This page took longer than {MATCH_PAGE_TIMEOUT}; try a smaller one.")
