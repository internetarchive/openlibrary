"""Tests for the Book Dash source adapter (#14749).

The fixtures under ``samples/bookdash/`` are REAL captured responses from
bookdash.org. They are the upstream-shape sentinels: if Book Dash redesigns its
book page or changes its sitemap, the parse tests below break — loudly, in CI —
instead of a live harvest silently staging nothing (or nothing-with-covers, which
is exactly how the previous standalone scraper rotted unnoticed).
"""

import datetime as dt
from pathlib import Path

import pytest
import requests
import web

from openlibrary.bookworm.adapters import bookdash
from openlibrary.bookworm.adapters.bookdash import (
    BookdashAdapter,
    BookdashFetchError,
    parse_book_page,
    parse_sitemap,
    strip_author_role,
    to_import_record,
)
from openlibrary.bookworm.registry import FeedRegistry

SAMPLES = Path(__file__).parent.parent / "samples" / "bookdash"
EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """The adapter sleeps between fetches to be polite; not in tests."""
    monkeypatch.setattr(bookdash, "REQUEST_DELAY", 0)


class FakeResponse:
    def __init__(self, *, content: bytes = b"", text: str = "", status: int = 200):
        self.content = content
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


class FakeSession:
    """Maps URL -> FakeResponse; records the order of fetches."""

    def __init__(self, responses: dict[str, FakeResponse]):
        self.responses = responses
        self.calls: list[str] = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        if url not in self.responses:
            raise KeyError(url)
        return self.responses[url]


def _feed(url: str = "https://bookdash.org/books-sitemap.xml") -> FeedRegistry:
    """A registry row without a database (iter_records reads only url/last_updated)."""
    return FeedRegistry(provider_name="bookdash", url=url, feed_type="bookdash", last_updated=None, data={})


# --- sitemap parsing -------------------------------------------------------


def test_parse_sitemap_drops_the_index_and_reads_lastmod_and_cover():
    entries = parse_sitemap((SAMPLES / "sitemap.xml").read_bytes())

    # The /books/ index page carries no book and must be dropped.
    assert all(e.url.rstrip("/") != "https://bookdash.org/books" for e in entries)
    by_url = {e.url: e for e in entries}
    assert set(by_url) == {
        "https://bookdash.org/books/a-beautiful-day/",
        "https://bookdash.org/books/usuku-oluhle/",
        "https://bookdash.org/books/no-cover-book/",
        "https://bookdash.org/books/no-lastmod-book/",
    }

    beautiful_day = by_url["https://bookdash.org/books/a-beautiful-day/"]
    assert beautiful_day.lastmod == dt.datetime(2026, 11, 27, 0, 1, 40, tzinfo=dt.UTC)
    assert beautiful_day.cover == "https://bookdash.org/wp-content/uploads/2016/01/a-beautiful-day_cover_20160104.jpg"

    # A book without <image:image> has no cover; without <lastmod> has no cursor.
    assert by_url["https://bookdash.org/books/no-cover-book/"].cover is None
    assert by_url["https://bookdash.org/books/no-lastmod-book/"].lastmod is None


# --- page parsing (the upstream-shape sentinel) ----------------------------


def test_parse_real_book_page():
    html = (SAMPLES / "a-beautiful-day.html").read_text()
    scraped = parse_book_page(html, "https://bookdash.org/books/a-beautiful-day/")

    assert scraped["title"] == "A Beautiful Day"
    assert scraped["languages"] == ["eng"]
    assert scraped["subjects"] == ["Family, friends, and home", "Let's go on an adventure"]
    assert scraped["isbn"] == "978-1-928318-15-6"
    assert "picnic" in scraped["description"]
    # Three contributors (role annotations still attached at the parse stage).
    assert len(scraped["authors"]) == 3


