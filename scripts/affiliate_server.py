#!/usr/bin/env python
"""Run affiliate server.

Usage:

start affiliate-server using dev webserver:

    ./scripts/affiliate_server.py openlibrary.yml 31337

start affiliate-server as fastcgi:

    ./scripts/affiliate_server.py openlibrary.yml fastcgi 31337

start affiliate-server using gunicorn webserver:

    ./scripts/affiliate_server.py openlibrary.yml --gunicorn -b 0.0.0.0:31337


Testing Amazon API:
  ol-home0% `docker exec -it openlibrary-affiliate-server-1 bash`
  openlibrary@ol-home0:/openlibrary$ `python`

```
import web
import infogami
from openlibrary.config import load_config
load_config('/olsystem/etc/openlibrary.yml')
infogami._setup()
from infogami import config;
from openlibrary.core.vendors import AmazonAPI
args=[config.amazon_api.get('key'), config.amazon_api.get('secret'),config.amazon_api.get('id')]
web.amazon_api = AmazonAPI(*args, throttling=0.9, proxy_url=config.get('http_proxy'))
products = web.amazon_api.get_products(["195302114X", "0312368615"], serialize=True)
```
"""
import itertools
import json
import logging
import os
import queue
import sys
import threading
import time
from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Final

import _init_path  # noqa: F401  Imported for its side effect of setting PYTHONPATH
import requests
import web

import infogami
from infogami import config
from openlibrary.config import load_config as openlibrary_load_config
from openlibrary.core import cache, stats
from openlibrary.core.imports import Batch, ImportItem
from openlibrary.core.vendors import AmazonAPI, clean_amazon_metadata_for_load
from openlibrary.plugins.upstream.utils import setup_requests
from openlibrary.utils.dateutil import WEEK_SECS
from openlibrary.utils.isbn import (
    isbn_10_to_isbn_13,
    normalize_identifier,
)

logger = logging.getLogger("affiliate-server")

# fmt: off
urls = (
    '/isbn/([bB]?[0-9a-zA-Z-]+)', 'Submit',
    '/status', 'Status',
    '/clear', 'Clear',
)
# fmt: on

API_MAX_ITEMS_PER_CALL = 10
API_MAX_WAIT_SECONDS = 0.9
# TODO: make a map for Google Books.
AZ_OL_MAP = {
    'cover': 'covers',
    'title': 'title',
    'authors': 'authors',
    'publishers': 'publishers',
    'publish_date': 'publish_date',
    'number_of_pages': 'number_of_pages',
}
RETRIES: Final = 5

batch: Batch | None = None

web.amazon_queue = (
    queue.PriorityQueue()
)  # a thread-safe multi-producer, multi-consumer queue
web.amazon_lookup_thread = None


class Priority(Enum):
    """
    Priority for the `PrioritizedIdentifier` class.

    `queue.PriorityQueue` has a lowest-value-is-highest-priority system, but
    setting `PrioritizedIdentifier.priority` to 0 can make it look as if priority is
    disabled. Using an `Enum` can help with that.
    """

    HIGH = 0
    LOW = 1

    def __lt__(self, other):
        if isinstance(other, Priority):
            return self.value < other.value
        return NotImplemented


@dataclass(order=True, slots=True)
class PrioritizedIdentifier:
    """
    Represent an identifiers's priority in the queue. Sorting is based on the `priority`
    attribute, then the `timestamp` to solve tie breaks within a specific priority,
    with priority going to whatever `min([items])` would return.
    For more, see https://docs.python.org/3/library/queue.html#queue.PriorityQueue.

    Therefore, priority 0, which is equivalent to `Priority.HIGH`, is the highest
    priority.

    This exists so certain identifiers can go to the front of the queue for faster
    processing as their look-ups are time sensitive and should return look up data
    to the caller (e.g. interactive API usage through `/isbn`).
    """

    identifier: str = field(compare=False)
    """identifier is an ISBN 13 or B* ASIN."""
    stage_import: bool = True
    """Whether to stage the item for import."""
    priority: Priority = field(default=Priority.LOW)
    timestamp: datetime = field(default_factory=datetime.now)

    def __hash__(self):
        """Only consider the `identifier` attribute when hashing (e.g. for `set` uniqueness)."""
        return hash(self.identifier)

    def __eq__(self, other):
        """Two instances of PrioritizedIdentifier are equal if their `identifier` attribute is equal."""
        if isinstance(other, PrioritizedIdentifier):
            return self.identifier == other.identifier
        return False

    def to_dict(self):
        """
        Convert the PrioritizedIdentifier object to a dictionary representation suitable
        for JSON serialization.
        """
        return {
            "isbn": self.identifier,
            "priority": self.priority.name,
            "stage_import": self.stage_import,
            "timestamp": self.timestamp.isoformat(),
        }


