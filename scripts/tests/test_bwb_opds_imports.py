import datetime
import io
import json
from pathlib import Path

import pytest

from .. import bwb_opds_imports
from ..bwb_opds_imports import (
    EPOCH,
    _parse_iso,
    _registry_cursor,
    extract_acquisition,
    extract_buy_url,
    extract_cover,
    extract_isbn,
    extract_price,
    find_next_url,
    iter_pages,
    map_publication_to_olbook,
    process_feed,
    read_state,
    upsert_acquisitions,
    write_state,
)

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
        {"rel": "self", "href": "https://www.betterworldbooks.com/opds/publication/9781737408802"},
        {
            "rel": "http://opds-spec.org/acquisition/buy",
            "href": "https://www.betterworldbooks.com/purchase/9781737408802",
            "properties": {"price": {"currency": "USD", "value": 1.1}},
        },
    ],
    "images": [{"href": "https://example.com/cover.jpg", "rel": "cover"}],
}


def test_extract_isbn_strips_urn_prefix():
    assert extract_isbn({"identifier": "urn:isbn:9781737408802"}) == "9781737408802"


def test_extract_isbn_returns_none_for_non_isbn_urn():
    assert extract_isbn({"identifier": "urn:uuid:abc"}) is None
    assert extract_isbn({}) is None


def test_extract_isbn_promotes_isbn10():
    # to_isbn_13 should upgrade a valid ISBN-10 to ISBN-13
    assert extract_isbn({"identifier": "urn:isbn:0140328726"}) == "9780140328721"


def test_extract_price_returns_first_buy_link():
    assert extract_price(SAMPLE_PUBLICATION) == {"currency": "USD", "value": 1.1}


def test_extract_price_returns_none_when_no_acquisition():
    assert extract_price({"links": [{"rel": "self", "href": "x"}]}) is None
    assert extract_price({}) is None


def test_extract_price_returns_none_when_acquisition_missing_price():
    pub = {"links": [{"rel": "http://opds-spec.org/acquisition/buy", "href": "x"}]}
    assert extract_price(pub) is None


def test_extract_cover():
    assert extract_cover(SAMPLE_PUBLICATION) == "https://example.com/cover.jpg"
    assert extract_cover({"images": [{"href": "x", "rel": "thumbnail"}]}) is None
    assert extract_cover({}) is None


def test_map_publication_basic_fields():
    olbook = map_publication_to_olbook(SAMPLE_PUBLICATION)
    assert olbook is not None
    assert olbook["isbn_13"] == ["9781737408802"]
    assert olbook["source_records"] == ["bwb:9781737408802"]
    assert olbook["title"] == "The Brick House Apparent Quarterly, Vol. 1"
    assert olbook["publish_date"] == "2021-08-03"
    assert olbook["languages"] == ["eng"]
    assert olbook["authors"] == [
        {"name": "The Brick House Cooperative"},
        {"name": "Maria Bustillos"},
    ]
    assert olbook["cover"] == "https://example.com/cover.jpg"
    assert olbook["publishers"] == []
    assert "local_id" not in olbook


def test_map_publication_skips_missing_isbn():
    pub = {"metadata": {"title": "No ISBN", "author": [{"name": "x"}]}}
    assert map_publication_to_olbook(pub) is None


def test_map_publication_skips_missing_title_or_authors():
    no_title = {"metadata": {"identifier": "urn:isbn:9781737408802", "author": [{"name": "x"}]}}
    no_authors = {"metadata": {"identifier": "urn:isbn:9781737408802", "title": "x"}}
    assert map_publication_to_olbook(no_title) is None
    assert map_publication_to_olbook(no_authors) is None


def test_map_publication_languages_use_marc21():
    pub = {
        "metadata": {
            "identifier": "urn:isbn:9781737408802",
            "title": "x",
            "author": [{"name": "a"}],
            "language": ["en", "fr"],
        }
    }
    olbook = map_publication_to_olbook(pub)
    assert olbook is not None
    assert olbook["languages"] == ["eng", "fre"]


def test_map_publication_drops_unmappable_language():
    pub = {
        "metadata": {
            "identifier": "urn:isbn:9781737408802",
            "title": "x",
            "author": [{"name": "a"}],
            "language": ["zz-not-real"],
        }
    }
    olbook = map_publication_to_olbook(pub)
    assert olbook is not None
    assert olbook["languages"] == []


def test_parse_iso_handles_offset_and_naive():
    dt = _parse_iso("2026-05-19T14:47:58.547630-04:00")
    assert dt.tzinfo is datetime.UTC
    assert dt == datetime.datetime(2026, 5, 19, 18, 47, 58, 547630, tzinfo=datetime.UTC)

    naive = _parse_iso("2026-05-19T14:47:58")
    assert naive.tzinfo is datetime.UTC


