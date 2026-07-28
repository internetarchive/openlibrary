import datetime
import io

from openlibrary.catalog import opds2
from openlibrary.catalog.opds2 import (
    EPOCH,
    Source,
    build_acquisition_data,
    extract_cover,
    extract_isbn,
    extract_price,
    find_next_url,
    iter_pages,
    map_publication_to_olbook,
    parse_iso,
    process_feed,
)

# A generic test source (no real provider); the BWB specifics live in the caller.
TEST_SOURCE = Source(provider_name="testprovider", source_id_prefix="test")

SAMPLE_PUBLICATION = {
    "metadata": {
        "type": "http://schema.org/Book",
        "title": "The Brick House Apparent Quarterly, Vol. 1",
        "identifier": "urn:isbn:9781737408802",
        "author": [{"name": "The Brick House Cooperative"}, {"name": "Maria Bustillos"}],
        "language": ["en"],
        "published": "2021-08-03",
        "modified": "2026-05-19T14:47:58.547630-04:00",
    },
    "links": [
        {"rel": "self", "href": "https://example.org/opds/publication/9781737408802"},
        {
            "rel": "http://opds-spec.org/acquisition/buy",
            "href": "https://example.org/purchase/9781737408802",
            "properties": {
                "indirectAcquisition": [{"type": "application/epub+zip"}],
                "price": {"currency": "USD", "value": 1.1},
            },
        },
    ],
    "images": [{"href": "https://example.com/cover.jpg", "rel": "cover"}],
}


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self, pages_by_url):
        self.pages_by_url = pages_by_url
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        return FakeResponse(self.pages_by_url[url])


def test_extract_isbn():
    assert extract_isbn({"identifier": "urn:isbn:9781737408802"}) == "9781737408802"
    assert extract_isbn({"identifier": "urn:uuid:abc"}) is None
    assert extract_isbn({}) is None
    # ISBN-10 is promoted to 13.
    assert extract_isbn({"identifier": "urn:isbn:0140328726"}) == "9780140328721"


def test_extract_price():
    assert extract_price(SAMPLE_PUBLICATION) == {"currency": "USD", "value": 1.1}
    assert extract_price({"links": [{"rel": "self", "href": "x"}]}) is None
    assert extract_price({}) is None
    missing = {"links": [{"rel": "http://opds-spec.org/acquisition/buy", "href": "x"}]}
    assert extract_price(missing) is None


def test_extract_cover():
    assert extract_cover(SAMPLE_PUBLICATION) == "https://example.com/cover.jpg"
    assert extract_cover({"images": [{"href": "x", "rel": "thumbnail"}]}) is None
    assert extract_cover({}) is None


def test_build_acquisition_data():
    data = build_acquisition_data(SAMPLE_PUBLICATION)
    assert data["price"] == {"currency": "USD", "value": 1.1}
    assert data["url"] == "https://example.org/purchase/9781737408802"
    assert data["formats"] == ["application/epub+zip"]


def test_map_publication_uses_source_prefix():
    olbook = map_publication_to_olbook(SAMPLE_PUBLICATION, TEST_SOURCE)
    assert olbook is not None
    assert olbook["isbn_13"] == ["9781737408802"]
    # source_records slug comes from the Source, not hard-coded.
    assert olbook["source_records"] == ["test:9781737408802"]
    assert olbook["languages"] == ["eng"]
    assert olbook["cover"] == "https://example.com/cover.jpg"


def test_map_publication_slug_is_per_source():
    bwbish = Source(provider_name="betterworldbooks", source_id_prefix="bwb")
    olbook = map_publication_to_olbook(SAMPLE_PUBLICATION, bwbish)
    assert olbook["source_records"] == ["bwb:9781737408802"]


def test_map_publication_skips_incomplete():
    assert map_publication_to_olbook({"metadata": {"title": "No ISBN", "author": [{"name": "x"}]}}, TEST_SOURCE) is None
    no_title = {"metadata": {"identifier": "urn:isbn:9781737408802", "author": [{"name": "x"}]}}
    no_authors = {"metadata": {"identifier": "urn:isbn:9781737408802", "title": "x"}}
    assert map_publication_to_olbook(no_title, TEST_SOURCE) is None
    assert map_publication_to_olbook(no_authors, TEST_SOURCE) is None


def test_parse_iso_handles_offset_and_naive():
    dt = parse_iso("2026-05-19T14:47:58.547630-04:00")
    assert dt == datetime.datetime(2026, 5, 19, 18, 47, 58, 547630, tzinfo=datetime.UTC)
    assert parse_iso("2026-05-19T14:47:58").tzinfo is datetime.UTC


def test_find_next_url():
    assert find_next_url({"links": [{"rel": "next", "href": "https://x/p2"}]}) == "https://x/p2"
    assert find_next_url({"links": [{"rel": "self", "href": "x"}]}) is None
    assert find_next_url({}) is None