class BaseLookupWorker(threading.Thread):
    """
    A base class for creating API look up workers on their own threads.
    """

    def __init__(
        self,
        queue: queue.PriorityQueue,
        process_item: Callable,
        stats_client: stats.StatsClient,
        logger: logging.Logger,
        name: str,
    ) -> None:
        self.queue = queue
        self.process_item = process_item
        self.stats_client = stats_client
        self.logger = logger
        self.name = name

    def run(self):
        while True:
            try:
                item = self.queue.get(timeout=API_MAX_WAIT_SECONDS)
                self.logger.info(f"{self.name} lookup: processing item {item}")
                self.process_item(item)
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.exception(f"{self.name} Lookup Thread died: {e}")
                self.stats_client.incr(f"ol.affiliate.{self.name}.lookup_thread_died")


class AmazonLookupWorker(BaseLookupWorker):
    """
    A look up worker for the Amazon Products API.

    A separate thread of execution that uses the time up to API_MAX_WAIT_SECONDS to
    create a list of isbn_10s that is not larger than API_MAX_ITEMS_PER_CALL and then
    passes them to process_amazon_batch()
    """

    def run(self):
        while True:
            start_time = time.time()
            asins: set[PrioritizedIdentifier] = set()  # no duplicates in the batch
            while len(asins) < API_MAX_ITEMS_PER_CALL and self._seconds_remaining(
                start_time
            ):
                try:  # queue.get() will block (sleep) until successful or it times out
                    asins.add(
                        self.queue.get(timeout=self._seconds_remaining(start_time))
                    )
                except queue.Empty:
                    pass

            self.logger.info(f"Before amazon_lookup(): {len(asins)} items")
            if asins:
                time.sleep(seconds_remaining(start_time))
                try:
                    process_amazon_batch(asins)
                    self.logger.info(f"After amazon_lookup(): {len(asins)} items")
                except Exception:
                    self.logger.exception("Amazon Lookup Thread died")
                    self.stats_client.incr("ol.affiliate.amazon.lookup_thread_died")

    def _seconds_remaining(self, start_time: float) -> float:
        return max(API_MAX_WAIT_SECONDS - (time.time() - start_time), 0)


def fetch_google_book(isbn: str) -> dict | None:
    """
    Get Google Books metadata, if it exists.
    """
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    headers = {"User-Agent": "Open Library BookWorm/1.0"}
    try:
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            return r.json()

    except Exception as e:
        logger.exception(f"Error processing ISBN {isbn} on Google Books: {e!s}")
        stats.increment("ol.affiliate.google.total_fetch_exceptions")
        return None

    return None


# TODO: See AZ_OL_MAP and do something similar here.
def process_google_book(google_book_data: dict[str, Any]) -> dict[str, Any] | None:
    """
    Returns a dict-edition record suitable for import via /api/import

    Processing https://www.googleapis.com/books/v1/volumes?q=isbn:9785699350131:
    {'isbn_10': ['5699350136'],
     'isbn_13': ['9785699350131'],
     'title': 'Бал моей мечты',
     'subtitle': '[для сред. шк. возраста]',
     'authors': [{'name': 'Светлана Лубенец'}],
     'source_records': ['google_books:9785699350131'],
     'publishers': [],
     'publish_date': '2009',
     'number_of_pages': 153}
    """
    result = {}
    isbn_10 = []
    isbn_13 = []

    if not (data := google_book_data.get("items", [])):
        return None

    if len(data) != 1:
        logger.warning("Google Books had more than one result for an ISBN.")
        return None

    # Permanent URL: https://www.googleapis.com/books/v1/volumes/{id}
    # google_books_identifier = data[0].get("id")
    if not (book := data[0].get("volumeInfo", {})):
        return None

    # Extract ISBNs, if any.
    for identifier in book.get("industryIdentifiers", []):
        if identifier.get("type") == "ISBN_10":
            isbn_10.append(identifier.get("identifier"))
        elif identifier.get("type") == "ISBN_13":
            isbn_13.append(identifier.get("identifier"))

    result["isbn_10"] = isbn_10 if isbn_10 else []
    result["isbn_13"] = isbn_13 if isbn_13 else []

    result["title"] = book.get("title", "")
    result["subtitle"] = book.get("subtitle")
    result["authors"] = (
        [{"name": author} for author in book.get("authors", [])]
        if book.get("authors")
        else []
    )
    # result["identifiers"] = {
    #     "google": [isbn_13]
    # }  # Assuming so far is there is always an ISBN 13.
    google_books_identifier = isbn_13[0] if isbn_13 else isbn_10[0]
    result["source_records"] = [f"google_books:{google_books_identifier}"]
    # has publisher: https://www.googleapis.com/books/v1/volumes/YJ1uQwAACAAJ
    # does not have publisher: https://www.googleapis.com/books/v1/volumes?q=isbn:9785699350131
    result["publishers"] = [book.get("publisher")] if book.get("publisher") else []
    result["publish_date"] = book.get("publishedDate", "")
    # Language needs converting. 2 character code -> 3 character.
    # result["languages"] = [book.get("language")] if book.get("language") else []
    result["number_of_pages"] = book.get("pageCount", None)
    result["description"] = book.get("description", None)

    return result


