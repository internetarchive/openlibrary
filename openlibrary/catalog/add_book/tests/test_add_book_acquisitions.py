"""The catalog writes provider acquisitions during import (#12844)."""

import json
from pathlib import Path
from typing import Final

import pytest
import web

from openlibrary.bookworm import opds
from openlibrary.catalog import add_book
from openlibrary.catalog.add_book import load
from openlibrary.core.acquisitions import Acquisition
from openlibrary.core.db import get_db
from openlibrary.plugins.importapi.import_edition_builder import import_edition_builder
from openlibrary.utils import extract_numeric_id_from_olid

SAMPLES: Final = Path(__file__).parents[3] / "bookworm" / "tests" / "samples"


@pytest.fixture
def ia_writeback(monkeypatch):
    """Prevent ia writeback from making live requests."""
    monkeypatch.setattr(add_book, "update_ia_metadata_for_ol_edition", lambda olid: {})


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

FEED_REGISTRY_DDL: Final = """
CREATE TABLE feed_registry (
    id integer primary key,
    provider_name text not null,
    feed_type text not null default 'opds',
    url text not null,
    last_updated timestamp,
    data json,
    created timestamp default current_timestamp,
    updated timestamp default current_timestamp,
    UNIQUE (provider_name, url)
);
"""

# The catalog only writes acquisitions for providers with a registered feed.
REGISTERED_PROVIDERS: Final = ["lenny", "bwb"]

BASE: Final = {
    "title": "Flatland",
    "source_records": ["ia:flatland_test"],
    "ocaid": "flatland_test",
    "languages": ["eng"],
}


@pytest.fixture
def acquisitions_db():
    web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
    db = get_db()
    db.query("DROP TABLE IF EXISTS acquisitions;")
    db.query("DROP TABLE IF EXISTS feed_registry;")
    db.query(ACQUISITIONS_DDL)
    db.query(FEED_REGISTRY_DDL)
    for provider_name in REGISTERED_PROVIDERS:
        db.insert("feed_registry", provider_name=provider_name, url=f"https://{provider_name}/feed", feed_type="opds", data="{}")
    yield db
    db.query("DROP TABLE IF EXISTS acquisitions;")
    db.query("DROP TABLE IF EXISTS feed_registry;")


def test_load_upserts_acquisitions_for_new_edition(mock_site, add_languages, ia_writeback, acquisitions_db):
    rec = {
        **BASE,
        "acquisitions": [
            {
                "provider_name": "lenny",
                "local_id": "37044775",
                "data": {"access": "open-access", "url": "https://lenny/read"},
            }
        ],
    }
    reply = load(rec)
    assert reply["success"] is True

    edition_id = int(extract_numeric_id_from_olid(reply["edition"]["key"]))
    rows = Acquisition.get_by_edition(edition_id)
    assert len(rows) == 1
    assert rows[0].provider_name == "lenny"
    assert rows[0].local_id == "37044775"
    assert rows[0].data["acquisitions"][0]["access"] == "open-access"

    # acquisitions must not leak onto the edition object
    edition = mock_site.get(reply["edition"]["key"])
    assert edition.get("acquisitions") is None


def test_reimport_updates_acquisition_in_place(mock_site, add_languages, ia_writeback, acquisitions_db):
    load({**BASE, "acquisitions": [{"provider_name": "bwb", "local_id": "urn:isbn:1", "data": {"price": {"currency": "USD", "value": 1.0}}}]})
    reply = load({**BASE, "acquisitions": [{"provider_name": "bwb", "local_id": "urn:isbn:1", "data": {"price": {"currency": "USD", "value": 2.0}}}]})

    edition_id = int(extract_numeric_id_from_olid(reply["edition"]["key"]))
    rows = Acquisition.get_by_edition(edition_id)
    assert len(rows) == 1  # refreshed, not duplicated
    assert rows[0].data["acquisitions"][0]["price"]["value"] == 2.0


def test_load_without_acquisitions_still_works(mock_site, add_languages, ia_writeback, acquisitions_db):
    reply = load(dict(BASE))
    assert reply["success"] is True
    edition_id = int(extract_numeric_id_from_olid(reply["edition"]["key"]))
    assert Acquisition.get_by_edition(edition_id) == []


def test_load_skips_malformed_acquisition_without_failing_import(mock_site, add_languages, ia_writeback, acquisitions_db):
    """A malformed acquisition (missing local_id) is skipped, not fatal, after the edition saves."""
    rec = {
        **BASE,
        "acquisitions": [
            {"provider_name": "lenny"},  # missing local_id
            {"provider_name": "lenny", "local_id": "37044775", "data": {"access": "open-access"}},
        ],
    }
    reply = load(rec)
    assert reply["success"] is True

    edition_id = int(extract_numeric_id_from_olid(reply["edition"]["key"]))
    rows = Acquisition.get_by_edition(edition_id)
    assert [row.local_id for row in rows] == ["37044775"]  # malformed skipped, valid kept


