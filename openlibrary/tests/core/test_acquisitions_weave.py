from typing import Final

import pytest
import web

from openlibrary.core.acquisitions import Acquisition, add_acquisitions
from openlibrary.core.db import get_db

ACQUISITIONS_DDL: Final = """
CREATE TABLE acquisitions (
    id integer primary key, work_id integer not null, edition_id integer not null,
    provider_name text not null, local_id text not null, data json not null,
    created timestamp default current_timestamp, updated timestamp default current_timestamp,
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


def test_add_acquisitions_weaves_by_edition(acquisitions_db):
    Acquisition.upsert(
        work_id=7,
        edition_id=55,
        provider_name="lenny",
        local_id="37044775",
        data={"acquisitions": [{"access": "open-access", "format": "text/html"}]},
    )
    Acquisition.upsert(
        work_id=7,
        edition_id=55,
        provider_name="betterworldbooks",
        local_id="urn:isbn:1",
        data={"acquisitions": [{"access": "buy", "price": {"currency": "USD", "value": 1.25}}]},
    )
    docs = [
        {"key": "/books/OL55M", "title": "Flatland"},
        {"key": "/works/OL7W", "title": "a work doc"},
        {"key": "/books/OL99M", "title": "edition with no acquisitions"},
    ]
    add_acquisitions(docs)

    accesses = {a["provider_name"]: a["access"] for a in docs[0]["acquisitions"]}
    assert accesses == {"lenny": "open-access", "betterworldbooks": "buy"}
    # the price survives the flattening, which is the point of the whole feature
    bwb = next(a for a in docs[0]["acquisitions"] if a["provider_name"] == "betterworldbooks")
    assert bwb["price"] == {"currency": "USD", "value": 1.25}
    assert "acquisitions" not in docs[1]  # work doc (no /books key) skipped
    assert "acquisitions" not in docs[2]  # edition without acquisitions untouched


def test_add_acquisitions_no_edition_docs_is_noop(acquisitions_db):
    docs = [{"key": "/works/OL7W"}]
    add_acquisitions(docs)
    assert "acquisitions" not in docs[0]


def test_get_by_editions_batches(acquisitions_db):
    Acquisition.upsert(work_id=1, edition_id=10, provider_name="p", local_id="a", data={})
    Acquisition.upsert(work_id=1, edition_id=20, provider_name="p", local_id="b", data={})
    grouped = Acquisition.get_by_editions([10, 20, 30])
    assert set(grouped) == {10, 20}
    assert grouped[10][0].local_id == "a"


def test_every_link_of_a_publication_is_woven(acquisitions_db):
    """One row holds all of a publication's links, and search must expose all
    of them -- a Gutenberg book's epub and html, not just one."""
    Acquisition.upsert(
        work_id=1,
        edition_id=42,
        provider_name="project_gutenberg",
        local_id="1342",
        data={
            "acquisitions": [
                {"access": "open-access", "format": "application/epub+zip", "url": "https://g/1342.epub"},
                {"access": "open-access", "format": "text/html", "url": "https://g/1342.html"},
            ]
        },
    )
    docs = [{"key": "/books/OL42M"}]

    add_acquisitions(docs)

    formats = [a["format"] for a in docs[0]["acquisitions"]]
    assert formats == ["application/epub+zip", "text/html"]
    assert all(a["provider_name"] == "project_gutenberg" for a in docs[0]["acquisitions"])


def test_a_row_with_an_empty_acquisition_list_attaches_nothing(acquisitions_db):
    """A row can exist with no usable links; don't attach an empty key that a
    consumer would have to special-case."""
    Acquisition.upsert(work_id=1, edition_id=43, provider_name="lenny", local_id="x", data={"acquisitions": []})
    docs = [{"key": "/books/OL43M"}]

    add_acquisitions(docs)

    assert "acquisitions" not in docs[0]