def stage_from_google_books(isbn: str) -> bool:
    """
    Stage `isbn` from the Google Books API. Can be ISBN 10 or 13.

    See https://developers.google.com/books.
    """
    if google_book_data := fetch_google_book(isbn):
        if google_book := process_google_book(google_book_data=google_book_data):
            get_current_batch("google").add_items(
                [
                    {
                        'ia_id': google_book['source_records'][0],
                        'status': 'staged',
                        'data': google_book,
                    }
                ]
            )

            stats.increment("ol.affiliate.google.total_items_fetched")
            return True

        stats.increment("ol.affiliate.google.total_items_not_found")
        return False

    return False


def get_current_batch(name: str) -> Batch:
    """
    At startup, get the `name` (e.g. amz) openlibrary.core.imports.Batch() for global use.
    """
    global batch
    if not batch:
        batch = Batch.find(name) or Batch.new(name)
    assert batch
    return batch


def get_isbns_from_book(book: dict) -> list[str]:  # Singular: book
    return [str(isbn) for isbn in book.get('isbn_10', []) + book.get('isbn_13', [])]


def get_isbns_from_books(books: list[dict]) -> list[str]:  # Plural: books
    return sorted(set(itertools.chain(*[get_isbns_from_book(book) for book in books])))


def is_book_needed(book: dict, edition: dict) -> list[str]:
    """
    Should an OL edition's metadata be updated with Amazon book data?

    :param book: dict from openlibrary.core.vendors.clean_amazon_metadata_for_load()
    :param edition: dict from web.ctx.site.get_many(edition_ids)
    """
    needed_book_fields = []  # book fields that should be copied to the edition
    for book_field, edition_field in AZ_OL_MAP.items():
        if book.get(book_field) and not edition.get(edition_field):
            needed_book_fields.append(book_field)

    if needed_book_fields == ["authors"]:  # noqa: SIM102
        if work_key := edition.get("works") and edition["work"][0].get("key"):
            work = web.ctx.site.get(work_key)
            if work.get("authors"):
                needed_book_fields = []

    if needed_book_fields:  # Log book fields that should to be copied to the edition
        fields = ", ".join(needed_book_fields)
        logger.debug(f"{edition.get('key') or 'New Edition'} needs {fields}")
    return needed_book_fields


def get_editions_for_books(books: list[dict]) -> list[dict]:
    """
    Get the OL editions for a list of ISBNs.

    :param isbns: list of book dicts
    :return: list of OL editions dicts
    """
    isbns = get_isbns_from_books(books)
    unique_edition_ids = set(
        web.ctx.site.things({'type': '/type/edition', 'isbn_': isbns})
    )
    return web.ctx.site.get_many(list(unique_edition_ids))


def get_pending_books(books):
    pending_books = []
    editions = get_editions_for_books(books)  # Make expensive call just once
    # For each amz book, check that we need its data
    for book in books:
        ed = next(
            (
                ed
                for ed in editions
                if set(book.get('isbn_13')).intersection(set(ed.isbn_13))
                or set(book.get('isbn_10')).intersection(set(ed.isbn_10))
            ),
            {},
        )

        if is_book_needed(book, ed):
            pending_books.append(book)
    return pending_books