def test_parse_book_page_cover_prefers_sitemap_then_falls_back_to_og_image():
    html = (SAMPLES / "a-beautiful-day.html").read_text()

    # Sitemap cover wins when provided.
    from_sitemap = parse_book_page(html, "https://bookdash.org/books/a-beautiful-day/", sitemap_cover="https://bookdash.org/wp-content/uploads/x.jpg")
    assert from_sitemap["cover_url"] == "https://bookdash.org/wp-content/uploads/x.jpg"

    # Otherwise the page's og:image is used -- the old <picture> scrape is gone.
    from_page = parse_book_page(html, "https://bookdash.org/books/a-beautiful-day/", sitemap_cover=None)
    assert from_page["cover_url"] == "https://bookdash.org/wp-content/uploads/2016/01/a-beautiful-day_cover_20160104.jpg"


def test_parse_book_page_without_title_raises():
    # A page that lost its <h1> is the loudest signal the shape changed; fail the
    # record rather than stage a titleless book.
    with pytest.raises(ValueError, match="Missing <h1>"):
        parse_book_page("<html><body><p>no title here</p></body></html>", "https://bookdash.org/books/x/")


def test_strip_author_role():
    assert strip_author_role("Raeesah Vawda(Designer)") == "Raeesah Vawda"
    assert strip_author_role("Elana Bregin (Writer)") == "Elana Bregin"
    assert strip_author_role("Jane Doe") == "Jane Doe"


# --- mapping to an import record -------------------------------------------


def test_to_import_record_real_page_round_trip():
    html = (SAMPLES / "a-beautiful-day.html").read_text()
    scraped = parse_book_page(
        html,
        "https://bookdash.org/books/a-beautiful-day/",
        sitemap_cover="https://bookdash.org/wp-content/uploads/2016/01/a-beautiful-day_cover_20160104.jpg",
    )
    record = to_import_record(scraped)
    assert record is not None

    assert record["title"] == "A Beautiful Day"
    assert record["source_records"] == ["bookdash:a-beautiful-day"]
    assert record["publishers"] == ["Book Dash"]
    # Roles stripped, order preserved.
    assert record["authors"] == [{"name": "Raeesah Vawda"}, {"name": "Lindy Pelzl"}, {"name": "Elana Bregin"}]
    assert record["languages"] == ["eng"]
    assert record["subjects"] == ["Family, friends, and home", "Let's go on an adventure"]
    # The provider identifier (for the registered-feed validation exemption) AND
    # the strong ISBN.
    assert record["identifiers"] == {"bookdash": ["a-beautiful-day"]}
    assert record["isbn_13"] == ["978-1-928318-15-6"]
    # bookdash.org is allow-listed, so the cover survives the gate.
    assert record["cover"] == "https://bookdash.org/wp-content/uploads/2016/01/a-beautiful-day_cover_20160104.jpg"


def test_to_import_record_without_isbn_has_no_isbn_13_but_keeps_provider_id():
    record = to_import_record(
        {
            "url": "https://bookdash.org/books/no-isbn/",
            "title": "No ISBN Book",
            "authors": ["Someone (Writer)"],
            "languages": ["afr"],
            "subjects": [],
            "description": "",
            "isbn": None,
            "cover_url": None,
        }
    )
    assert record is not None
    assert "isbn_13" not in record
    # Still importable via the feed exemption: the provider id is always present.
    assert record["identifiers"] == {"bookdash": ["no-isbn"]}


def test_to_import_record_drops_disallowed_cover():
    record = to_import_record(
        {
            "url": "https://bookdash.org/books/x/",
            "title": "X",
            "authors": ["An Author"],
            "languages": [],
            "subjects": [],
            "description": "",
            "isbn": None,
            "cover_url": "https://evil.example.com/not-allowed.jpg",
        }
    )
    assert record is not None
    assert "cover" not in record


def test_to_import_record_without_title_returns_none():
    assert to_import_record({"url": "https://bookdash.org/books/x/", "title": ""}) is None


def test_to_import_record_without_authors_returns_none():
    # An authorless record would stage then fail FeedSourcedBook validation
    # silently; dropping it here makes a selector drift show up as a record-count
    # collapse instead. (FeedSourcedBook and the OPDS path both require authors.)
    record = to_import_record(
        {
            "url": "https://bookdash.org/books/x/",
            "title": "X",
            "authors": [],
            "languages": ["eng"],
            "subjects": [],
            "description": "",
            "isbn": "978-1-928318-15-6",
            "cover_url": None,
        }
    )
    assert record is None