def test_iter_pages_follows_next_and_breaks_on_cycle(monkeypatch):
    monkeypatch.setattr(opds2, "PAGE_SLEEP_SECONDS", 0)
    pages = {
        "https://x/p1": {"publications": [{"id": 1}], "links": [{"rel": "next", "href": "https://x/p2"}]},
        "https://x/p2": {"publications": [{"id": 2}], "links": [{"rel": "next", "href": "https://x/p1"}]},
    }
    session = FakeSession(pages)
    fetched = list(iter_pages("https://x/p1", session))
    assert [f["publications"][0]["id"] for f in fetched] == [1, 2]
    assert session.calls == ["https://x/p1", "https://x/p2"]


def test_iter_pages_respects_max_pages(monkeypatch):
    monkeypatch.setattr(opds2, "PAGE_SLEEP_SECONDS", 0)
    pages = {
        "https://x/p1": {"publications": [], "links": [{"rel": "next", "href": "https://x/p2"}]},
        "https://x/p2": {"publications": [], "links": [{"rel": "next", "href": "https://x/p3"}]},
        "https://x/p3": {"publications": [], "links": []},
    }
    assert len(list(iter_pages("https://x/p1", FakeSession(pages), max_pages=2))) == 2


def _run(monkeypatch, pages, since, source=TEST_SOURCE, **kwargs):
    monkeypatch.setattr(opds2, "PAGE_SLEEP_SECONDS", 0)
    session = FakeSession(pages)
    monkeypatch.setattr(opds2.requests, "Session", lambda: session)
    return process_feed("https://x/p1", since, io.StringIO(), source, **kwargs)


def test_process_feed_filters_by_modified_and_collects_acquisitions(monkeypatch):
    old = {"metadata": {"identifier": "urn:isbn:9780000000002", "title": "Old", "modified": "2026-01-01T00:00:00+00:00"}, "links": []}
    pages = {"https://x/p1": {"publications": [old, SAMPLE_PUBLICATION], "links": []}}
    acqs: list = []
    cutoff = datetime.datetime(2026, 3, 1, tzinfo=datetime.UTC)
    olbooks, max_modified = _run(monkeypatch, pages, cutoff, acquisitions_out=acqs)
    assert [b["isbn_13"][0] for b in olbooks] == ["9781737408802"]
    assert max_modified > cutoff
    assert acqs == [
        ("9781737408802", {"price": {"currency": "USD", "value": 1.1}, "url": "https://example.org/purchase/9781737408802", "formats": ["application/epub+zip"]})
    ]


def test_process_feed_applies_record_filter(monkeypatch):
    # record_filter that excludes everything -> no olbooks kept.
    drop_all = Source(provider_name="p", source_id_prefix="p", record_filter=lambda _olbook: True)
    pages = {"https://x/p1": {"publications": [SAMPLE_PUBLICATION], "links": []}}
    olbooks, _ = _run(monkeypatch, pages, EPOCH, source=drop_all)
    assert olbooks == []


def test_process_feed_advances_cursor_when_mapping_fails(monkeypatch):
    # Newer record without ISBN still bumps max_modified so it isn't re-scanned forever.
    pub = {"metadata": {"title": "No ISBN", "modified": "2026-05-20T00:00:00+00:00"}, "links": []}
    pages = {"https://x/p1": {"publications": [pub], "links": []}}
    olbooks, max_modified = _run(monkeypatch, pages, EPOCH)
    assert olbooks == []
    assert max_modified == parse_iso("2026-05-20T00:00:00+00:00")


def test_process_feed_early_stop(monkeypatch):
    fresh = SAMPLE_PUBLICATION
    stale = {"metadata": {"identifier": "urn:isbn:9780000000002", "title": "Old", "modified": "2026-01-01T00:00:00+00:00"}, "links": []}
    pages = {
        "https://x/p1": {"publications": [fresh], "links": [{"rel": "next", "href": "https://x/p2"}]},
        "https://x/p2": {"publications": [stale], "links": [{"rel": "next", "href": "https://x/p3"}]},
        "https://x/p3": {"publications": [fresh], "links": []},
    }
    monkeypatch.setattr(opds2, "PAGE_SLEEP_SECONDS", 0)
    session = FakeSession(pages)
    monkeypatch.setattr(opds2.requests, "Session", lambda: session)
    cutoff = datetime.datetime(2026, 3, 1, tzinfo=datetime.UTC)
    olbooks, _ = process_feed("https://x/p1", cutoff, io.StringIO(), TEST_SOURCE, early_stop=True)
    assert session.calls == ["https://x/p1", "https://x/p2"]  # p3 not fetched
    assert len(olbooks) == 1