def test_load_drops_acquisitions_for_unregistered_provider(mock_site, add_languages, ia_writeback, acquisitions_db):
    """The guard: only providers with a registered feed may write acquisitions.

    ImportBot POSTs feed records to the (privileged) /api/import endpoint, so the
    trust anchor is feed-registry membership, not the endpoint. A record naming an
    unregistered provider gets its acquisition silently dropped.
    """
    rec = {
        **BASE,
        "acquisitions": [
            {"provider_name": "evilcorp", "local_id": "x1", "data": {"access": "buy"}},
            {"provider_name": "lenny", "local_id": "37044775", "data": {"access": "open-access"}},
        ],
    }
    reply = load(rec)
    assert reply["success"] is True

    edition_id = int(extract_numeric_id_from_olid(reply["edition"]["key"]))
    rows = Acquisition.get_by_edition(edition_id)
    assert [row.provider_name for row in rows] == ["lenny"]  # evilcorp dropped, lenny kept


def test_end_to_end_opds_publication_to_edition_with_acquisition(mock_site, add_languages, ia_writeback, acquisitions_db):
    """Full seam: OPDS publication -> import record -> /api/import validation -> edition + acquisition.

    Exercises the real path a harvested feed record takes: parser output ->
    import_edition_builder (which runs import_validator, incl. the registered-feed
    exemption for non-ISBN feeds) -> add_book.load -> edition created + acquisition
    upserted. Lenny is the hard case (no ISBN, no publisher).
    """
    lenny = opds.Feed(provider_name="lenny", id_strategy="self_link")
    pub = opds.Publication(**json.loads((SAMPLES / "lenny.json").read_text())[0])
    rec = opds.to_import_record(pub, lenny)
    assert rec is not None
    assert rec["acquisitions"]  # parser produced a record carrying an acquisition

    # The /api/import seam: build + validate the edition dict, then load it.
    edition = import_edition_builder(init_dict=rec).get_dict()
    reply = load(edition)
    assert reply["success"] is True

    edition_id = int(extract_numeric_id_from_olid(reply["edition"]["key"]))
    rows = Acquisition.get_by_edition(edition_id)
    assert len(rows) == 1
    assert rows[0].provider_name == "lenny"
    assert rows[0].local_id == rec["acquisitions"][0]["local_id"]
    assert rows[0].data["acquisitions"][0]["access"] == "open-access"


def test_every_acquisition_of_a_publication_is_kept(mock_site, add_languages, ia_writeback, acquisitions_db):
    """All links share one row, so all of them must survive.

    `acquisitions` is UNIQUE on (local_id, provider_name). Upserting each
    acquisition of a publication separately made them overwrite one another and
    only the LAST survived -- a Gutenberg book offering epub, html and txt kept
    one link, and a record carrying both a price and a download kept whichever
    came last.
    """
    rec = {
        "title": "Multi Format",
        "source_records": ["lenny:1342"],
        "authors": [{"name": "Jane Austen"}],
        "identifiers": {"lenny": ["1342"]},
        "acquisitions": [
            {"provider_name": "lenny", "local_id": "1342", "data": {"access": "open-access", "format": "application/epub+zip", "url": "https://g/1342.epub"}},
            {"provider_name": "lenny", "local_id": "1342", "data": {"access": "open-access", "format": "text/html", "url": "https://g/1342.html"}},
            {"provider_name": "lenny", "local_id": "1342", "data": {"access": "open-access", "format": "text/plain", "url": "https://g/1342.txt"}},
        ],
    }

    load(rec)

    rows = list(acquisitions_db.select("acquisitions"))
    assert len(rows) == 1, "all links for one publication share a single row"
    stored = rows[0].data if isinstance(rows[0].data, dict) else json.loads(rows[0].data)
    assert [a["format"] for a in stored["acquisitions"]] == [
        "application/epub+zip",
        "text/html",
        "text/plain",
    ]


def test_a_later_save_replaces_withdrawn_links(mock_site, add_languages, ia_writeback, acquisitions_db):
    """The feed is authoritative for its own publication, so a link the provider
    has withdrawn must disappear rather than linger forever. That is why the set
    is replaced rather than merged into what is already stored."""
    base = {
        "title": "Shrinking Formats",
        "source_records": ["lenny:99"],
        "authors": [{"name": "A N Author"}],
        "identifiers": {"lenny": ["99"]},
    }
    load(
        dict(
            base,
            acquisitions=[
                {"provider_name": "lenny", "local_id": "99", "data": {"access": "open-access", "format": "application/epub+zip"}},
                {"provider_name": "lenny", "local_id": "99", "data": {"access": "open-access", "format": "text/html"}},
            ],
        )
    )

    # The provider drops the html edition.
    load(
        dict(
            base,
            acquisitions=[
                {"provider_name": "lenny", "local_id": "99", "data": {"access": "open-access", "format": "application/epub+zip"}},
            ],
        )
    )

    rows = list(acquisitions_db.select("acquisitions"))
    stored = rows[0].data if isinstance(rows[0].data, dict) else json.loads(rows[0].data)
    assert [a["format"] for a in stored["acquisitions"]] == ["application/epub+zip"]