def test_to_import_record_routes_isbn_by_length():
    base = {
        "url": "https://bookdash.org/books/x/",
        "title": "X",
        "authors": ["An Author"],
        "languages": [],
        "subjects": [],
        "description": "",
        "cover_url": None,
    }
    isbn13 = to_import_record({**base, "isbn": "978-1-928318-15-6"})
    assert isbn13 is not None
    assert isbn13["isbn_13"] == ["978-1-928318-15-6"]
    assert "isbn_10" not in isbn13

    isbn10 = to_import_record({**base, "isbn": "1-928318-15-9"})
    assert isbn10 is not None
    assert isbn10["isbn_10"] == ["1-928318-15-9"]
    assert "isbn_13" not in isbn10


def test_parse_book_page_tolerates_og_description_without_content(monkeypatch):
    # A meta tag present but missing its content attribute must not crash the
    # parse (and so drop the whole book) over an optional field.
    html = '<html><body><h1>T</h1><meta property="og:description"></body></html>'
    scraped = parse_book_page(html, "https://bookdash.org/books/t/")
    assert scraped["description"] == ""


# --- the adapter end to end (fake transport) -------------------------------


def _responses(pages: dict[str, str]) -> dict[str, FakeResponse]:
    responses = {"https://bookdash.org/books-sitemap.xml": FakeResponse(content=(SAMPLES / "sitemap.xml").read_bytes())}
    real = (SAMPLES / "a-beautiful-day.html").read_text()
    for url, html in pages.items():
        responses[url] = FakeResponse(text=html if html is not None else real)
    return responses


def test_iter_records_yields_record_and_lastmod_per_book():
    # Serve the real page HTML for every book URL in the sitemap.
    book_urls = [
        "https://bookdash.org/books/a-beautiful-day/",
        "https://bookdash.org/books/usuku-oluhle/",
        "https://bookdash.org/books/no-cover-book/",
        "https://bookdash.org/books/no-lastmod-book/",
    ]
    session = FakeSession(_responses(dict.fromkeys(book_urls)))

    pairs = list(BookdashAdapter().iter_records(_feed(), since=EPOCH, session=session))

    assert len(pairs) == 4
    record, lastmod = pairs[0]
    assert record["source_records"] == ["bookdash:a-beautiful-day"]
    assert lastmod == dt.datetime(2026, 11, 27, 0, 1, 40, tzinfo=dt.UTC)
    # The book with no <lastmod> yields modified=None.
    assert any(mod is None for _rec, mod in pairs)


def test_iter_records_skips_books_at_or_below_the_cursor_without_fetching_them():
    book_urls = [
        "https://bookdash.org/books/a-beautiful-day/",
        "https://bookdash.org/books/usuku-oluhle/",
        "https://bookdash.org/books/no-cover-book/",
        "https://bookdash.org/books/no-lastmod-book/",
    ]
    session = FakeSession(_responses(dict.fromkeys(book_urls)))

    # Cursor after the two 2026-11-27 books but before/at no-cover-book (2026-11-20).
    since = dt.datetime(2026, 11, 25, tzinfo=dt.UTC)
    pairs = list(BookdashAdapter().iter_records(_feed(), since=since, session=session))

    # Only the two books newer than the cursor; no-cover-book (older) is skipped,
    # and the no-lastmod book (modified=None) is always considered.
    staged = {rec["source_records"][0] for rec, _mod in pairs}
    assert staged == {"bookdash:a-beautiful-day", "bookdash:usuku-oluhle", "bookdash:no-lastmod-book"}
    # The skipped older book's page was never fetched.
    assert "https://bookdash.org/books/no-cover-book/" not in session.calls