def make_cache_key(product: dict[str, Any]) -> str:
    """
    Takes a `product` returned from `vendor.get_products()` and returns a cache key to
    identify the product. For a given product, the cache key will be either (1) its
    ISBN 13, or (2) it's non-ISBN 10 ASIN (i.e. one that starts with `B`).
    """
    if (isbn_13s := product.get("isbn_13")) and len(isbn_13s):
        return isbn_13s[0]

    if product.get("isbn_10") and (
        cache_key := isbn_10_to_isbn_13(product.get("isbn_10", [])[0])
    ):
        return cache_key

    if (source_records := product.get("source_records")) and (
        amazon_record := next(
            (record for record in source_records if record.startswith("amazon:")), ""
        )
    ):
        return amazon_record.split(":")[1]

    return ""


def process_amazon_batch(asins: Collection[PrioritizedIdentifier]) -> None:
    """
    Call the Amazon API to get the products for a list of isbn_10s/ASINs and store
    each product in memcache using amazon_product_{isbn_13 or b_asin} as the cache key.
    """
    logger.info(f"process_amazon_batch(): {len(asins)} items")
    try:
        identifiers = [
            prioritized_identifier.identifier for prioritized_identifier in asins
        ]
        products = web.amazon_api.get_products(identifiers, serialize=True)
        # stats_ol_affiliate_amazon_imports - Open Library - Dashboards - Grafana
        # http://graphite.us.archive.org Metrics.stats.ol...
        stats.increment(
            "ol.affiliate.amazon.total_items_fetched",
            n=len(products),
        )
    except Exception:
        logger.exception(f"amazon_api.get_products({asins}, serialize=True)")
        return

    for product in products:
        cache_key = make_cache_key(product)  # isbn_13 or non-ISBN-10 ASIN.
        cache.memcache_cache.set(  # Add each product to memcache
            f'amazon_product_{cache_key}', product, expires=WEEK_SECS
        )

    # Only proceed if config finds infobase db creds
    if not config.infobase.get('db_parameters'):  # type: ignore[attr-defined]
        logger.debug("DB parameters missing from affiliate-server infobase")
        return

    # Skip staging no_import_identifiers for for import by checking AMZ source record.
    no_import_identifiers = {
        identifier.identifier for identifier in asins if not identifier.stage_import
    }

    books = [
        clean_amazon_metadata_for_load(product)
        for product in products
        if product.get("source_records")[0].split(":")[1] not in no_import_identifiers
    ]

    if books:
        stats.increment(
            "ol.affiliate.amazon.total_items_batched_for_import",
            n=len(books),
        )
        get_current_batch(name="amz").add_items(
            [
                {'ia_id': b['source_records'][0], 'status': 'staged', 'data': b}
                for b in books
            ]
        )


def seconds_remaining(start_time: float) -> float:
    return max(API_MAX_WAIT_SECONDS - (time.time() - start_time), 0)


def amazon_lookup(site, stats_client, logger) -> None:
    """
    A separate thread of execution that uses the time up to API_MAX_WAIT_SECONDS to
    create a list of isbn_10s that is not larger than API_MAX_ITEMS_PER_CALL and then
    passes them to process_amazon_batch()
    """
    stats.client = stats_client
    web.ctx.site = site

    while True:
        start_time = time.time()
        asins: set[PrioritizedIdentifier] = set()  # no duplicates in the batch
        while len(asins) < API_MAX_ITEMS_PER_CALL and seconds_remaining(start_time):
            try:  # queue.get() will block (sleep) until successful or it times out
                asins.add(web.amazon_queue.get(timeout=seconds_remaining(start_time)))
            except queue.Empty:
                pass

        logger.info(f"Before amazon_lookup(): {len(asins)} items")
        if asins:
            time.sleep(seconds_remaining(start_time))
            try:
                process_amazon_batch(asins)
                logger.info(f"After amazon_lookup(): {len(asins)} items")
            except Exception:
                logger.exception("Amazon Lookup Thread died")
                stats_client.incr("ol.affiliate.amazon.lookup_thread_died")


def make_amazon_lookup_thread() -> threading.Thread:
    """Called from start_server() and assigned to web.amazon_lookup_thread."""
    thread = threading.Thread(
        target=amazon_lookup,
        args=(web.ctx.site, stats.client, logger),
        daemon=True,
    )
    thread.start()
    return thread


