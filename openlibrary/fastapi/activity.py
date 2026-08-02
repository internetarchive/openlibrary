"""FastAPI endpoint backing the social activity feed.

Serves one JSON shape for every rendering of the feed -- the My Books section,
the standalone feed page, and the design gallery all read from here, so a card
looks the same wherever it appears and there is only one place to change what a
feed event means.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from openlibrary.core.activity import ActivityEvent, ActivityStream, ListEvent
from openlibrary.core.follows import PubSub
from openlibrary.core.models import User
from openlibrary.fastapi.auth import AuthenticatedUser, get_authenticated_user

router = APIRouter()

Scope = Literal["auto", "public", "following"]


class FeedWork(BaseModel):
    """The book a feed event is about."""

    key: str
    title: str
    author: str | None = None
    author_key: str | None = None
    cover_id: int | None = None
    first_publish_year: int | None = None
    ebook_access: str | None = None


class FeedList(BaseModel):
    """The list a feed event is about."""

    key: str
    name: str
    book_count: int
    cover_ids: list[int]


class FeedItem(BaseModel):
    type: str
    username: str
    patron_url: str
    avatar_url: str
    created: str
    label: str
    shelf_url: str | None = None
    rating: int | None = None
    work: FeedWork | None = None
    list: FeedList | None = None


class FeedResponse(BaseModel):
    scope: Literal["public", "following"]
    following: bool
    page: int
    activity: list[FeedItem]


def _first(values, prefix: str = "") -> str | None:
    """First entry of a Solr multi-value field, optionally path-prefixed."""
    if not values:
        return None
    return f"{prefix}{values[0]}"


def _serialise(event: ActivityEvent) -> FeedItem | None:
    """Turn one activity event into its wire shape, or None if unrenderable."""
    if event.created is None:
        return None

    work = None
    if event.work_id is not None:
        # An event whose work Solr has never heard of would render as a blank
        # card, so it is dropped rather than shown empty.
        if not event.work or not event.work.get("title"):
            return None
        work = FeedWork(
            key=event.work.get("key") or event.work_key or "",
            title=event.work["title"],
            author=_first(event.work.get("author_name")),
            author_key=_first(event.work.get("author_key"), prefix="/authors/"),
            cover_id=event.work.get("cover_i"),
            first_publish_year=event.work.get("first_publish_year"),
            ebook_access=event.work.get("ebook_access"),
        )

    feed_list = None
    if isinstance(event, ListEvent):
        feed_list = FeedList(
            key=event.list_key,
            name=event.name,
            book_count=event.book_count,
            cover_ids=event.cover_ids,
        )

    return FeedItem(
        type=event.type,
        username=event.username,
        patron_url=event.patron_url,
        avatar_url=_avatar_url(event.username),
        created=event.created.isoformat(),
        label=_label(event),
        shelf_url=event.shelf_url,
        rating=event.rating,
        work=work,
        list=feed_list,
    )


def _label(event: ActivityEvent) -> str:
    if event.type == "list_update":
        return "updated a list"
    if event.type == "rating":
        return "rated"
    return event.label


def _avatar_url(username: str) -> str:
    """Avatar for a patron, falling back to the local route if unresolvable."""
    try:
        return User.get_avatar_url(username)
    except Exception:  # noqa: BLE001 - an unlinked account still gets a card, just a default face
        return f"/people/{username}/avatar"


@router.get(
    "/api/internal/activity/feed.json",
    response_model=FeedResponse,
    description="Recent community or personalised book activity, for the social activity feed.",
)
async def activity_feed(
    user: Annotated[AuthenticatedUser | None, Depends(get_authenticated_user)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 12,
    page: Annotated[int, Query(ge=1)] = 1,
    scope: Annotated[Scope, Query()] = "auto",
) -> FeedResponse:
    viewer = user.username if user else None
    following = bool(viewer) and PubSub.is_following(viewer)

    events: list[ActivityEvent] = []
    resolved: Literal["public", "following"] = "public"

    if scope != "public" and following and viewer:
        events = ActivityStream.following_feed(viewer, limit=limit, page=page)
        resolved = "following"

    # Following someone quiet should not leave the patron staring at nothing --
    # fall back to the community feed rather than an empty page.
    if not events:
        events = ActivityStream.public_feed(viewer=viewer, limit=limit, page=page)
        resolved = "public"

    ActivityStream.attach_works(events)

    activity = [item for event in events if (item := _serialise(event))]
    return FeedResponse(scope=resolved, following=following, page=page, activity=activity)
