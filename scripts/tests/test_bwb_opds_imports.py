import datetime
import io
import json
from pathlib import Path
from typing import Final

import pytest
import web

from openlibrary.catalog import opds2
from openlibrary.core.acquisitions import Acquisition
from openlibrary.core.db import get_db
from openlibrary.core.tbp import FeedRegistry

from .. import bwb_opds_imports
from ..bwb_opds_imports import (
    EPOCH,
    commit_batch,
    map_publication_to_olbook,
    process_feed,
    read_state,
    write_state,
)

# Generic OPDS 2.0 parsing/crawl is tested in openlibrary/catalog/tests/test_opds2.py.
# This module covers the BWB-specific specialization + orchestration: the BWB
# Source config, batch staging + idempotency, the FeedRegistry cursor, and the
# acquisitions wiring.

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

SAMPLE_FEED_URL: Final = "https://www.betterworldbooks.com/opds/"
SAMPLE_FEED: Final = json.loads((Path(__file__).parent / "opds_sample.json").read_text())


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


# ---------------------------------------------------------------------------
# BWB Source specialization of the generic adapter
# ---------------------------------------------------------------------------


def test_map_publication_uses_bwb_source():
    # The BWB wrapper injects BWB_SOURCE, so source_records carries the bwb slug.
    olbook = map_publication_to_olbook(SAMPLE_PUBLICATION)
    assert olbook is not None
    assert olbook["isbn_13"] == ["9781737408802"]
    assert olbook["source_records"] == ["bwb:9781737408802"]


def test_bwb_source_wires_quality_filter():
    assert bwb_opds_imports.BWB_SOURCE.provider_name == "betterworldbooks"
    assert bwb_opds_imports.BWB_SOURCE.source_id_prefix == "bwb"
    assert bwb_opds_imports.BWB_SOURCE.record_filter is bwb_opds_imports._bwb_record_filter
    # A normal book is kept (not excluded).
    assert bwb_opds_imports._bwb_record_filter(map_publication_to_olbook(SAMPLE_PUBLICATION)) is False


# ---------------------------------------------------------------------------
# State file + lazy price writer
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# End-to-end idempotency (epic #12844): re-running the importer against the
# same feed state must not create duplicate import_item rows. Uses the
# synthetic opds_sample.json feed so the check is reliable and offline.
# ---------------------------------------------------------------------------