class Status:
    def GET(self) -> str:
        return json.dumps(
            {
                "thread_is_alive": bool(
                    web.amazon_lookup_thread and web.amazon_lookup_thread.is_alive()
                ),
                "queue_size": web.amazon_queue.qsize(),
                "queue": [isbn.to_dict() for isbn in web.amazon_queue.queue],
            }
        )


class Clear:
    """Clear web.amazon_queue and return the queue size before it was cleared."""

    def GET(self) -> str:
        qsize = web.amazon_queue.qsize()
        web.amazon_queue.queue.clear()
        stats.put(
            "ol.affiliate.amazon.currently_queued_isbns",
            web.amazon_queue.qsize(),
        )
        return json.dumps({"Cleared": "True", "qsize": qsize})


class Submit:
    def GET(self, identifier: str) -> str:
        """
        GET endpoint looking up ISBNs and B* ASINs via the affiliate server.

        URL Parameters:
            - high_priority='true' or 'false': whether to wait and return result.
            - stage_import='true' or 'false': whether to stage result for import.
              By default this is 'true'. Setting this to 'false' is useful when you
              want to return AMZ metadata but don't want to import; therefore
              high_priority=true must also be 'true', or this returns nothing and
              stages nothing (unless the result is cached).

        If `identifier` is in memcache, then return the `hit` (which is marshalled
        into a format appropriate for import on Open Library if `?high_priority=true`).

        By default `stage_import=true`, and results will be staged for import if they have
        requisite fields. Disable staging with `stage_import=false`.

        If no hit, then queue the identifier for look up and either attempt to return
        a promise as `submitted`, or if `?high_priority=true`, return marshalled data
        from the cache.

        `Priority.HIGH` is set when `?high_priority=true` and is the highest priority.
        It is used when the caller is waiting for a response with the AMZ data, if
        available. See `PrioritizedIdentifier` for more on prioritization.

        NOTE: For this API, "ASINs" are ISBN 10s when valid ISBN 10s, and otherwise
        they are Amazon-specific identifiers starting with "B".
        """
        # cache could be None if reached before initialized (mypy)
        if not web.amazon_api:
            return json.dumps({"error": "not_configured"})

        # Handle URL query parameters.
        input = web.input(high_priority=False, stage_import=True)
        priority = (
            Priority.HIGH if input.get("high_priority") == "true" else Priority.LOW
        )
        stage_import = input.get("stage_import") != "false"

        b_asin, isbn_10, isbn_13 = normalize_identifier(identifier)
        key = isbn_10 or b_asin

        # For ISBN 13, conditionally go straight to Google Books.
        if not key and isbn_13 and priority == Priority.HIGH and stage_import:
            return (
                json.dumps({"status": "success"})
                if stage_from_google_books(isbn=isbn_13)
                else json.dumps({"status": "not found"})
            )

        if not (key := isbn_10 or b_asin):
            return json.dumps({"error": "rejected_isbn", "identifier": identifier})

        # Cache lookup by isbn_13 or b_asin. If there's a hit return the product to
        # the caller.
        if product := cache.memcache_cache.get(f'amazon_product_{isbn_13 or b_asin}'):
            return json.dumps(
                {
                    "status": "success",
                    "hit": clean_amazon_metadata_for_load(product),
                }
            )

        # Cache misses will be submitted to Amazon as ASINs (isbn10 if possible, or
        # a 'true' ASIN otherwise) and the response will be `staged` for import.
        if key not in web.amazon_queue.queue:
            key_queue_item = PrioritizedIdentifier(
                identifier=key, priority=priority, stage_import=stage_import
            )
            web.amazon_queue.put_nowait(key_queue_item)

        # Give us a snapshot over time of how many new isbns are currently queued
        stats.put(
            "ol.affiliate.amazon.currently_queued_isbns",
            web.amazon_queue.qsize(),
            rate=0.2,
        )

        # Check the cache a few times for product data to return to the client,
        # or otherwise return.
        if priority == Priority.HIGH:
            for _ in range(RETRIES):
                time.sleep(1)
                if product := cache.memcache_cache.get(
                    f'amazon_product_{isbn_13 or b_asin}'
                ):
                    # If not importing, return whatever data AMZ returns, even if it's unimportable.
                    cleaned_metadata = clean_amazon_metadata_for_load(product)
                    if not stage_import:
                        return json.dumps(
                            {"status": "success", "hit": cleaned_metadata}
                        )

                    # When importing, return a result only if the item can be imported.
                    source, pid = cleaned_metadata['source_records'][0].split(":")
                    if ImportItem.find_staged_or_pending(
                        identifiers=[pid], sources=[source]
                    ):
                        return json.dumps(
                            {"status": "success", "hit": cleaned_metadata}
                        )

            stats.increment("ol.affiliate.amazon.total_items_not_found")

            # Fall back to Google Books
            # TODO: Any point in having option not to stage and just return metadata?
            if isbn_13 and stage_from_google_books(isbn=isbn_13):
                return json.dumps({"status": "success"})

            return json.dumps({"status": "not found"})

        else:
            return json.dumps(
                {"status": "submitted", "queue": web.amazon_queue.qsize()}
            )


