"""The signed-in reader's shelf and rating for a batch of works.

`<ol-shelf-button>` and `<ol-book-actions>` render whatever `shelf` and
`rating` they are handed, so a server-rendered page can set them directly.
Anything that renders books on the client — a carousel, a search result list —
needs to ask, and asking once for the whole batch keeps the public payload
cacheable and user-agnostic.
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BeforeValidator

from openlibrary.core.bookshelves import Bookshelves
from openlibrary.core.ratings import Ratings
from openlibrary.fastapi.auth import AuthenticatedUser, require_authenticated_user
from openlibrary.fastapi.models import parse_comma_separated_list
from openlibrary.utils import extract_numeric_id_from_olid

router = APIRouter(tags=["internal"], include_in_schema=os.getenv("LOCAL_DEV") is not None)

MAX_STATE_WORKS = 100


@router.get("/reading-state.json")
async def reading_state(
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    work_ids: Annotated[
        list[str],
        BeforeValidator(parse_comma_separated_list),
        Query(description="Comma-separated work OLIDs, e.g. OL1W,OL2W", max_length=MAX_STATE_WORKS),
    ],
) -> dict[str, dict[str, int]]:
    """`{"shelves": {"OL1W": 1}, "ratings": {"OL1W": 4}}` — only works with state are present."""
    numeric_ids = [int(extract_numeric_id_from_olid(olid)) for olid in work_ids if olid]
    if not numeric_ids:
        return {"shelves": {}, "ratings": {}}
    shelves = {f"OL{row.work_id}W": row.bookshelf_id for row in Bookshelves.get_users_read_status_of_works(user.username, numeric_ids)}
    ratings = {f"OL{work_id}W": rating for work_id, rating in Ratings.get_users_ratings_of_works(user.username, numeric_ids).items()}
    return {"shelves": shelves, "ratings": ratings}