def test_find_next_url_present_and_absent():
    feed = {"links": [{"rel": "next", "href": "https://x/p2"}, {"rel": "self", "href": "x"}]}
    assert find_next_url(feed) == "https://x/p2"
    assert find_next_url({"links": [{"rel": "self", "href": "x"}]}) is None
    assert find_next_url({}) is None


def test_state_roundtrip(tmp_path: Path):
    state_file = tmp_path / "state.txt"
    assert read_state(str(state_file)) == EPOCH

    ts = datetime.datetime(2026, 5, 22, 12, 0, 0, tzinfo=datetime.UTC)
    write_state(str(state_file), ts)
    assert read_state(str(state_file)) == ts


def test_state_read_empty_file_returns_epoch(tmp_path: Path):
    state_file = tmp_path / "state.txt"
    state_file.write_text("")
    assert read_state(str(state_file)) == EPOCH


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


def test_iter_pages_follows_next_link(monkeypatch):

    monkeypatch.setattr(bwb_opds_imports, "PAGE_SLEEP_SECONDS", 0)
    pages = {
        "https://x/p1": {"publications": [{"id": 1}], "links": [{"rel": "next", "href": "https://x/p2"}]},
        "https://x/p2": {"publications": [{"id": 2}], "links": [{"rel": "self", "href": "https://x/p2"}]},
    }
    session = FakeSession(pages)
    fetched = list(iter_pages("https://x/p1", session))
    assert [f["publications"][0]["id"] for f in fetched] == [1, 2]
    assert session.calls == ["https://x/p1", "https://x/p2"]


def test_iter_pages_breaks_on_cycle(monkeypatch):

    monkeypatch.setattr(bwb_opds_imports, "PAGE_SLEEP_SECONDS", 0)
    pages = {"https://x/p1": {"publications": [], "links": [{"rel": "next", "href": "https://x/p1"}]}}
    session = FakeSession(pages)
    fetched = list(iter_pages("https://x/p1", session))
    assert len(fetched) == 1


def test_iter_pages_respects_max_pages(monkeypatch):

    monkeypatch.setattr(bwb_opds_imports, "PAGE_SLEEP_SECONDS", 0)
    pages = {
        "https://x/p1": {"publications": [], "links": [{"rel": "next", "href": "https://x/p2"}]},
        "https://x/p2": {"publications": [], "links": [{"rel": "next", "href": "https://x/p3"}]},
        "https://x/p3": {"publications": [], "links": []},
    }
    session = FakeSession(pages)
    fetched = list(iter_pages("https://x/p1", session, max_pages=2))
    assert len(fetched) == 2


def test_process_feed_filters_by_modified(monkeypatch):

    monkeypatch.setattr(bwb_opds_imports, "PAGE_SLEEP_SECONDS", 0)
    old_pub = {
        "metadata": {
            "identifier": "urn:isbn:9780000000002",
            "title": "Old",
            "modified": "2026-01-01T00:00:00+00:00",
        },
        "links": [],
    }
    new_pub = dict(SAMPLE_PUBLICATION)
    pages = {"https://x/p1": {"publications": [old_pub, new_pub], "links": []}}
    session = FakeSession(pages)
    monkeypatch.setattr(bwb_opds_imports.requests, "Session", lambda: session)

    cutoff = datetime.datetime(2026, 3, 1, tzinfo=datetime.UTC)
    prices_fh = io.StringIO()
    olbooks, max_modified = process_feed(
        feed_url="https://x/p1",
        since=cutoff,
        prices_out_fh=prices_fh,
    )
    assert len(olbooks) == 1
    assert olbooks[0]["isbn_13"] == ["9781737408802"]
    assert max_modified > cutoff

    price_lines = [json.loads(line) for line in prices_fh.getvalue().splitlines()]
    assert price_lines == [{"isbn_13": "9781737408802", "price": 1.1, "currency": "USD"}]


def test_process_feed_skips_publication_without_modified(monkeypatch):
    monkeypatch.setattr(bwb_opds_imports, "PAGE_SLEEP_SECONDS", 0)
    pub = {"metadata": {"identifier": "urn:isbn:9781737408802", "title": "x"}, "links": []}
    pages = {"https://x/p1": {"publications": [pub], "links": []}}
    session = FakeSession(pages)
    monkeypatch.setattr(bwb_opds_imports.requests, "Session", lambda: session)

    olbooks, max_modified = process_feed(
        feed_url="https://x/p1",
        since=EPOCH,
        prices_out_fh=io.StringIO(),
    )
    assert olbooks == []
    assert max_modified == EPOCH