def test_iter_records_max_pages_truncates_and_flags_state():
    book_urls = [
        "https://bookdash.org/books/a-beautiful-day/",
        "https://bookdash.org/books/usuku-oluhle/",
        "https://bookdash.org/books/no-cover-book/",
        "https://bookdash.org/books/no-lastmod-book/",
    ]
    session = FakeSession(_responses(dict.fromkeys(book_urls)))
    state: dict = {}

    pairs = list(BookdashAdapter().iter_records(_feed(), since=EPOCH, session=session, max_pages=1, state=state))

    assert len(pairs) == 1
    # Cutting the crawl short must flag truncation so the harvester warns that the
    # cursor advanced past unfetched books.
    assert state["truncated"] is True


def _responses_with(status_or_text: dict[str, object]) -> dict[str, FakeResponse]:
    """Sitemap + real page for every book, overriding named URLs with a status/text."""
    responses = {"https://bookdash.org/books-sitemap.xml": FakeResponse(content=(SAMPLES / "sitemap.xml").read_bytes())}
    real = (SAMPLES / "a-beautiful-day.html").read_text()
    for url in (
        "https://bookdash.org/books/a-beautiful-day/",
        "https://bookdash.org/books/usuku-oluhle/",
        "https://bookdash.org/books/no-cover-book/",
        "https://bookdash.org/books/no-lastmod-book/",
    ):
        override = status_or_text.get(url)
        if isinstance(override, int):
            responses[url] = FakeResponse(status=override)
        elif isinstance(override, str):
            responses[url] = FakeResponse(text=override)
        else:
            responses[url] = FakeResponse(text=real)
    return responses


def test_iter_records_skips_a_gone_page_without_aborting_the_crawl():
    # A 404/410 book is permanently gone: skip it, keep harvesting, do NOT raise
    # (one deleted book must not wedge the whole feed).
    session = FakeSession(_responses_with({"https://bookdash.org/books/a-beautiful-day/": 410}))

    pairs = list(BookdashAdapter().iter_records(_feed(), since=EPOCH, session=session))

    staged = {rec["source_records"][0] for rec, _mod in pairs}
    assert "bookdash:a-beautiful-day" not in staged  # the gone book was skipped
    assert len(staged) == 3  # the other three still harvested


def test_iter_records_raises_on_a_transient_fetch_failure_to_hold_the_cursor():
    # A non-gone HTTP error (after the session's own retries) is transient: the
    # whole run must fail so the harvester holds the cursor and retries next run,
    # rather than letting a newer book advance the cursor past the failed one.
    session = FakeSession(_responses_with({"https://bookdash.org/books/no-cover-book/": 503}))

    with pytest.raises(BookdashFetchError):
        list(BookdashAdapter().iter_records(_feed(), since=EPOCH, session=session))


def test_iter_records_raises_on_a_network_error():
    class FlakySession(FakeSession):
        def get(self, url, **kwargs):
            if url == "https://bookdash.org/books/usuku-oluhle/":
                raise requests.ConnectionError("boom")
            return super().get(url, **kwargs)

    session = FlakySession(_responses_with({}))
    with pytest.raises(BookdashFetchError):
        list(BookdashAdapter().iter_records(_feed(), since=EPOCH, session=session))


def test_iter_records_skips_an_unparseable_page_and_flags_truncated():
    # A deterministic parse failure (shape drift) is skipped this run and the run
    # is flagged truncated (operator-visible) rather than raising and wedging the
    # feed. The other books still harvest.
    session = FakeSession(_responses_with({"https://bookdash.org/books/a-beautiful-day/": "<html><body>no h1</body></html>"}))
    state: dict = {}

    pairs = list(BookdashAdapter().iter_records(_feed(), since=EPOCH, session=session, state=state))

    staged = {rec["source_records"][0] for rec, _mod in pairs}
    assert "bookdash:a-beautiful-day" not in staged
    assert len(staged) == 3
    assert state["truncated"] is True


def test_web_storage_feed_exposes_fields():
    # Guard the no-DB test helper: FeedRegistry is a web.storage, so attribute
    # access must work for the fields iter_records reads.
    feed = _feed()
    assert isinstance(feed, web.storage)
    assert feed.url == "https://bookdash.org/books-sitemap.xml"
    assert feed.feed_type == "bookdash"
