"""
FastAPI endpoints for public_my_books_json (reading log).
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from openlibrary.fastapi.auth import (
    AuthenticatedUser,
    get_authenticated_user,
)
from openlibrary.fastapi.models import Pagination  # noqa: TC001
from openlibrary.plugins.upstream.mybooks import ReadingLog
from openlibrary.utils.request_context import site

router = APIRouter()


class WorkData(BaseModel):
    """Work data in reading log."""

    title: str | None
    key: str
    author_keys: list[str]
    author_names: list[str]
    first_publish_year: int | None
    lending_edition_s: str | None
    edition_key: list[str] | None
    cover_id: int | None
    cover_edition_key: str | None


class ReadingLogEntry(BaseModel):
    """Single reading log entry."""

    work: WorkData
    logged_edition: str | None
    logged_date: str | None


class ReadingLogResponse(BaseModel):
    """Response model for reading log."""

    page: int
    numFound: int
    reading_log_entries: list[ReadingLogEntry]


ReadingLogKey = Literal["want-to-read", "currently-reading", "already-read"]


@router.get("/people/{username}/books/{key}.json")
async def get_public_my_books_json(
    username: str,
    key: ReadingLogKey,
    logged_in_user: Annotated[AuthenticatedUser | None, Depends(get_authenticated_user)],
    pagination: Annotated[Pagination, Depends()],
    q: str = Query("", min_length=0, max_length=100),
    mode: str = Query("everything"),
) -> ReadingLogResponse:
    """Get public reading log for a user.

    Returns the user's reading log if:
    1. The user's readlog is public (preferences.public_readlog == 'yes')
    2. The requesting user is the same as the requested username

    Otherwise returns an error.
    """
    key = key.lower()  # type: ignore[assignment]

    if len(q) < 3:
        q = ""

    current_site = site.get()
    user_obj = current_site.get("/people/%s" % username)

    if not user_obj:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    is_public = user_obj.preferences().get("public_readlog", "no") == "yes"

    if not is_public and (not logged_in_user or logged_in_user.username != username):
        raise HTTPException(
            status_code=403,
            detail="This reading log is private",
        )

    fq = None
    if mode == "ebooks":
        from openlibrary.solr.solr import get_fulltext_min

        fq = [f"ebook_access:[{get_fulltext_min()} TO *]"]

    page = pagination.page or 1
    readlog = ReadingLog(user=user_obj)
    books = readlog.get_works(key, page, pagination.limit, q=q, fq=fq).docs

    records_json = [
        ReadingLogEntry(
            work=WorkData(
                title=w.get("title"),
                key=w.key,
                author_keys=["/authors/" + k for k in w.get("author_key", [])],
                author_names=w.get("author_name", []),
                first_publish_year=w.get("first_publish_year") or None,
                lending_edition_s=w.get("lending_edition_s") or None,
                edition_key=w.get("edition_key") or None,
                cover_id=w.get("cover_i") or None,
                cover_edition_key=w.get("cover_edition_key") or None,
            ),
            logged_edition=w.get("logged_edition") or None,
            logged_date=w.get("logged_date").strftime("%Y/%m/%d, %H:%M:%S") if w.get("logged_date") else None,
        )
        for w in books
    ]

    if page == 1 and len(records_json) < pagination.limit:
        num_found = len(records_json)
    else:
        num_found = readlog.count_shelf(key)

    return ReadingLogResponse(
        page=page,
        numFound=num_found,
        reading_log_entries=records_json,
    )