def test_process_feed_advances_state_when_mapping_fails(monkeypatch):
    """Newer publication without ISBN must still bump max_modified — otherwise
    every future run re-scans the same record forever.
    """
    monkeypatch.setattr(bwb_opds_imports, "PAGE_SLEEP_SECONDS", 0)
    new_modified = "2026-05-20T00:00:00+00:00"
    pub = {"metadata": {"title": "No ISBN here", "modified": new_modified}, "links": []}
    pages = {"https://x/p1": {"publications": [pub], "links": []}}
    session = FakeSession(pages)
    monkeypatch.setattr(bwb_opds_imports.requests, "Session", lambda: session)

    olbooks, max_modified = process_feed(
        feed_url="https://x/p1",
        since=EPOCH,
        prices_out_fh=io.StringIO(),
    )
    assert olbooks == []
    assert max_modified == _parse_iso(new_modified)


def test_process_feed_early_stops_on_first_all_stale_page(monkeypatch):
    """Once a whole page contains nothing newer than ``since``, stop walking."""
    monkeypatch.setattr(bwb_opds_imports, "PAGE_SLEEP_SECONDS", 0)
    fresh = dict(SAMPLE_PUBLICATION)
    stale = {
        "metadata": {
            "identifier": "urn:isbn:9780000000002",
            "title": "Old",
            "modified": "2026-01-01T00:00:00+00:00",
        },
        "links": [],
    }
    pages = {
        "https://x/p1": {"publications": [fresh], "links": [{"rel": "next", "href": "https://x/p2"}]},
        "https://x/p2": {"publications": [stale], "links": [{"rel": "next", "href": "https://x/p3"}]},
        "https://x/p3": {"publications": [fresh], "links": []},
    }
    session = FakeSession(pages)
    monkeypatch.setattr(bwb_opds_imports.requests, "Session", lambda: session)

    cutoff = datetime.datetime(2026, 3, 1, tzinfo=datetime.UTC)
    olbooks, _ = process_feed(
        feed_url="https://x/p1",
        since=cutoff,
        prices_out_fh=io.StringIO(),
        early_stop=True,
    )
    # p3 must NOT be fetched.
    assert session.calls == ["https://x/p1", "https://x/p2"]
    assert len(olbooks) == 1


def test_process_feed_full_traversal_is_the_default(monkeypatch):
    monkeypatch.setattr(bwb_opds_imports, "PAGE_SLEEP_SECONDS", 0)
    stale = {
        "metadata": {
            "identifier": "urn:isbn:9780000000002",
            "title": "Old",
            "modified": "2026-01-01T00:00:00+00:00",
        },
        "links": [],
    }
    pages = {
        "https://x/p1": {"publications": [stale], "links": [{"rel": "next", "href": "https://x/p2"}]},
        "https://x/p2": {"publications": [stale], "links": []},
    }
    session = FakeSession(pages)
    monkeypatch.setattr(bwb_opds_imports.requests, "Session", lambda: session)

    process_feed(
        feed_url="https://x/p1",
        since=datetime.datetime(2026, 3, 1, tzinfo=datetime.UTC),
        prices_out_fh=io.StringIO(),
    )
    # Default early_stop=False — both pages fetched even when first is all-stale.
    assert session.calls == ["https://x/p1", "https://x/p2"]


def test_process_feed_excludes_low_quality(monkeypatch):
    """Reuse partner-import filters: independently-published 'notebook' from 2024 is dropped."""
    monkeypatch.setattr(bwb_opds_imports, "PAGE_SLEEP_SECONDS", 0)
    junk = {
        "metadata": {
            "identifier": "urn:isbn:9781737408802",
            "title": "My Notebook",
            "modified": "2026-05-20T00:00:00+00:00",
            "published": "2024-01-01",
            "publisher": [{"name": "Independently Published"}],
            "author": [{"name": "Whoever"}],
        },
        "links": [],
    }
    pages = {"https://x/p1": {"publications": [junk], "links": []}}
    session = FakeSession(pages)
    monkeypatch.setattr(bwb_opds_imports.requests, "Session", lambda: session)

    # Patch the mapper to inject publishers (OPDS metadata doesn't always expose them
    # under a fixed key, and we just need the filter wired correctly).
    real_map = bwb_opds_imports.map_publication_to_olbook

    def fake_map(pub):
        olbook = real_map(pub)
        if olbook is not None:
            olbook["publishers"] = ["Independently Published"]
            olbook["publish_date"] = "2024-01-01"
        return olbook

    monkeypatch.setattr(bwb_opds_imports, "map_publication_to_olbook", fake_map)

    olbooks, _ = process_feed(
        feed_url="https://x/p1",
        since=EPOCH,
        prices_out_fh=io.StringIO(),
    )
    assert olbooks == []


def test_lazy_writer_does_not_create_file_when_unused(tmp_path: Path):
    path = tmp_path / "subdir" / "prices.jsonl"
    w = bwb_opds_imports._LazyWriter(str(path))
    w.close()
    assert not path.exists()


