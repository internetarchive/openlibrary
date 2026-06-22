import datetime
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import web

from openlibrary.utils.opds_types import OPDSPublication, OPDSPublicationMetadata

from .. import bwb_opds_imports
from ..bwb_opds_imports import (
    EPOCH,
    PublicationResult,
    _parse_iso,
    _registry_cursor,
    map_publication_to_ol_book,
    process_feed,
    upsert_acquisitions,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_PUB_DICT = {
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
    "images": [{"rel": "cover", "href": "https://example.com/cover.jpg"}],
}

SAMPLE_PUBLICATION = OPDSPublication.model_validate(SAMPLE_PUB_DICT)

# Real BWB OPDS feed response with 2 publications, used for full-pipeline tests.
SAMPLE_FEED_URL = "https://www.betterworldbooks.com/opds/"
SAMPLE_FEED_JSON = json.loads(Path(__file__).parent.joinpath("opds_sample.json").read_text())


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

    def get(self, url, **kwargs):
        return FakeResponse(self.pages_by_url[url])


def _make_feed_json(*pub_dicts, next_url=None):
    links = [{"rel": "next", "href": next_url}] if next_url else []
    return {"metadata": {"title": "BWB"}, "links": links, "publications": list(pub_dicts)}


def _patch_session(monkeypatch, pages_by_url):
    monkeypatch.setattr(bwb_opds_imports.requests, "Session", lambda: FakeSession(pages_by_url))


def _make_result(isbn_13="9781737408802", buy_link=None):
    return PublicationResult(
        provider_name="bwb",
        local_publication_id=f"https://www.betterworldbooks.com/opds/publication/{isbn_13}",
        ol_book={
            "title": "x",
            "isbn_13": [isbn_13],
            "source_records": [f"bwb:{isbn_13}"],
            "authors": [],
            "languages": [],
            "publish_date": "",
            "publishers": [],
        },
        modified=datetime.datetime(2026, 5, 19, tzinfo=datetime.UTC),
        buy_link=buy_link,
    )


# ---------------------------------------------------------------------------
# _parse_iso
# ---------------------------------------------------------------------------


def test_parse_iso_handles_timezone_offset():
    dt = _parse_iso("2026-05-19T14:47:58.547630-04:00")
    assert dt.tzinfo is datetime.UTC
    assert dt == datetime.datetime(2026, 5, 19, 18, 47, 58, 547630, tzinfo=datetime.UTC)


def test_parse_iso_treats_naive_as_utc():
    dt = _parse_iso("2026-05-19T14:47:58")
    assert dt.tzinfo is datetime.UTC
    assert dt.hour == 14


# ---------------------------------------------------------------------------
# map_publication_to_ol_book
# ---------------------------------------------------------------------------


def test_map_publication_basic_fields():
    ol_book = map_publication_to_ol_book(SAMPLE_PUBLICATION)
    assert ol_book == {
        "title": "The Brick House Apparent Quarterly, Vol. 1",
        "isbn_13": ["9781737408802"],
        "source_records": ["bwb:9781737408802"],
        "authors": [{"name": "The Brick House Cooperative"}, {"name": "Maria Bustillos"}],
        "languages": ["eng"],
        "publish_date": "2021-08-03",
        "publishers": [],
        "cover": "https://example.com/cover.jpg",
    }


@pytest.mark.parametrize(
    "metadata",
    [
        OPDSPublicationMetadata.model_validate({"title": "No ISBN", "author": [{"name": "x"}]}),
        OPDSPublicationMetadata.model_validate({"title": "", "identifier": "urn:isbn:9781737408802", "author": [{"name": "x"}]}),
        OPDSPublicationMetadata.model_validate({"title": "x", "identifier": "urn:isbn:9781737408802"}),  # no authors
    ],
)
def test_map_publication_returns_none_for_incomplete_metadata(metadata):
    pub = OPDSPublication(metadata=metadata)
    assert map_publication_to_ol_book(pub) is None


def test_map_publication_isbn10_promoted_to_isbn13():
    pub = OPDSPublication.model_validate(
        {
            "metadata": {
                "title": "x",
                "identifier": "urn:isbn:0140328726",
                "author": [{"name": "a"}],
            },
        }
    )
    ol_book = map_publication_to_ol_book(pub)
    assert ol_book is not None
    assert ol_book["isbn_13"] == ["9780140328721"]


def test_map_publication_languages_use_marc21():
    pub = OPDSPublication.model_validate(
        {
            "metadata": {
                "title": "x",
                "identifier": "urn:isbn:9781737408802",
                "author": [{"name": "a"}],
                "language": ["en", "fr"],
            },
        }
    )
    ol_book = map_publication_to_ol_book(pub)
    assert ol_book is not None
    assert ol_book["languages"] == ["eng", "fre"]


def test_map_publication_drops_unmappable_language():
    pub = OPDSPublication.model_validate(
        {
            "metadata": {
                "title": "x",
                "identifier": "urn:isbn:9781737408802",
                "author": [{"name": "a"}],
                "language": ["zz-not-real"],
            },
        }
    )
    ol_book = map_publication_to_ol_book(pub)
    assert ol_book is not None
    assert ol_book["languages"] == []


# ---------------------------------------------------------------------------
# process_feed — full pipeline via requests.Session patch
# ---------------------------------------------------------------------------


def test_process_feed_yields_results_from_sample_feed(monkeypatch):
    """Full pipeline test: HTTP response → OPDSFeed.model_validate → PublicationResult."""
    _patch_session(monkeypatch, {SAMPLE_FEED_URL: SAMPLE_FEED_JSON})
    results = list(process_feed(SAMPLE_FEED_URL, since=EPOCH))
    assert len(results) == 2

    r = results[0]
    assert isinstance(r, PublicationResult)
    assert r.provider_name == "bwb"
    assert r.local_publication_id == "https://www.betterworldbooks.com/opds/publication/9781737408802"
    assert r.ol_book["isbn_13"] == ["9781737408802"]
    assert r.buy_link is not None
    assert r.buy_link.properties.price.value == 1.25
    assert r.buy_link.properties.price.currency == "USD"


def test_process_feed_filters_by_modified(monkeypatch):
    old_pub = {
        "metadata": {
            "title": "Old Book",
            "identifier": "urn:isbn:9780000000002",
            "author": [{"name": "x"}],
            "modified": "2026-01-01T00:00:00+00:00",
        },
        "links": [{"rel": "self", "href": "https://x/old"}],
    }
    _patch_session(monkeypatch, {"https://x/p1": _make_feed_json(old_pub, SAMPLE_PUB_DICT)})
    results = list(process_feed("https://x/p1", since=datetime.datetime(2026, 3, 1, tzinfo=datetime.UTC)))
    assert len(results) == 1
    assert results[0].ol_book["isbn_13"] == ["9781737408802"]


def test_process_feed_skips_publication_without_self_link(monkeypatch):
    no_self = {
        "metadata": {
            "title": "x",
            "identifier": "urn:isbn:9781737408802",
            "author": [{"name": "a"}],
            "modified": "2026-05-20T00:00:00+00:00",
        },
        # links defaults to []
    }
    _patch_session(monkeypatch, {"https://x/p1": _make_feed_json(no_self)})
    assert list(process_feed("https://x/p1", since=EPOCH)) == []


def test_process_feed_skips_publication_without_modified(monkeypatch):
    no_modified = {
        "metadata": {
            "title": "x",
            "identifier": "urn:isbn:9781737408802",
            "author": [{"name": "a"}],
        },
        "links": [{"rel": "self", "href": "https://x"}],
    }
    _patch_session(monkeypatch, {"https://x/p1": _make_feed_json(no_modified)})
    assert list(process_feed("https://x/p1", since=EPOCH)) == []


def test_process_feed_excludes_low_quality(monkeypatch):
    """Publications are dropped when _should_exclude returns True."""
    monkeypatch.setattr(bwb_opds_imports, "_should_exclude", lambda ol_book: True)
    _patch_session(monkeypatch, {"https://x/p1": _make_feed_json(SAMPLE_PUB_DICT)})
    assert list(process_feed("https://x/p1", since=EPOCH)) == []


# ---------------------------------------------------------------------------
# upsert_acquisitions
# ---------------------------------------------------------------------------


class _FakeThing:
    def __init__(self, key):
        self.key = key


class _FakeEdition:
    def __init__(self, key, work_key):
        self.key = key
        self.works = [_FakeThing(work_key)] if work_key else []


def test_upsert_acquisitions_isbn_fallback(monkeypatch):
    editions = {"9781737408802": _FakeEdition("/books/OL55M", "/works/OL7W")}
    monkeypatch.setattr(
        bwb_opds_imports.Edition,
        "from_isbn",
        staticmethod(lambda isbn, allow_import=False: editions.get(isbn)),
    )
    calls = []
    monkeypatch.setattr(
        bwb_opds_imports.Acquisition,
        "upsert",
        staticmethod(lambda work_id, edition_id, provider_name, local_publication_id, data=None: calls.append((work_id, edition_id, provider_name, data))),
    )

    # Second record has no edition — should be skipped
    results = [_make_result("9781737408802"), _make_result("9780000000000")]
    upserted = upsert_acquisitions(results, [None, None], "bwb")
    assert upserted == 1
    assert calls == [(7, 55, "bwb", None)]


def test_upsert_acquisitions_ol_key_path(monkeypatch):
    edition = _FakeEdition("/books/OL55M", "/works/OL7W")
    fake_site = SimpleNamespace(get=lambda key: edition if key == "/books/OL55M" else None)
    monkeypatch.setattr(web, "ctx", SimpleNamespace(site=fake_site))
    calls = []
    monkeypatch.setattr(
        bwb_opds_imports.Acquisition,
        "upsert",
        staticmethod(lambda work_id, edition_id, provider_name, local_publication_id, data=None: calls.append((work_id, edition_id))),
    )

    upserted = upsert_acquisitions([_make_result()], ["/books/OL55M"], "bwb")
    assert upserted == 1
    assert calls == [(7, 55)]


def test_upsert_acquisitions_skips_workless_edition(monkeypatch):
    monkeypatch.setattr(
        bwb_opds_imports.Edition,
        "from_isbn",
        staticmethod(lambda isbn, allow_import=False: _FakeEdition("/books/OL55M", None)),
    )
    monkeypatch.setattr(
        bwb_opds_imports.Acquisition,
        "upsert",
        staticmethod(lambda *a, **k: pytest.fail("should not upsert workless edition")),
    )
    assert upsert_acquisitions([_make_result()], [None], "bwb") == 0


def test_upsert_acquisitions_skips_missing_edition(monkeypatch):
    monkeypatch.setattr(
        bwb_opds_imports.Edition,
        "from_isbn",
        staticmethod(lambda isbn, allow_import=False: None),
    )
    monkeypatch.setattr(
        bwb_opds_imports.Acquisition,
        "upsert",
        staticmethod(lambda *a, **k: pytest.fail("should not upsert missing edition")),
    )
    assert upsert_acquisitions([_make_result()], [None], "bwb") == 0


# ---------------------------------------------------------------------------
# _registry_cursor
# ---------------------------------------------------------------------------


def test_registry_cursor_returns_none_for_none():
    assert _registry_cursor(None) is None


def test_registry_cursor_returns_none_for_null_last_updated():
    assert _registry_cursor(bwb_opds_imports.FeedRegistry({"last_updated": None})) is None


def test_registry_cursor_makes_naive_datetime_utc():
    naive = datetime.datetime(2026, 5, 1, 12, 0, 0)
    cur = _registry_cursor(bwb_opds_imports.FeedRegistry({"last_updated": naive}))
    assert cur == datetime.datetime(2026, 5, 1, 12, 0, 0, tzinfo=datetime.UTC)
