"""Infobase event hooks for Open Library.

Triggers and handles various events from Infobase. All the events are triggered using eventer.

List of events:

    * infobase.all: Triggered for any change in Infobase. The infobase event object is passed as argument.
    * infobase.edit: Triggered for edits. Changeset is passed as argument.
"""

import logging
import re

import eventer
import web

from infogami.infobase import config, server
from openlibrary.utils import olmemcache

logger = logging.getLogger("openlibrary.olbase")


def setup():
    setup_event_listener()


def setup_event_listener():
    logger.info("setting up infobase events for Open Library")

    ib = server._infobase

    # Convert infobase event into generic eventer event
    ib.add_event_listener(lambda event: eventer.trigger("infobase.all", event))


@eventer.bind("infobase.all")
def trigger_subevents(event):
    """Trigger infobase.edit event for edits."""
    if event.name in ['save', 'save_many']:
        changeset = event.data['changeset']

        author = changeset['author'] or changeset['ip']
        keys = [c['key'] for c in changeset['changes']]
        logger.info(
            "Edit by %s, changeset_id=%s, changes=%s", author, changeset["id"], keys
        )

        eventer.trigger("infobase.edit", changeset)


@eventer.bind("infobase.edit")
def invalidate_memcache(changeset):
    """Invalidate memcache entries effected by this change."""
    if memcache_client := get_memcache():
        keys = MemcacheInvalidater().find_keys(changeset)
        if keys:
            logger.info("invalidating %s", keys)
            memcache_client.delete_multi(keys)


class MemcacheInvalidater:
    """Class to find keys to invalidate from memcache on edit."""

    def find_keys(self, changeset):
        """Returns keys for the effected entries by this change."""
        methods = [
            self.find_data,
            self.find_lists,
            self.find_edition_counts,
        ]

        keys = set()
        for m in methods:
            keys.update(m(changeset))
        return list(keys)

    def find_data(self, changeset):
        """Returns the data entries effected by this change.

        The data entry stores the history, lists and edition_count of a page.
        """
        return ["d" + c['key'] for c in changeset['changes']]

    def find_lists(self, changeset):
        """Returns the list entries effected by this change.

        When a list is modified, the data of the user and the data of each
        seed are invalidated.
        """
        docs = changeset['docs'] + changeset['old_docs']
        rx = web.re_compile(r"(/people/[^/]*)?/lists/OL\d+L")
        for doc in docs:
            if match := doc and rx.match(doc['key']):
                if owner := match.group(1):
                    yield "d" + owner  # d/people/foo
                for seed in doc.get('seeds', []):
                    yield "d" + self.seed_to_key(seed)

    def find_edition_counts(self, changeset):
        """Returns the edition_count entries effected by this change."""
        docs = changeset['docs'] + changeset['old_docs']
        return {k for doc in docs for k in self.find_edition_counts_for_doc(doc)}

    def find_edition_counts_for_doc(self, doc):
        """Returns the memcache keys to be invalided for edition_counts effected by editing this doc."""
        if doc and doc['type']['key'] == '/type/edition':
            return ["d" + w['key'] for w in doc.get("works", [])]
        else:
            return []

    def seed_to_key(self, seed):
        """Converts seed to key.

        >>> invalidater = MemcacheInvalidater()
        >>> invalidater.seed_to_key({"key": "/books/OL1M"})
        '/books/OL1M'
        >>> invalidater.seed_to_key("subject:love")
        '/subjects/love'
        >>> invalidater.seed_to_key("place:san_francisco")
        '/subjects/place:san_francisco'
        """
        if isinstance(seed, dict):
            return seed['key']
        elif seed.startswith("subject:"):
            return "/subjects/" + seed[len("subject:") :]
        else:
            return "/subjects/" + seed


@web.memoize
def get_memcache():
    """Returns memcache client created from infobase configuration."""
    cache = config.get("cache", {})
    if cache.get("type") == "memcache":
        return olmemcache.Client(cache['servers'])


def extract_numeric_id_from_olid(olid: str) -> str | None:
    """Extract numeric ID from an OLID like '/works/OL123W' -> '123'."""
    if not olid:
        return None
    match = re.search(r'OL(\d+)[AWM]', olid)
    return match.group(1) if match else None


@eventer.bind("infobase.edit")
def sync_patron_data_for_work_merge(changeset):
    """Update reading logs, ratings, booknotes, etc. when works are merged.

    When works are merged, editions get their 'works' field updated to point
    to the new master work. However, patron data tables (bookshelves_books,
    ratings, etc.) still reference the old work IDs. This handler updates
    those tables to use the new master work ID.

    See: https://github.com/internetarchive/openlibrary/issues/11646
    """
    if changeset.get('action') != 'merge-works':
        return

    data = changeset.get('data', {})
    master_key = data.get('master')  # e.g., "/works/OL123W"
    duplicate_keys = data.get('duplicates', [])

    if not master_key or not duplicate_keys:
        return

    master_id = extract_numeric_id_from_olid(master_key)
    if not master_id:
        logger.warning(
            "sync_patron_data_for_work_merge: Could not extract ID from master key %s",
            master_key,
        )
        return

    # Import here to avoid circular imports
    from openlibrary.core.bestbook import Bestbook
    from openlibrary.core.booknotes import Booknotes
    from openlibrary.core.bookshelves import Bookshelves
    from openlibrary.core.bookshelves_events import BookshelvesEvents
    from openlibrary.core.observations import Observations
    from openlibrary.core.ratings import Ratings

    for dup_key in duplicate_keys:
        dup_id = extract_numeric_id_from_olid(dup_key)
        if not dup_id:
            logger.warning(
                "sync_patron_data_for_work_merge: Could not extract ID from duplicate key %s",
                dup_key,
            )
            continue

        logger.info(
            "sync_patron_data_for_work_merge: Updating patron data from work %s to %s",
            dup_id,
            master_id,
        )

        # Update all patron data tables
        Bookshelves.update_work_id(dup_id, master_id)
        Ratings.update_work_id(dup_id, master_id)
        Booknotes.update_work_id(dup_id, master_id)
        Observations.update_work_id(dup_id, master_id)
        Bestbook.update_work_id(dup_id, master_id)
        BookshelvesEvents.update_work_id(dup_id, master_id)