IMPORT_BATCH_DDL: Final = """
CREATE TABLE import_batch (
    id integer primary key,
    name text,
    submitter text,
    submit_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

IMPORT_ITEM_DDL: Final = """
CREATE TABLE import_item (
    id serial primary key,
    batch_id integer,
    status text default 'pending',
    error text,
    ia_id text,
    data text,
    ol_key text,
    comments text,
    submitter text,
    UNIQUE (batch_id, ia_id)
);
"""


@pytest.fixture
def import_db():
    web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
    db = get_db()
    # get_db() is a process-wide cached connection shared with other test
    # modules (e.g. test_imports.py). Drop/recreate so this module owns a
    # clean schema regardless of collection order.
    db.query("DROP TABLE IF EXISTS import_item;")
    db.query("DROP TABLE IF EXISTS import_batch;")
    db.query(IMPORT_BATCH_DDL)
    db.query(IMPORT_ITEM_DDL)
    yield db
    db.query("DROP TABLE IF EXISTS import_item;")
    db.query("DROP TABLE IF EXISTS import_batch;")


def _olbooks_from_sample(monkeypatch):
    # The crawl lives in opds2, so patch the session/sleep there (the BWB
    # process_feed wrapper delegates to opds2.process_feed).
    monkeypatch.setattr(opds2, "PAGE_SLEEP_SECONDS", 0)
    session = FakeSession({SAMPLE_FEED_URL: SAMPLE_FEED})
    monkeypatch.setattr(opds2.requests, "Session", lambda: session)
    olbooks, _ = process_feed(feed_url=SAMPLE_FEED_URL, since=EPOCH, prices_out_fh=io.StringIO())
    return olbooks


def _count(db) -> int:
    return len(list(db.select("import_item")))


def test_process_feed_maps_sample_feed(monkeypatch):
    olbooks = _olbooks_from_sample(monkeypatch)
    assert {b["isbn_13"][0] for b in olbooks} == {"9781737408802", "9798995425007"}
    assert all(b["source_records"][0].startswith("bwb:") for b in olbooks)


def test_commit_batch_is_idempotent_within_same_batch(monkeypatch, import_db):
    olbooks = _olbooks_from_sample(monkeypatch)
    commit_batch("bwb-opds-2026-06-16", olbooks)
    assert _count(import_db) == 2
    # Re-running the same feed into the same day's batch must add nothing.
    commit_batch("bwb-opds-2026-06-16", olbooks)
    assert _count(import_db) == 2
    ia_ids = {row.ia_id for row in import_db.select("import_item")}
    assert ia_ids == {"bwb:9781737408802", "bwb:9798995425007"}


def test_commit_batch_is_idempotent_across_batches(monkeypatch, import_db):
    """A later run (new daily batch) must not re-stage already-imported records."""
    olbooks = _olbooks_from_sample(monkeypatch)
    commit_batch("bwb-opds-2026-06-16", olbooks)
    assert _count(import_db) == 2
    # Next day's batch: dedupe_items filters ia_ids present in ANY batch.
    commit_batch("bwb-opds-2026-06-17", olbooks)
    assert _count(import_db) == 2


# ---------------------------------------------------------------------------
# Acquisitions wiring (epic #12844, subtask 2): BWB ingestion is the first
# writer of the (previously dormant) acquisitions table. Upserts are keyed on
# (local_id, provider_name) so re-running the feed refreshes rather than
# duplicates provider acquisition metadata.
# ---------------------------------------------------------------------------

ACQUISITIONS_DDL: Final = """
CREATE TABLE acquisitions (
    id integer primary key,
    work_id integer not null,
    edition_id integer not null,
    provider_name text not null,
    local_id text not null,
    data json not null,
    created timestamp default current_timestamp,
    updated timestamp default current_timestamp,
    UNIQUE (local_id, provider_name)
);
"""


@pytest.fixture
def acquisitions_db():
    web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
    db = get_db()
    db.query("DROP TABLE IF EXISTS acquisitions;")
    db.query(ACQUISITIONS_DDL)
    yield db
    db.query("DROP TABLE IF EXISTS acquisitions;")


def test_upsert_acquisition_is_idempotent(acquisitions_db):
    pub = SAMPLE_FEED["publications"][0]
    first = bwb_opds_imports.upsert_acquisition(work_id=10, edition_id=100, isbn_13="9781737408802", publication=pub)
    assert first is not None
    assert len(Acquisition.get_by_edition(100, "betterworldbooks")) == 1
    # Re-running the same feed refreshes the same row, does not duplicate.
    bwb_opds_imports.upsert_acquisition(work_id=10, edition_id=100, isbn_13="9781737408802", publication=pub)
    rows = Acquisition.get_by_edition(100, "betterworldbooks")
    assert len(rows) == 1
    assert rows[0].local_id == "urn:isbn:9781737408802"
    assert rows[0].data["price"] == {"currency": "USD", "value": 1.25}


def test_upsert_acquisition_updates_changed_price(acquisitions_db):
    pub = SAMPLE_FEED["publications"][0]
    bwb_opds_imports.upsert_acquisition(work_id=10, edition_id=100, isbn_13="9781737408802", publication=pub)
    # Simulate the price changing in a later feed pull.
    changed = json.loads(json.dumps(pub))
    for link in changed["links"]:
        if link.get("rel") == opds2.ACQUISITION_REL:
            link["properties"]["price"]["value"] = 3.50
    bwb_opds_imports.upsert_acquisition(work_id=10, edition_id=100, isbn_13="9781737408802", publication=changed)
    rows = Acquisition.get_by_edition(100, "betterworldbooks")
    assert len(rows) == 1
    assert rows[0].data["price"]["value"] == 3.50


# ---------------------------------------------------------------------------
# Cursor source: the FeedRegistry DB cursor is the source of truth for BWB's
# incremental state; the file-state is a fallback only.
# ---------------------------------------------------------------------------

TBP_FEED_REGISTRY_DDL: Final = """
CREATE TABLE tbp_feed_registry (
    id integer primary key,
    provider_name text not null,
    feed_type text not null,
    url text not null,
    last_updated timestamp default null,
    data text not null default '{}',
    created timestamp default current_timestamp,
    updated timestamp default current_timestamp,
    UNIQUE (provider_name, url)
);
"""

FEED_URL: Final = "https://www.betterworldbooks.com/opds"


@pytest.fixture
def registry_db():
    web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
    db = get_db()
    db.query("DROP TABLE IF EXISTS tbp_feed_registry;")
    db.query(TBP_FEED_REGISTRY_DDL)
    yield db
    db.query("DROP TABLE IF EXISTS tbp_feed_registry;")


def test_resolve_cutoff_prefers_explicit_since(registry_db, tmp_path):
    # --since wins over everything and does not require a registered feed.
    cutoff = bwb_opds_imports.resolve_cutoff(FEED_URL, since="2026-01-02T00:00:00+00:00", state_file=str(tmp_path / "s.txt"))
    assert cutoff == datetime.datetime(2026, 1, 2, 0, 0, 0, tzinfo=datetime.UTC)


def test_resolve_cutoff_uses_registry_cursor(registry_db, tmp_path):
    FeedRegistry.register("betterworldbooks", FEED_URL)
    feed = FeedRegistry.find("betterworldbooks", FEED_URL)
    FeedRegistry.advance(feed.id, last_updated=datetime.datetime(2026, 6, 1, 0, 0, 0))
    cutoff = bwb_opds_imports.resolve_cutoff(FEED_URL, since=None, state_file=str(tmp_path / "s.txt"))
    assert cutoff == datetime.datetime(2026, 6, 1, 0, 0, 0, tzinfo=datetime.UTC)


def test_resolve_cutoff_falls_back_to_file_state(registry_db, tmp_path):
    # Feed not registered -> use the file-state fallback.
    state = tmp_path / "s.txt"
    ts = datetime.datetime(2026, 3, 3, tzinfo=datetime.UTC)
    bwb_opds_imports.write_state(str(state), ts)
    cutoff = bwb_opds_imports.resolve_cutoff(FEED_URL, since=None, state_file=str(state))
    assert cutoff == ts


def test_advance_cursor_updates_registry_and_file(registry_db, tmp_path):
    FeedRegistry.register("betterworldbooks", FEED_URL)
    state = tmp_path / "s.txt"
    ts = datetime.datetime(2026, 6, 16, 17, 2, 54, tzinfo=datetime.UTC)
    bwb_opds_imports.advance_cursor(FEED_URL, ts, str(state))
    feed = FeedRegistry.find("betterworldbooks", FEED_URL)
    assert str(feed.last_updated).startswith("2026-06-16 17:02:54")
    assert bwb_opds_imports.read_state(str(state)) == ts


def test_advance_cursor_unregistered_feed_writes_only_file(registry_db, tmp_path):
    state = tmp_path / "s.txt"
    ts = datetime.datetime(2026, 6, 16, tzinfo=datetime.UTC)
    bwb_opds_imports.advance_cursor(FEED_URL, ts, str(state))
    assert FeedRegistry.find("betterworldbooks", FEED_URL) is None
    assert bwb_opds_imports.read_state(str(state)) == ts


# ---------------------------------------------------------------------------
# Edition resolution + acquisition staging (option (a)): attach acquisitions to
# ISBNs that already resolve to an edition; defer the rest to the post-import
# hook.
# ---------------------------------------------------------------------------


class FakeWork:
    def __init__(self, key):
        self.key = key


class FakeEdition:
    def __init__(self, key, works, isbn_13=None):
        self.key = key
        self.works = works
        self.isbn_13 = isbn_13 or []


class FakeSite:
    def __init__(self, thing_keys, editions):
        self._thing_keys = thing_keys
        self._editions = editions

    def things(self, query):
        return self._thing_keys

    def get(self, key):
        return self._editions.get(key)


def _patch_site(monkeypatch, site):
    # Set only web.ctx.site; do not replace web.ctx itself (the DB layer's
    # infogami stats hook needs web.ctx to stay dict-like).
    monkeypatch.setattr(bwb_opds_imports.web.ctx, "site", site, raising=False)


def test_resolve_edition_ids_existing(monkeypatch):
    site = FakeSite(["/books/OL55M"], {"/books/OL55M": FakeEdition("/books/OL55M", [FakeWork("/works/OL7W")])})
    _patch_site(monkeypatch, site)
    assert bwb_opds_imports.resolve_edition_ids("9781737408802") == (7, 55)


def test_resolve_edition_ids_not_in_catalog(monkeypatch):
    _patch_site(monkeypatch, FakeSite([], {}))
    assert bwb_opds_imports.resolve_edition_ids("9781737408802") is None


def test_resolve_edition_ids_edition_without_work(monkeypatch):
    site = FakeSite(["/books/OL55M"], {"/books/OL55M": FakeEdition("/books/OL55M", [])})
    _patch_site(monkeypatch, site)
    assert bwb_opds_imports.resolve_edition_ids("9781737408802") is None


def test_stage_acquisitions_only_resolved(monkeypatch, acquisitions_db):
    monkeypatch.setattr(bwb_opds_imports, "resolve_edition_ids", {"9781737408802": (7, 55)}.get)
    items = [
        ("9781737408802", {"price": {"currency": "USD", "value": 1.25}}),
        ("9798995425007", {"price": {"currency": "USD", "value": 1.01}}),
    ]
    assert bwb_opds_imports.stage_acquisitions(items) == 1
    rows = Acquisition.get_by_edition(55, "betterworldbooks")
    assert len(rows) == 1
    assert rows[0].local_id == "urn:isbn:9781737408802"
    assert rows[0].data["price"]["value"] == 1.25


def test_stage_acquisitions_is_idempotent(monkeypatch, acquisitions_db):
    monkeypatch.setattr(bwb_opds_imports, "resolve_edition_ids", lambda isbn: (7, 55))
    items = [("9781737408802", {"price": {"currency": "USD", "value": 1.25}})]
    bwb_opds_imports.stage_acquisitions(items)
    bwb_opds_imports.stage_acquisitions(items)
    assert len(Acquisition.get_by_edition(55, "betterworldbooks")) == 1


def test_link_acquisition_for_edition_post_import(monkeypatch, acquisitions_db):
    ed = FakeEdition("/books/OL55M", [FakeWork("/works/OL7W")], isbn_13=["9781737408802"])
    _patch_site(monkeypatch, FakeSite([], {"/books/OL55M": ed}))
    result = bwb_opds_imports.link_acquisition_for_edition("/books/OL55M", SAMPLE_FEED["publications"][0])
    assert result is not None
    rows = Acquisition.get_by_edition(55, "betterworldbooks")
    assert len(rows) == 1
    assert rows[0].data["price"] == {"currency": "USD", "value": 1.25}
