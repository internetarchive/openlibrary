"""A unified activity stream over the things patrons publicly do with books.

Open Library records patron activity in several unrelated places: reading-log
shelvings and star ratings live in Postgres, lists live in Infogami. The social
feed needs one time-ordered stream across all of them, so this module normalises
each source into a common event shape and merges them.

Three card types come out of it, in the order they matter:

1. ``shelf_change`` -- a book put on Want to Read, Currently Reading or
   Already Read.
2. ``rating`` -- a book given stars. Its own card, not a decoration on the
   shelving, because rating is its own act.
3. ``list_add`` -- a book added to one of the patron's lists. The book is the
   subject; the list is context.

Hearting a list is an *action* offered on card three, not a card of its own.

Two feeds come out of it:

``public_feed``
    Everything happening across the library, restricted to patrons who have
    opted into a public reading log. This is what a patron who follows nobody
    sees -- there is real value in the community's activity before you follow
    anyone, so this is a browsable feed rather than a placeholder.

``following_feed``
    The same shape, restricted to the patrons the viewer follows. Following is
    consent, so this deliberately does *not* re-apply the public-reading-log
    filter.

Only the sources that actually exist today are covered here. Borrow events are
the one thing the feed cannot show: loans have no public source to read from and
are privacy-sensitive. That gap is left open rather than faked.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, cast

from openlibrary.core.bookshelves import Bookshelves
from openlibrary.core.follows import PubSub
from openlibrary.core.ratings import Ratings
from openlibrary.utils.request_context import site

logger = logging.getLogger("openlibrary.activity")

EventType = Literal["shelf_change", "rating", "list_add"]

# Phrasing is deliberately third-person and past-tense so it reads correctly
# after a username: "ada_reads added to Want to Read".
SHELF_LABELS: dict[int, str] = {
    1: "added to Want to Read",
    2: "is Currently Reading",
    3: "finished reading",
    4: "stopped reading",
}

SHELF_SLUGS: dict[int, str] = {
    1: "want-to-read",
    2: "currently-reading",
    3: "already-read",
    4: "stopped-reading",
}

FEED_SHELF_IDS = [1, 2, 3]


def shelf_label(shelf_id: int) -> str:
    """Human phrasing for a bookshelf id, safe for ids we do not recognise."""
    return SHELF_LABELS.get(shelf_id, "logged")


def _work_key(work_id: int | str) -> str:
    return f"/works/OL{work_id}W"


@dataclass(kw_only=True)
class ActivityEvent:
    """One thing a patron did, normalised across every source."""

    type: EventType
    username: str
    # Rows can arrive without a usable timestamp; undated events are dropped
    # during assembly rather than crashing the feed.
    created: datetime | None = None

    # Work-shaped events (shelvings, ratings) carry these; list events do not.
    work_key: str | None = None
    work_id: int | None = None
    shelf_id: int | None = None
    rating: int | None = None

    # Populated later, from Solr, by `attach_works`.
    work: dict[str, Any] | None = None

    @property
    def patron_url(self) -> str:
        return f"/people/{self.username}"

    @property
    def label(self) -> str:
        return shelf_label(self.shelf_id) if self.shelf_id else ""

    @property
    def shelf_url(self) -> str | None:
        if not self.shelf_id or self.shelf_id not in SHELF_SLUGS:
            return None
        return f"/people/{self.username}/books/{SHELF_SLUGS[self.shelf_id]}"

    @property
    def dedupe_key(self) -> tuple:
        """Identifies the same underlying act across sources."""
        return (self.username, self.work_id)


@dataclass(kw_only=True)
class ShelfEvent(ActivityEvent):
    type: EventType = "shelf_change"

    @classmethod
    def from_row(cls, row: dict) -> ShelfEvent:
        work_id = row["work_id"]
        return cls(
            type="shelf_change",
            username=row["username"],
            created=row.get("created") or row.get("updated"),
            work_id=work_id,
            work_key=_work_key(work_id),
            shelf_id=row.get("bookshelf_id"),
        )


@dataclass(kw_only=True)
class RatingEvent(ActivityEvent):
    type: EventType = "rating"

    @classmethod
    def from_row(cls, row: dict) -> RatingEvent | None:
        # A row can exist with rating 0 meaning "rating cleared" -- not an event.
        rating = row.get("rating")
        if not rating:
            return None
        work_id = row["work_id"]
        return cls(
            type="rating",
            username=row["username"],
            created=row.get("created") or row.get("updated"),
            work_id=work_id,
            work_key=_work_key(work_id),
            rating=rating,
        )


@dataclass(kw_only=True)
class ListAddEvent(ActivityEvent):
    """A book added to a patron's list.

    The book is the subject -- it carries `work_id` like the other two card
    types, so it enriches from Solr the same way and offers the same
    add-to-reading-log action. The list is context, and supplies the extra
    "heart this list" action.
    """

    type: EventType = "list_add"
    list_key: str = ""
    name: str = ""
    book_count: int = 0
    cover_ids: list[int] = field(default_factory=list)
    like_count: int = 0

    @property
    def list_url(self) -> str:
        return self.list_key


class ActivityStream:
    """Builds the public and following feeds."""

    @classmethod
    def public_feed(cls, viewer: str | None = None, limit: int = 25, page: int = 1) -> list[ActivityEvent]:
        """Recent activity from across the library, public reading logs only."""
        # Over-fetch: filtering private patrons and the viewer's own rows both
        # thin the result, and a short feed is worse than a slightly slower one.
        fetch = limit * 4

        shelf_rows = Bookshelves.get_recently_logged_books(shelf_ids=FEED_SHELF_IDS, limit=fetch, page=page)
        rating_rows = Ratings.get_recent_ratings(limit=fetch, page=page)
        list_events = cls._recent_list_adds(limit=limit)

        candidates = [r["username"] for r in shelf_rows] + [r["username"] for r in rating_rows] + [e.username for e in list_events]
        public = cls._public_usernames(candidates)

        def visible(username: str) -> bool:
            return username in public and username != viewer

        events = cls._build_events(
            shelf_rows=[r for r in shelf_rows if visible(r["username"])],
            rating_rows=[r for r in rating_rows if visible(r["username"])],
            list_events=[e for e in list_events if visible(e.username)],
        )
        return events[:limit]

    @classmethod
    def following_feed(cls, viewer: str, limit: int = 25, page: int = 1) -> list[ActivityEvent]:
        """Recent activity from the patrons the viewer follows."""
        following = PubSub.get_following(viewer, exclude_disabled=True)
        usernames = [f["publisher"] for f in following]
        if not usernames:
            return []

        fetch = limit * 2
        shelf_rows = cls._shelf_rows_for(usernames, limit=fetch, page=page)
        rating_rows = Ratings.get_recent_ratings(usernames=usernames, limit=fetch, page=page)
        list_events = cls._recent_list_adds(limit=limit, usernames=usernames)

        followed = set(usernames)
        events = cls._build_events(
            shelf_rows=[r for r in shelf_rows if r["username"] in followed],
            rating_rows=[r for r in rating_rows if r["username"] in followed],
            list_events=[e for e in list_events if e.username in followed],
        )
        return events[:limit]

    @classmethod
    def popular_feed(cls, viewer: str | None = None, limit: int = 25, page: int = 1) -> list[ActivityEvent]:
        """The latest single event from each of the most-followed readers.

        One card per patron rather than a stream, ordered by how many people
        follow them -- a "who is worth following" view rather than a timeline.
        """
        ranked = [row["publisher"] for row in PubSub.most_followed(limit=limit * 2)]
        usernames = [name for name in ranked if name != viewer]
        if not usernames:
            return []

        fetch = limit * 4
        shelf_rows = cls._shelf_rows_for(usernames, limit=fetch, page=page)
        rating_rows = Ratings.get_recent_ratings(usernames=usernames, limit=fetch, page=page)
        list_events = cls._recent_list_adds(limit=fetch, usernames=usernames)

        allowed = set(usernames)
        events = cls._build_events(
            shelf_rows=[r for r in shelf_rows if r["username"] in allowed],
            rating_rows=[r for r in rating_rows if r["username"] in allowed],
            list_events=[e for e in list_events if e.username in allowed],
        )

        newest: dict[str, ActivityEvent] = {}
        for event in events:  # already newest-first
            newest.setdefault(event.username, event)

        rank = {name: i for i, name in enumerate(usernames)}
        return sorted(newest.values(), key=lambda e: rank[e.username])[:limit]

    # -- assembly ---------------------------------------------------------

    @classmethod
    def _build_events(cls, shelf_rows: list, rating_rows: list, list_events: list) -> list[ActivityEvent]:
        """Normalise every source into events and sort newest first.

        Shelving and rating are separate cards even for the same book by the
        same patron -- they are two of the three card types, and folding one
        into the other hid an event the feed is meant to surface.
        """
        events: list[ActivityEvent] = [ShelfEvent.from_row(r) for r in shelf_rows]
        events.extend(e for row in rating_rows if (e := RatingEvent.from_row(row)))
        events.extend(list_events)
        events = [e for e in events if e.created]
        events.sort(key=lambda e: cast(datetime, e.created), reverse=True)
        return events

    @classmethod
    def _shelf_rows_for(cls, usernames: list[str], limit: int, page: int = 1) -> list:
        """Recent reading-log rows for a specific set of patrons."""
        from openlibrary.core import db

        oldb = db.get_db()
        offset = limit * (max(page, 1) - 1)
        query = "SELECT * FROM bookshelves_books WHERE username IN $usernames AND bookshelf_id IN $shelf_ids ORDER BY created DESC LIMIT $limit OFFSET $offset"
        return list(
            oldb.query(
                query,
                vars={"usernames": usernames, "shelf_ids": FEED_SHELF_IDS, "limit": limit, "offset": offset},
            )
        )

    @classmethod
    def _public_usernames(cls, usernames: list[str]) -> set[str]:
        """Subset of the given patrons whose reading log is public.

        Reads the preference store directly, one key per patron, rather than
        unmarshalling a full account model each time.
        """
        public: set[str] = set()
        store = site.get().store
        for username in set(usernames):
            try:
                prefs = store.get(f"/people/{username}/preferences") or {}
            except Exception:  # noqa: BLE001 - a single unreadable patron must not fail the feed
                logger.warning("could not read preferences for %s", username, exc_info=True)
                continue
            if prefs.get("public_readlog") == "yes":
                public.add(username)
        return public

    @classmethod
    def _recent_list_adds(cls, limit: int = 10, usernames: list[str] | None = None) -> list[ListAddEvent]:
        """Recently touched patron lists, as "added a book to a list" events.

        Lists are Infogami things rather than Postgres rows, so this is a
        `things` query rather than part of the union above, and there is no
        per-book event to read. `List.add_seed` appends, though, so the last
        work in `seeds` is the one most recently added -- which is enough to
        name the book without diffing revisions.

        That approximation is the reason a computed `activity_feed` table is
        the right long-term home for this: a worker can record the real event
        when it happens instead of inferring it afterwards.
        """
        query: dict[str, Any] = {
            "type": "/type/list",
            "sort": "-last_modified",
            "limit": limit,
        }
        try:
            keys = site.get().things(query)
        except Exception:  # noqa: BLE001 - lists are a bonus source; the feed still works without them
            logger.warning("could not query recent lists", exc_info=True)
            return []

        events: list[ListAddEvent] = []
        for key in keys:
            owner = cls._list_owner(key)
            if not owner or (usernames is not None and owner not in usernames):
                continue
            doc = site.get().get(key)
            if not doc:
                continue
            work_id = cls._newest_work_seed(doc.seeds or [])
            if work_id is None:
                # A list of subjects or authors has no book to offer.
                continue
            showcase = cls._list_showcase(doc)
            events.append(
                ListAddEvent(
                    username=owner,
                    created=cls._as_datetime(doc.last_modified),
                    work_id=work_id,
                    work_key=_work_key(work_id),
                    list_key=key,
                    name=showcase["title"],
                    book_count=showcase["count"],
                    cover_ids=showcase["cover_ids"],
                    like_count=cls._like_count(key),
                )
            )
        return events

    @staticmethod
    def _newest_work_seed(seeds) -> int | None:
        """Numeric work id of the most recently added book seed, if any."""
        for seed in reversed(list(seeds)):
            key = getattr(seed, "key", None) or (seed.get("key") if isinstance(seed, dict) else None)
            if isinstance(key, str) and key.startswith("/works/OL") and key.endswith("W"):
                digits = key.removeprefix("/works/OL").removesuffix("W")
                if digits.isdigit():
                    return int(digits)
        return None

    @staticmethod
    def _like_count(key: str) -> int:
        from openlibrary.core.likes import Likes

        try:
            return Likes.get_count(key).get("likes", 0)
        except Exception:  # noqa: BLE001 - a heart count is decoration, not the card
            logger.warning("could not count likes for %s", key, exc_info=True)
            return 0

    @staticmethod
    def _list_owner(key: str) -> str | None:
        """`/people/ada/lists/OL1L` -> `ada`. Non-patron lists have no owner."""
        parts = key.split("/")
        if len(parts) >= 3 and parts[1] == "people":
            return parts[2]
        return None

    @staticmethod
    def _list_showcase(doc) -> dict[str, Any]:
        """Title, size, and up to three cover ids for a list card."""
        covers: list[int] = []
        count = 0
        try:
            cached = doc.get_patron_showcase()
            count = cached.get("count", 0)
            for url in cached.get("covers") or []:
                # `get_patron_showcase` hands back cover URLs; the feed wants
                # ids so the client can size the image itself.
                if url and (cover_id := ActivityStream._cover_id_from_url(url)):
                    covers.append(cover_id)
        except Exception:  # noqa: BLE001 - a malformed list renders without covers rather than 500ing
            logger.warning("could not build showcase for %s", doc.key, exc_info=True)
        return {"title": doc.name or "", "count": count, "cover_ids": covers[:3]}

    @staticmethod
    def _cover_id_from_url(url: str) -> int | None:
        """Pull the numeric id out of a `.../b/id/12345-S.jpg` cover URL."""
        segment = url.rsplit("/", 1)[-1]
        digits = segment.split("-", 1)[0]
        return int(digits) if digits.isdigit() else None

    @staticmethod
    def _as_datetime(value) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    @staticmethod
    def balance(events: list[ActivityEvent], limit: int) -> list[ActivityEvent]:
        """Trim to `limit` while keeping every card type represented.

        Strict newest-first can return a page of one type, which is fine for a
        real feed and useless for comparing card designs. Round-robins across
        types, then restores time order within the sample.
        """
        if len(events) <= limit:
            return events

        buckets: dict[str, list[ActivityEvent]] = {}
        for event in events:
            buckets.setdefault(event.type, []).append(event)

        picked: list[ActivityEvent] = []
        while len(picked) < limit:
            took = False
            for bucket in buckets.values():
                if not bucket:
                    continue
                picked.append(bucket.pop(0))
                took = True
                if len(picked) == limit:
                    break
            if not took:
                break

        picked.sort(key=lambda e: cast(datetime, e.created), reverse=True)
        return picked

    # -- enrichment -------------------------------------------------------

    @classmethod
    def attach_works(cls, events: list[ActivityEvent]) -> None:
        """Fill in each event's Solr work record, in place.

        Covers were rendered from guessed work-OLID URLs in an earlier attempt at
        this feature and came out wrong; the cover id has to come off the Solr
        record, which is what this fetches.
        """
        work_events = [e for e in events if e.work_id is not None]
        if not work_events:
            return
        items: list[dict[str, Any]] = [{"work_id": e.work_id} for e in work_events]
        Bookshelves.add_solr_works(items, fields=["key", "title", "author_name", "author_key", "cover_i", "first_publish_year", "ebook_access"])
        for event, item in zip(work_events, items, strict=True):
            event.work = item.get("work")