def test_lazy_writer_creates_file_on_write(tmp_path: Path):
    path = tmp_path / "subdir" / "prices.jsonl"
    w = bwb_opds_imports._LazyWriter(str(path))
    w.write("hello\n")
    w.close()
    assert path.read_text() == "hello\n"


@pytest.mark.parametrize(
    "modified_raw",
    ["not-a-date", "2026/05/19"],
)
def test_process_feed_logs_and_skips_bad_modified(monkeypatch, modified_raw):
    monkeypatch.setattr(bwb_opds_imports, "PAGE_SLEEP_SECONDS", 0)
    pub = {
        "metadata": {"identifier": "urn:isbn:9781737408802", "modified": modified_raw},
        "links": [],
    }
    pages = {"https://x/p1": {"publications": [pub], "links": []}}
    session = FakeSession(pages)
    monkeypatch.setattr(bwb_opds_imports.requests, "Session", lambda: session)

    olbooks, _ = process_feed(
        feed_url="https://x/p1",
        since=EPOCH,
        prices_out_fh=io.StringIO(),
    )
    assert olbooks == []


# --- PR3: acquisitions + registry ------------------------------------------


def test_extract_buy_url():
    assert extract_buy_url(SAMPLE_PUBLICATION) == "https://www.betterworldbooks.com/purchase/9781737408802"
    assert extract_buy_url({"links": []}) is None


def test_extract_acquisition_captures_price_and_url():
    assert extract_acquisition(SAMPLE_PUBLICATION) == {
        "price": 1.1,
        "currency": "USD",
        "url": "https://www.betterworldbooks.com/purchase/9781737408802",
    }


def test_extract_acquisition_none_without_buy_link():
    assert extract_acquisition({"links": []}) is None


def test_process_feed_collects_acquisitions(monkeypatch):
    monkeypatch.setattr(bwb_opds_imports, "PAGE_SLEEP_SECONDS", 0)
    pages = {"https://x/p1": {"publications": [SAMPLE_PUBLICATION], "links": []}}
    session = FakeSession(pages)
    monkeypatch.setattr(bwb_opds_imports.requests, "Session", lambda: session)

    acquisitions: list = []
    process_feed(
        feed_url="https://x/p1",
        since=EPOCH,
        prices_out_fh=io.StringIO(),
        acquisitions_out=acquisitions,
    )
    assert acquisitions == [
        {
            "isbn_13": "9781737408802",
            "data": {
                "price": 1.1,
                "currency": "USD",
                "url": "https://www.betterworldbooks.com/purchase/9781737408802",
            },
        }
    ]


class _FakeThing:
    def __init__(self, key):
        self.key = key


class _FakeEdition:
    def __init__(self, key, work_key):
        self.key = key
        self.works = [_FakeThing(work_key)] if work_key else []


def test_upsert_acquisitions_maps_existing_editions(monkeypatch):
    editions = {"9781737408802": _FakeEdition("/books/OL55M", "/works/OL7W")}
    monkeypatch.setattr(bwb_opds_imports.Edition, "from_isbn", staticmethod(lambda isbn, allow_import=False: editions.get(isbn)))
    calls = []
    monkeypatch.setattr(
        bwb_opds_imports.Acquisition,
        "upsert",
        staticmethod(lambda work_id, edition_id, provider_name, data=None: calls.append((work_id, edition_id, provider_name, data))),
    )

    records = [
        {"isbn_13": "9781737408802", "data": {"price": 1.1}},
        {"isbn_13": "9780000000000", "data": {"price": 2.0}},  # no edition yet -> skipped
    ]
    upserted = upsert_acquisitions(records, "betterworldbooks")
    assert upserted == 1
    assert calls == [(7, 55, "betterworldbooks", {"price": 1.1})]


def test_upsert_acquisitions_skips_workless_edition(monkeypatch):
    monkeypatch.setattr(bwb_opds_imports.Edition, "from_isbn", staticmethod(lambda isbn, allow_import=False: _FakeEdition("/books/OL55M", None)))
    monkeypatch.setattr(
        bwb_opds_imports.Acquisition,
        "upsert",
        staticmethod(lambda *a, **k: pytest.fail("should not upsert a workless edition")),
    )
    assert upsert_acquisitions([{"isbn_13": "9781737408802", "data": {}}]) == 0


def test_registry_cursor_naive_and_none():
    assert _registry_cursor(None) is None
    assert _registry_cursor(bwb_opds_imports.FeedRegistry({"last_updated": None})) is None
    naive = datetime.datetime(2026, 5, 1, 12, 0, 0)
    cur = _registry_cursor(bwb_opds_imports.FeedRegistry({"last_updated": naive}))
    assert cur == datetime.datetime(2026, 5, 1, 12, 0, 0, tzinfo=datetime.UTC)
