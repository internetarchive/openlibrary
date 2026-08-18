"""Endpoints backing the `<ol-books-display>` component.

- `GET /books-display.json` — the (cacheable, user-agnostic) book cards for a
  Solr query, paginated by offset.
- `GET /books-display/user-state.json` — the current user's shelf + rating for
  a batch of works, so the public payload above stays cacheable.
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BeforeValidator

from openlibrary import accounts
from openlibrary.core.bookshelves import Bookshelves
from openlibrary.core.ratings import Ratings
from openlibrary.fastapi.auth import AuthenticatedUser, require_authenticated_user
from openlibrary.fastapi.models import parse_comma_separated_list
from openlibrary.fastapi.services.books_display import BooksDisplayResponse, fetch_books_display
from openlibrary.utils import extract_numeric_id_from_olid

router = APIRouter(tags=["internal"], include_in_schema=os.getenv("LOCAL_DEV") is not None)

MAX_LIMIT = 50
MAX_STATE_WORKS = 100


@router.get("/books-display.json")
async def books_display(
    q: Annotated[str, Query(description="Solr work query")],
    sort: Annotated[str, Query()] = "new",
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    has_fulltext_only: Annotated[bool, Query()] = True,
    safe_mode: Annotated[bool, Query()] = True,
) -> BooksDisplayResponse:
    return await fetch_books_display(
        q=q,
        sort=sort,
        limit=limit,
        offset=offset,
        has_fulltext_only=has_fulltext_only,
        safe_mode=safe_mode,
        user=accounts.get_current_user(),
    )


@router.get("/books-display/user-state.json")
async def books_display_user_state(
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
