import asyncio
from typing import Final

import pytest
import web

from openlibrary.core.acquisitions import Acquisition, add_acquisitions
from openlibrary.core.db import get_db
from openlibrary.plugins.worksearch.code import (
    SearchResponse,
    _process_solr_search_response,
)

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
    # The work doc is woven too, matched on work_id. An earlier version skipped
    # anything without a /books key, which meant the obvious query --
    # /search.json?fields=key,title,acquisitions, which returns WORK docs and no
    # edition sub-documents -- silently attached nothing at all. Verified
    # against production: that query returns docs with only {key, title} and no
    # "editions" member.
    assert len(docs[1]["acquisitions"]) == 2
    assert {a["edition_key"] for a in docs[1]["acquisitions"]} == {"/books/OL55M"}
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


# ---------------------------------------------------------------------------
# Real search-response shapes.
#
# Captured from production openlibrary.org, because the two shapes are not
# interchangeable and which one a client gets depends on the fields it asked
# for. Reading the code was not enough to tell: the bug above survived unit
# tests precisely because the fixtures used a shape no real query returns.
# ---------------------------------------------------------------------------

WORK_LEVEL_RESPONSE: Final = [
    # /search.json?q=frankenstein&fields=key,title,acquisitions
    {"key": "/works/OL450063W", "title": "Frankenstein"},
    {"key": "/works/OL25595002W", "title": "Frankenstein"},
]

EDITIONS_REQUESTED_RESPONSE: Final = [
    # /search.json?q=frankenstein&fields=key,title,editions,editions.key
    {"key": "/books/OL36620178M", "title": "Frankenstein"},
    {"key": "/books/OL25422618M", "title": "Frankenstein"},
]


def test_the_naive_query_shape_gets_acquisitions(acquisitions_db):
    """A client asking only for `acquisitions` gets work docs. This is the query
    people will actually write, and it has to work."""
    Acquisition.upsert(
        work_id=450063,
        edition_id=36620178,
        provider_name="betterworldbooks",
        local_id="9781737408802",
        data={"acquisitions": [{"access": "buy", "price": {"currency": "USD", "value": 1.25}}]},
    )
    docs = [dict(doc) for doc in WORK_LEVEL_RESPONSE]
    add_acquisitions(docs)
    assert docs[0]["acquisitions"][0]["price"]["value"] == 1.25
    assert docs[0]["acquisitions"][0]["edition_key"] == "/books/OL36620178M"
    assert "acquisitions" not in docs[1], "a work with no acquisitions gains no key"


def test_the_editions_requested_shape_also_gets_acquisitions(acquisitions_db):
    Acquisition.upsert(
        work_id=450063,
        edition_id=36620178,
        provider_name="lenny",
        local_id="36620178",
        data={"acquisitions": [{"access": "open-access", "format": "text/html"}]},
    )
    docs = [dict(doc) for doc in EDITIONS_REQUESTED_RESPONSE]
    add_acquisitions(docs)
    assert docs[0]["acquisitions"][0]["access"] == "open-access"
    assert "acquisitions" not in docs[1]


def test_a_work_result_names_which_edition_each_price_belongs_to(acquisitions_db):
    """At work level a price is meaningless without saying which edition it is
    for -- a work can have thousands, at different prices."""
    for edition_id, value in ((36620178, 1.25), (25422618, 9.99)):
        Acquisition.upsert(
            work_id=450063,
            edition_id=edition_id,
            provider_name="betterworldbooks",
            local_id=f"isbn-{edition_id}",
            data={"acquisitions": [{"access": "buy", "price": {"currency": "USD", "value": value}}]},
        )
    docs = [dict(WORK_LEVEL_RESPONSE[0])]
    add_acquisitions(docs)
    by_edition = {a["edition_key"]: a["price"]["value"] for a in docs[0]["acquisitions"]}
    assert by_edition == {"/books/OL36620178M": 1.25, "/books/OL25422618M": 9.99}


def test_mixed_work_and_edition_docs_in_one_page(acquisitions_db):
    """Both shapes can appear together, and each must be matched on its own id."""
    Acquisition.upsert(
        work_id=450063,
        edition_id=36620178,
        provider_name="lenny",
        local_id="a",
        data={"acquisitions": [{"access": "open-access"}]},
    )
    docs = [{"key": "/works/OL450063W"}, {"key": "/books/OL36620178M"}, {"key": "/authors/OL1A"}]
    add_acquisitions(docs)
    assert docs[0]["acquisitions"][0]["access"] == "open-access"
    assert docs[1]["acquisitions"][0]["access"] == "open-access"
    assert "acquisitions" not in docs[2], "a non-book, non-work key is ignored"


# ---------------------------------------------------------------------------
# The wiring, not just the weaving.
#
# add_acquisitions being correct does not mean search.json calls it. This
# exercises the real post-processing function with the real response object, so
# the field check and the doc extraction are covered rather than assumed.
# ---------------------------------------------------------------------------


def _solr_response(docs: list[dict]):
    return SearchResponse(
        facet_counts={},
        sort="",
        docs=docs,
        num_found=len(docs),
        solr_select="",
        raw_resp={"response": {"docs": docs, "numFound": len(docs)}},
    )


def _process(docs: list[dict], fields):
    return asyncio.run(_process_solr_search_response(_solr_response(docs), fields))


@pytest.fixture
def one_acquisition(acquisitions_db):
    Acquisition.upsert(
        work_id=450063,
        edition_id=36620178,
        provider_name="betterworldbooks",
        local_id="isbn-1",
        data={"acquisitions": [{"access": "buy", "price": {"currency": "USD", "value": 1.25}}]},
    )
    return acquisitions_db


def test_search_weaves_when_the_field_is_requested(one_acquisition):
    """The field list arrives here already split into a list."""
    out = _process([{"key": "/works/OL450063W"}], ["key", "title", "acquisitions"])
    assert out["docs"][0]["acquisitions"][0]["price"]["value"] == 1.25


def test_search_does_not_weave_when_the_field_is_not_requested(one_acquisition):
    """Nobody pays for a database query they did not ask for."""
    out = _process([{"key": "/works/OL450063W"}], ["key", "title"])
    assert "acquisitions" not in out["docs"][0]


def test_a_star_field_list_does_not_weave(one_acquisition):
    """`fields=*` does NOT include acquisitions, and that is deliberate.

    Verified against production: `?fields=*` does not include `availability`
    either, because by this point the field list is `["*"]` and the `fields ==
    "*"` comparison cannot match a list. Acquisitions follow availability
    exactly -- ask for them by name. Pinned because the asymmetry is surprising
    and would otherwise look like a bug worth "fixing" into a database query on
    every wildcard search.
    """
    out = _process([{"key": "/works/OL450063W"}], ["*"])
    assert "acquisitions" not in out["docs"][0]


def test_edition_subdocs_are_woven_not_the_work_wrapper(one_acquisition):
    """When editions are requested the acquisition belongs on the edition doc."""
    docs = [{"key": "/works/OL450063W", "editions": {"docs": [{"key": "/books/OL36620178M"}]}}]
    out = _process(docs, ["key", "editions", "acquisitions"])
    edition = out["docs"][0]["editions"]["docs"][0]
    assert edition["acquisitions"][0]["price"]["value"] == 1.25
    assert "acquisitions" not in out["docs"][0], "the wrapper work doc is not the target"