def load_config(configfile):
    # This loads openlibrary.yml + infobase.yml
    openlibrary_load_config(configfile)
    http_proxy_url = config.get('http_proxy')

    stats.client = stats.create_stats_client(cfg=config)

    web.amazon_api = None
    args = [
        config.amazon_api.get('key'),
        config.amazon_api.get('secret'),
        config.amazon_api.get('id'),
    ]
    if all(args):
        web.amazon_api = AmazonAPI(*args, throttling=0.9, proxy_url=http_proxy_url)
        logger.info("AmazonAPI Initialized")
    else:
        raise RuntimeError(f"{configfile} is missing required keys.")


def setup_env():
    # make sure PYTHON_EGG_CACHE is writable
    os.environ['PYTHON_EGG_CACHE'] = "/tmp/.python-eggs"

    # required when run as fastcgi
    os.environ['REAL_SCRIPT_NAME'] = ""


def start_server():
    sysargs = sys.argv[1:]
    configfile, args = sysargs[0], sysargs[1:]
    web.ol_configfile = configfile

    # # type: (str) -> None

    load_config(web.ol_configfile)
    setup_requests()

    # sentry loaded by infogami
    infogami._setup()

    if "pytest" not in sys.modules:
        web.amazon_lookup_thread = make_amazon_lookup_thread()
        thread_is_alive = bool(
            web.amazon_lookup_thread and web.amazon_lookup_thread.is_alive()
        )
        logger.critical(f"web.amazon_lookup_thread.is_alive() is {thread_is_alive}")
    else:
        logger.critical("Not starting amazon_lookup_thread in pytest")

    sys.argv = [sys.argv[0]] + list(args)
    app.run()


def start_gunicorn_server():
    """Starts the affiliate server using gunicorn server."""
    from gunicorn.app.base import Application  # noqa: PLC0415

    configfile = sys.argv.pop(1)

    class WSGIServer(Application):
        def init(self, parser, opts, args):
            pass

        def load(self):
            load_config(configfile)
            setup_requests()
            # init_setry(app)
            return app.wsgifunc(https_middleware)

    WSGIServer("%prog openlibrary.yml --gunicorn [options]").run()


def https_middleware(app):
    """Hack to support https even when the app server http only.

    The nginx configuration has changed to add the following setting:

        proxy_set_header X-Scheme $scheme;

    Using that value to overwrite wsgi.url_scheme in the WSGI environ,
    which is used by all redirects and other utilities.
    """

    def wrapper(environ, start_response):
        if environ.get('HTTP_X_SCHEME') == 'https':
            environ['wsgi.url_scheme'] = 'https'
        return app(environ, start_response)

    return wrapper


def runfcgi(func, addr=('localhost', 8000)):
    """Runs a WSGI function as a FastCGI pre-fork server."""
    config = dict(web.config.get("fastcgi", {}))

    mode = config.pop("mode", None)
    if mode == "prefork":
        import flup.server.fcgi_fork as flups  # noqa: PLC0415
    else:
        import flup.server.fcgi as flups  # noqa: PLC0415

    return flups.WSGIServer(func, multiplexed=True, bindAddress=addr, **config).run()


web.config.debug = False
web.wsgi.runfcgi = runfcgi

app = web.application(urls, locals())


if __name__ == "__main__":
    setup_env()
    if "--gunicorn" in sys.argv:
        sys.argv.pop(sys.argv.index("--gunicorn"))
        start_gunicorn_server()
    else:
        start_server()
